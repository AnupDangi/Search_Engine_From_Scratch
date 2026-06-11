# search/search_engine.py

import re
import math
import datetime
from collections import defaultdict
from urllib.parse import urlparse

from search.query_processor import QueryProcessor
from search.query_understanding import QueryUnderstanding
from search.index_reader import IndexReader
from search.retriever import Retriever
from storage.database import Database
from search.bm25_ranker import BM25Ranker
from search.snippet_generator import SnippetGenerator


# ── Scoring weights ────────────────────────────────────────────────────────────
DOC_SCORE_WEIGHTS = {
    "bm25f": 0.50,
    "phrase_prox": 0.20,
    "authority": 0.15,
    "freshness": 0.10,
    "url_match": 0.05,
}

IMG_SCORE_WEIGHTS = {
    "bm25f": 0.60,
    "phrase_prox": 0.30,
    "authority": 0.10,
}

# Penalise icon/favicon/sprite images — visually useless in results
_ICON_PATTERNS = re.compile(
    r'(favicon|/icon[s]?[/_\-]|sprite|badge|button|logo\d|\.ico$|_icon\.|icon_|'
    r'arrow|bullet|star\.png|rating|thumbnail_s)',
    re.I,
)

_IMAGE_RANKER_WEIGHTS = {
    "alt_text": 4.0,
    "surrounding_text": 1.5,
    "page_title": 2.0,
    "image_url": 1.0,
    "filename": 3.0,
}
_IMAGE_RANKER_B = {
    "alt_text": 0.5,
    "surrounding_text": 0.75,
    "page_title": 0.5,
    "image_url": 0.5,
    "filename": 0.5,
}


def _extract_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.lstrip("www.")
    except Exception:
        return ""


def parse_query(query_str: str):
    pattern = r'"([^"]+)"|(\S+)'
    matches = re.findall(pattern, query_str)
    strict_phrases = []
    terms = []
    for phrase_match, term_match in matches:
        if phrase_match:
            strict_phrases.append(phrase_match)
        elif term_match:
            terms.append(term_match)
    return strict_phrases, terms


def check_phrase_in_field(phrase_terms, field_positions):
    if not phrase_terms:
        return True
    if any(term not in field_positions or not field_positions[term] for term in phrase_terms):
        return False
    first_term = phrase_terms[0]
    other_pos_sets = [set(field_positions[term]) for term in phrase_terms[1:]]
    for p in field_positions[first_term]:
        if all((p + i + 1) in other_pos_sets[i] for i in range(len(other_pos_sets))):
            return True
    return False


def _normalize(scores: dict) -> dict:
    if not scores:
        return {}
    lo = min(scores.values())
    hi = max(scores.values())
    if hi == lo:
        return {k: 0.0 for k in scores}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}


def _freshness(crawled_at_str) -> float:
    if not crawled_at_str:
        return 0.5
    try:
        crawled_at = datetime.datetime.fromisoformat(str(crawled_at_str))
        days_old = max(0, (datetime.datetime.now() - crawled_at).days)
        return math.exp(-days_old / 365.0)
    except Exception:
        return 0.5


def _diversify(results: list, max_per_domain: int = 3) -> list:
    """Cap results per domain to avoid one site dominating the SERP."""
    seen: dict = {}
    out = []
    for r in results:
        d = r.get("domain", "")
        count = seen.get(d, 0)
        if count < max_per_domain:
            out.append(r)
            seen[d] = count + 1
    return out


