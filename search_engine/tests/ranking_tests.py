"""
ranking_tests.py — Unit tests for MINISEARCH ranking components.

Tests ranking logic directly using synthetic documents inserted into a temp DB.
No live API or external network needed.
"""

import os
import sys
import math
import tempfile
import sqlite3
import datetime
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from storage.database import Database
from storage.schema import (
    DOCUMENTS_TABLE, IMAGES_TABLE, LINKS_TABLE,
    QUERY_LOGS_TABLE, QUERY_CACHE_TABLE,
)
from search.query_processor import QueryProcessor
from search.bm25_ranker import BM25Ranker
from search.search_engine import SearchEngine, _normalize, _freshness, DOC_SCORE_WEIGHTS
from indexing.index_builder import IndexBuilder


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_temp_db(path: str) -> Database:
    db = Database(db_path=path)
    return db


def insert_doc(db: Database, url: str, title: str, content: str,
               author: str = None, doc_type: str = "HTML",
               pagerank: float = 0.0, days_old: int = 0) -> int:
    crawled_at = (
        datetime.datetime.now() - datetime.timedelta(days=days_old)
    ).isoformat()
    with db.lock:
        db.cursor.execute(
            """
            INSERT OR REPLACE INTO documents
              (url, title, content, author, doc_type, html_file, content_hash,
               indexed_at, pagerank, crawled_at)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            """,
            (url, title, content, author, doc_type, pagerank, crawled_at),
        )
        db.conn.commit()
        return db.cursor.lastrowid


def build_index_for_db(db_path: str, index_dir: str):
    builder = IndexBuilder(db_path=db_path, index_dir=index_dir)
    builder.build(incremental=False)
    builder.save()
    builder.close()


# ── Test Suite ─────────────────────────────────────────────────────────────────

class TestNormalize(unittest.TestCase):

    def test_normal_case(self):
        scores = {"a": 0.0, "b": 5.0, "c": 10.0}
        n = _normalize(scores)
        self.assertAlmostEqual(n["a"], 0.0)
        self.assertAlmostEqual(n["c"], 1.0)
        self.assertAlmostEqual(n["b"], 0.5)

    def test_all_equal(self):
        scores = {"a": 3.0, "b": 3.0}
        n = _normalize(scores)
        self.assertEqual(n["a"], 0.0)
        self.assertEqual(n["b"], 0.0)

    def test_empty(self):
        self.assertEqual(_normalize({}), {})


class TestFreshness(unittest.TestCase):

    def test_today(self):
        f = _freshness(datetime.datetime.now().isoformat())
        self.assertAlmostEqual(f, 1.0, places=2)

    def test_one_year_old(self):
        one_year = (datetime.datetime.now() - datetime.timedelta(days=365)).isoformat()
        f = _freshness(one_year)
        self.assertAlmostEqual(f, math.exp(-1), places=2)

    def test_unknown(self):
        self.assertEqual(_freshness(None), 0.5)
        self.assertEqual(_freshness(""), 0.5)

    def test_newer_beats_older(self):
        new = _freshness((datetime.datetime.now() - datetime.timedelta(days=30)).isoformat())
        old = _freshness((datetime.datetime.now() - datetime.timedelta(days=500)).isoformat())
        self.assertGreater(new, old)


class TestRankingWithSyntheticDocs(unittest.TestCase):
    """
    Each test creates an isolated temp DB + index, inserts synthetic docs,
    runs SearchEngine, and asserts ordering.
    """

    def _make_engine(self, docs: list) -> tuple:
        """docs = list of (url, title, content, pagerank, days_old, doc_type)"""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.db")
        index_dir = os.path.join(tmpdir, "index")
        os.makedirs(index_dir)

        db = make_temp_db(db_path)
        for url, title, content, pr, days_old, doc_type in docs:
            insert_doc(db, url, title, content,
                       doc_type=doc_type, pagerank=pr, days_old=days_old)

        build_index_for_db(db_path, index_dir)

        engine = SearchEngine.__new__(SearchEngine)
        engine.query_processor = QueryProcessor()
        from search.query_understanding import QueryUnderstanding
        from search.snippet_generator import SnippetGenerator
        from search.index_reader import IndexReader
        from search.retriever import Retriever

        engine.query_understanding = QueryUnderstanding()
        engine.db = Database(db_path=db_path)
        engine.snippet_generator = SnippetGenerator()

        engine.index_reader = IndexReader(index_type="document", index_dir=index_dir)
        engine.retriever = Retriever(engine.index_reader)
        engine.ranker = BM25Ranker(engine.index_reader)
        engine.pageranks = engine.db.get_all_pageranks()
        engine.domain_authority = {}  # no link graph in synthetic tests

        from search.index_reader import IndexReader as IR2
        img_ir = IR2(index_type="image", index_dir=index_dir)
        engine.image_index_reader = img_ir
        engine.image_retriever = Retriever(img_ir)
        engine.image_ranker = BM25Ranker(img_ir, weights={
            "alt_text": 4.0, "surrounding_text": 1.5,
            "page_title": 2.0, "image_url": 1.0, "filename": 3.0,
        })

        return engine

    # ── Test 1: Title boost ───────────────────────────────────────────────────

    def test_title_boost_beats_content_only(self):
        """
        Doc A: query term in title AND content.
        Doc B: query term in content only (longer content for higher raw TF).
        A must rank above B.
        """
        docs = [
            ("http://a.test/", "Python Decorators Guide",
             "This page explains python decorators in detail.",
             0.0, 0, "HTML"),
            ("http://b.test/", "Advanced Programming Concepts",
             " ".join(["python decorators"] * 5) + " advanced patterns.",
             0.0, 0, "HTML"),
        ]
        engine = self._make_engine(docs)
        results = engine.search("python decorators", limit=10)
        self.assertGreaterEqual(len(results), 2,
                                f"Expected >=2 results, got {len(results)}")
        urls = [r["url"] for r in results]
        self.assertIn("http://a.test/", urls)
        self.assertIn("http://b.test/", urls)
        pos_a = urls.index("http://a.test/")
        pos_b = urls.index("http://b.test/")
        self.assertLess(pos_a, pos_b,
                        f"Title doc should rank above content-only doc. Got order: {urls}")

    # ── Test 2: Phrase boost ──────────────────────────────────────────────────

    def test_phrase_boost_adjacent_beats_split(self):
        """
        Doc A: 'python decorators' adjacent.
        Doc B: 'python' and 'decorators' far apart.
        Phrase query \"python decorators\" → A must rank higher.
        """
        docs = [
            ("http://a.test/", "A",
             "Python decorators are functions that wrap other functions.",
             0.0, 0, "HTML"),
            ("http://b.test/", "B",
             "Python is a language. " + "word " * 50 + " decorators are patterns.",
             0.0, 0, "HTML"),
        ]
        engine = self._make_engine(docs)
        results = engine.search('"python decorators"', limit=10)
        # Doc B may not even appear (strict phrase filter)
        urls = [r["url"] for r in results]
        self.assertIn("http://a.test/", urls,
                      "Adjacent phrase doc must be in results")
        if "http://b.test/" in urls:
            pos_a = urls.index("http://a.test/")
            pos_b = urls.index("http://b.test/")
            self.assertLess(pos_a, pos_b,
                            "Phrase doc must rank above non-phrase doc")

    # ── Test 3: Authority boost ───────────────────────────────────────────────

    def test_authority_boost_high_pagerank_wins(self):
        """
        Doc A: pagerank=10 (high authority).
        Doc B: pagerank=0.01 (low authority).
        Same title and content → A must rank above B.
        """
        content = "Python asyncio is an asynchronous framework for Python."
        docs = [
            ("http://low.test/",  "Python Asyncio", content, 0.01, 0, "HTML"),
            ("http://high.test/", "Python Asyncio", content, 10.0, 0, "HTML"),
        ]
        engine = self._make_engine(docs)
        results = engine.search("python asyncio", limit=10)
        urls = [r["url"] for r in results]
        self.assertIn("http://high.test/", urls)
        self.assertIn("http://low.test/", urls)
        pos_high = urls.index("http://high.test/")
        pos_low = urls.index("http://low.test/")
        self.assertLess(pos_high, pos_low,
                        f"High-PR doc should outrank low-PR. Order: {urls}")

    # ── Test 4: Freshness boost ───────────────────────────────────────────────

    def test_freshness_boost_recent_beats_stale(self):
        """
        Doc A: crawled today.
        Doc B: crawled 3 years ago.
        Same content → A must rank above B.
        """
        content = "Machine learning models and neural networks latest ai research."
        docs = [
            ("http://stale.test/", "ML Research", content, 0.0, 1095, "HTML"),
            ("http://fresh.test/", "ML Research", content, 0.0, 0,    "HTML"),
        ]
        engine = self._make_engine(docs)
        results = engine.search("machine learning", limit=10)
        urls = [r["url"] for r in results]
        self.assertIn("http://fresh.test/", urls)
        self.assertIn("http://stale.test/", urls)
        pos_fresh = urls.index("http://fresh.test/")
        pos_stale = urls.index("http://stale.test/")
        self.assertLess(pos_fresh, pos_stale,
                        f"Fresh doc should outrank stale. Order: {urls}")

    # ── Test 5: URL match boost ───────────────────────────────────────────────

    def test_url_match_boosts_relevant_urls(self):
        """
        Doc A: URL contains query tokens (python-asyncio).
        Doc B: URL is opaque (/page/1234).
        Same content → A should rank above or equal to B.
        """
        content = "Asyncio is Python's built-in async framework for concurrent code."
        docs = [
            ("http://docs.test/python-asyncio/",  "Asyncio", content, 0.0, 0, "HTML"),
            ("http://docs.test/page/1234/",         "Asyncio", content, 0.0, 0, "HTML"),
        ]
        engine = self._make_engine(docs)
        results = engine.search("python asyncio", limit=10)
        urls = [r["url"] for r in results]
        if len(urls) >= 2:
            pos_a = urls.index("http://docs.test/python-asyncio/")
            pos_b = urls.index("http://docs.test/page/1234/")
            self.assertLessEqual(pos_a, pos_b,
                                 "URL-matching doc should rank at least as high")

    # ── Test 6: PDF intent boost ──────────────────────────────────────────────

    def test_pdf_intent_boosts_pdf_docs(self):
        """
        Query contains 'pdf' → PDF docs get ×1.3 boost.
        Doc A: HTML, identical content.
        Doc B: PDF, identical content.
        With PDF intent, B should appear before A.
        """
        content = "Operating system notes memory management processes scheduling."
        docs = [
            ("http://site.test/notes.html", "OS Notes", content, 0.0, 0, "HTML"),
            ("http://site.test/notes.pdf",  "OS Notes", content, 0.0, 0, "PDF"),
        ]
        engine = self._make_engine(docs)
        results = engine.search("operating system notes pdf", limit=10)
        urls = [r["url"] for r in results]
        doc_types = [r["doc_type"] for r in results]
        self.assertIn("PDF", doc_types,
                      "PDF doc must appear in results for PDF-intent query")
        if len(urls) >= 2:
            # PDF should appear before or at same position as HTML
            pdf_positions = [i for i, dt in enumerate(doc_types) if dt == "PDF"]
            html_positions = [i for i, dt in enumerate(doc_types) if dt == "HTML"]
            if pdf_positions and html_positions:
                self.assertLess(min(pdf_positions), min(html_positions),
                                "PDF doc should rank above HTML for PDF-intent query")

    # ── Test 7: proximity decay ───────────────────────────────────────────────

    def test_proximity_adjacent_beats_distant(self):
        """
        Doc A: 'deepfake detection' adjacent (distance=1).
        Doc B: 'deepfake' and 'detection' 50 words apart.
        A must rank higher.
        """
        docs = [
            ("http://close.test/", "Detection",
             "This paper presents a deepfake detection system using deep learning.",
             0.0, 0, "HTML"),
            ("http://far.test/", "Detection",
             "Deepfake technology has advanced rapidly. " + "word " * 50 +
             " The detection of such media remains challenging.",
             0.0, 0, "HTML"),
        ]
        engine = self._make_engine(docs)
        results = engine.search("deepfake detection", limit=10)
        urls = [r["url"] for r in results]
        self.assertIn("http://close.test/", urls)
        if "http://far.test/" in urls:
            pos_close = urls.index("http://close.test/")
            pos_far = urls.index("http://far.test/")
            self.assertLess(pos_close, pos_far,
                            f"Adjacent doc should rank above distant. Order: {urls}")


class TestWeightSanity(unittest.TestCase):

    def test_doc_weights_sum_to_one(self):
        total = sum(DOC_SCORE_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, places=6,
                               msg=f"DOC_SCORE_WEIGHTS must sum to 1.0, got {total}")

    def test_all_weights_positive(self):
        for k, v in DOC_SCORE_WEIGHTS.items():
            self.assertGreater(v, 0, f"Weight {k} must be > 0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