class SearchEngine:

    def __init__(self):
        self.query_processor = QueryProcessor()
        self.query_understanding = QueryUnderstanding()
        self.db = Database()
        self.snippet_generator = SnippetGenerator()

        # Document search stack
        self.index_reader = IndexReader(index_type="document")
        self.retriever = Retriever(self.index_reader)
        self.ranker = BM25Ranker(self.index_reader)
        self.pageranks = self.db.get_all_pageranks()

        # Image search stack
        self.image_index_reader = IndexReader(index_type="image")
        self.image_retriever = Retriever(self.image_index_reader)
        self.image_ranker = BM25Ranker(
            self.image_index_reader,
            weights=_IMAGE_RANKER_WEIGHTS,
            b_map=_IMAGE_RANKER_B,
        )

        # Domain-level authority (built from pageranks + doc metadata)
        self.domain_authority: dict = {}
        self._build_domain_authority()

    def _build_domain_authority(self):
        """Compute mean PageRank per domain, cached in self.domain_authority."""
        try:
            with self.db.lock:
                self.db.cursor.execute("SELECT url, pagerank FROM documents")
                doc_rows = self.db.cursor.fetchall()
        except Exception:
            self.domain_authority = {}
            return

        domain_prs: dict = defaultdict(list)
        for url, pr in doc_rows:
            if url:
                d = _extract_domain(url)
                if d:
                    domain_prs[d].append(pr or 0.0)

        self.domain_authority = {
            d: sum(prs) / len(prs)
            for d, prs in domain_prs.items()
            if prs
        }

    def _doc_authority(self, doc_id: int, doc_url: str) -> float:
        """Blend per-doc PageRank (60%) with domain mean PageRank (40%)."""
        doc_pr = self.pageranks.get(doc_id, 0.0)
        dom_pr = self.domain_authority.get(_extract_domain(doc_url), 0.0)
        blended = 0.6 * doc_pr + 0.4 * dom_pr
        return math.log1p(blended * 100)

    def reload_indices(self):
        self.db = Database()
        self.pageranks = self.db.get_all_pageranks()
        self.index_reader.reload()
        self.image_index_reader.reload()
        self.ranker = BM25Ranker(self.index_reader)
        self.image_ranker = BM25Ranker(
            self.image_index_reader,
            weights=_IMAGE_RANKER_WEIGHTS,
            b_map=_IMAGE_RANKER_B,
        )
        self._build_domain_authority()

    # ── Document search ────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> list:
        intent = self.query_understanding.detect_intent(query)
        strict_phrases_raw, _ = parse_query(query)
        query_terms = self.query_processor.process(query)
        if not query_terms:
            return []

        candidates = self.retriever.retrieve(query_terms)
        if not candidates:
            return []

        strict_phrases = [
            self.query_processor.process(p)
            for p in strict_phrases_raw
            if self.query_processor.process(p)
        ]

        if strict_phrases:
            candidates = self._filter_by_phrases(
                candidates, strict_phrases,
                ["heading", "title", "content", "url", "author"]
            )
        if not candidates:
            return []

        component_scores = self.ranker.score(
            query_terms, candidates, strict_phrases=strict_phrases
        )
        if not component_scores:
            return []

        doc_ids = [int(d) for d in component_scores]
        rows = self.db.get_documents_by_ids_with_crawled_at(doc_ids)
        doc_meta = {row[0]: row for row in rows}

        bm25f_raw = {d: v[0] for d, v in component_scores.items()}
        pp_raw = {d: v[1] for d, v in component_scores.items()}

        # Blended doc + domain authority
        authority_raw = {
            d: self._doc_authority(int(d), doc_meta.get(int(d), [None, None, ""])[2] or "")
            for d in component_scores
        }

        freshness_scores = {}
        url_match_scores = {}
        for d, row in doc_meta.items():
            crawled_at = row[8]
            freshness_scores[str(d)] = _freshness(crawled_at)

            doc_url = row[2]
            parsed = urlparse(doc_url)
            url_text = f"{parsed.netloc} {parsed.path}"
            url_tokens = set(self.query_processor.process(url_text))
            matched = len(set(query_terms) & url_tokens)
            url_match_scores[str(d)] = matched / len(query_terms) if query_terms else 0.0

        bm25f_n = _normalize(bm25f_raw)
        pp_n = _normalize(pp_raw)
        auth_n = _normalize(authority_raw)

        w = DOC_SCORE_WEIGHTS
        final_scores = {}
        for d in component_scores:
            final_scores[d] = (
                w["bm25f"] * bm25f_n.get(d, 0.0)
                + w["phrase_prox"] * pp_n.get(d, 0.0)
                + w["authority"] * auth_n.get(d, 0.0)
                + w["freshness"] * freshness_scores.get(str(d), 0.5)
                + w["url_match"] * url_match_scores.get(str(d), 0.0)
            )

        # Apply intent boosts
        doc_type_pref = intent.get("doc_type_preference")
        domain_boost = intent.get("domain_boost")
        if doc_type_pref or domain_boost:
            for d, row in doc_meta.items():
                key = str(d)
                if key not in final_scores:
                    continue
                doc_type = row[5]
                doc_url = row[2]
                if doc_type_pref and doc_type == doc_type_pref:
                    final_scores[key] *= 1.5  # boosted from 1.3
                if domain_boost and domain_boost in doc_url:
                    final_scores[key] *= 1.5

        sorted_docs = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        score_lookup = {int(d): s for d, s in sorted_docs}
        for doc_id in [int(d) for d, _ in sorted_docs]:
            row = doc_meta.get(doc_id)
            if not row:
                continue
            content = row[3]
            snippet = self.snippet_generator.generate(content, query, query_terms)
            results.append({
                "doc_id": row[0],
                "title": row[1],
                "url": row[2],
                "domain": _extract_domain(row[2]),
                "score": score_lookup.get(doc_id, 0.0),
                "snippet": snippet,
                "author": row[4],
                "doc_type": row[5],
                "html_file": row[6],
            })

        # Diversify: cap per-domain at 3 for HTML, uncapped for PDF (rare)
        html_results = _diversify(
            [r for r in results if r.get("doc_type", "HTML") == "HTML"],
            max_per_domain=3,
        )
        pdf_results = [r for r in results if r.get("doc_type") == "PDF"]

        # Re-merge: preserve relative score order across both types
        combined = sorted(html_results + pdf_results, key=lambda r: r["score"], reverse=True)
        return combined[:limit]

    # ── Image search ───────────────────────────────────────────────────────────

    def search_images(self, query: str, limit: int = 20) -> list:
        strict_phrases_raw, _ = parse_query(query)
        query_terms = self.query_processor.process(query)
        if not query_terms:
            return []

        candidates = self.image_retriever.retrieve(query_terms)
        if not candidates:
            return []

        strict_phrases = [
            self.query_processor.process(p)
            for p in strict_phrases_raw
            if self.query_processor.process(p)
        ]

        if strict_phrases:
            candidates = self._filter_by_phrases(
                candidates, strict_phrases,
                ["alt_text", "surrounding_text", "page_title", "image_url", "filename"]
            )
        if not candidates:
            return []

        component_scores = self.image_ranker.score(
            query_terms, candidates, strict_phrases=strict_phrases
        )
        if not component_scores:
            return []

        bm25f_raw = {d: v[0] for d, v in component_scores.items()}
        pp_raw = {d: v[1] for d, v in component_scores.items()}
        bm25f_n = _normalize(bm25f_raw)
        pp_n = _normalize(pp_raw)

        sorted_imgs = sorted(component_scores.keys(),
                             key=lambda d: bm25f_n.get(d, 0.0), reverse=True)[:limit * 3]
        img_ids = [int(i) for i in sorted_imgs]
        if not img_ids:
            return []

        placeholders = ",".join("?" for _ in img_ids)
        img_query = f"""
        SELECT id, page_url, image_url, alt_text, surrounding_text, page_title,
               width, height, local_path
        FROM images WHERE id IN ({placeholders})
        """
        with self.db.lock:
            self.db.cursor.execute(img_query, tuple(img_ids))
            rows = self.db.cursor.fetchall()

        # Build authority score per image using page_url domain
        img_rows_by_id = {row[0]: row for row in rows}

        w = IMG_SCORE_WEIGHTS
        final_scores = {}
        for d in sorted_imgs:
            img_id = int(d)
            row = img_rows_by_id.get(img_id)
            page_url = row[1] if row else ""
            dom_auth = self.domain_authority.get(_extract_domain(page_url), 0.0)
            # Normalise domain authority to [0,1] roughly via log scale
            auth_score = math.log1p(dom_auth * 100) / math.log1p(100)

            score = (
                w["bm25f"] * bm25f_n.get(d, 0.0)
                + w["phrase_prox"] * pp_n.get(d, 0.0)
                + w["authority"] * auth_score
            )

            # Penalise icons / favicons / sprites
            img_url = row[2] if row else ""
            if _ICON_PATTERNS.search(img_url):
                score *= 0.4

            final_scores[img_id] = score

        results = []
        for img_id, score in sorted(final_scores.items(), key=lambda x: x[1], reverse=True):
            row = img_rows_by_id.get(img_id)
            if not row:
                continue
            results.append({
                "image_id": img_id,
                "page_url": row[1],
                "image_url": row[2],
                "alt_text": row[3],
                "surrounding_text": row[4],
                "page_title": row[5],
                "width": row[6],
                "height": row[7],
                "local_path": row[8],
                "domain": _extract_domain(row[1]),
                "score": score,
            })

        return results[:limit]

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _filter_by_phrases(self, candidates: dict, strict_phrases: list, fields: list) -> dict:
        filtered = {}
        for doc_id, info in candidates.items():
            ok = True
            for phrase_terms in strict_phrases:
                found = False
                for field in fields:
                    fp = {t: info["positions"].get(t, {}).get(field, []) for t in phrase_terms}
                    if check_phrase_in_field(phrase_terms, fp):
                        found = True
                        break
                if not found:
                    ok = False
                    break
            if ok:
                filtered[doc_id] = info
        return filtered
