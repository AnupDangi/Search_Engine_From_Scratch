import pytest
import tempfile
from pathlib import Path
import sqlite3
import shutil

from storage.database import Database
from indexing.index_builder import IndexBuilder
from search.index_reader import IndexReader
from search.retriever import Retriever
from search.bm25_ranker import BM25Ranker
from search.search_engine import SearchEngine, parse_query, check_phrase_in_field


@pytest.fixture
def temp_workspace():
    # Set up a temporary directory for database and index files
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_search.db"
    
    # Instantiate database and verify initialization
    db = Database(db_path=str(db_path))
    
    yield db, Path(temp_dir)
    
    db.close()
    shutil.rmtree(temp_dir)


def test_database_and_incremental_flow(temp_workspace):
    db, temp_path = temp_workspace
    
    # 1. Insert first document
    url1 = "https://example.com/page1"
    title1 = "Asyncio Event Loop"
    content1 = "The asyncio event loop is running fast. It processes tasks concurrently."
    html_file1 = "1.html"
    hash1 = "hash_abc_123"
    
    db.insert_document(url1, title1, content1, html_file1, hash1)
    
    # Check if doc exists and has NULL indexed_at
    db.cursor.execute("SELECT content_hash, indexed_at, id FROM documents WHERE url = ?", (url1,))
    row = db.cursor.fetchone()
    assert row is not None
    assert row[0] == hash1
    assert row[1] is None
    doc_id = row[2]
    
    # 2. Try inserting document with identical content hash
    db.insert_document(url1, title1, content1, html_file1, hash1)
    
    # Let's mock indexing
    docs_to_index = db.get_docs_to_index()
    assert len(docs_to_index) == 1
    assert docs_to_index[0][0] == doc_id
    
    # Mark it indexed
    db.update_docs_indexed_at([doc_id], "2026-06-10T12:00:00")
    
    # Verify it is no longer returned in get_docs_to_index
    assert len(db.get_docs_to_index()) == 0
    
    # 3. Insert again with a DIFFERENT hash (content change)
    new_hash = "hash_xyz_999"
    db.insert_document(url1, title1, "Updated content for asyncio event loop.", html_file1, new_hash)
    
    # Should now be dirty again
    dirty = db.get_docs_to_index()
    assert len(dirty) == 1
    assert dirty[0][0] == doc_id
    
    # DB count check
    assert db.count_documents() == 1


def test_positional_indexing_and_bm25f(temp_workspace, monkeypatch):
    db, temp_path = temp_workspace
    
    # Mock database path in Database and IndexReader without recursion
    original_db_init = Database.__init__
    def mock_db_init(self, db_path=None):
        original_db_init(self, db_path=str(temp_path / "test_search.db"))
    monkeypatch.setattr(Database, "__init__", mock_db_init)
    
    # Insert two test documents
    # Doc 1 has "asyncio" in the title
    db.insert_document(
        url="https://example.com/asyncio-doc",
        title="Asyncio Event Loop",
        content="This page explains the event loop in Python, which is part of asyncio.",
        html_file="1.html",
        content_hash="hash1"
    )
    
    # Doc 2 has "asyncio" in the content body only
    db.insert_document(
        url="https://example.com/python-doc",
        title="Python Programming Guide",
        content="Python is a clean programming language. We can use asyncio for asynchronous tasks.",
        html_file="2.html",
        content_hash="hash2"
    )
    
    builder = IndexBuilder()
    builder.index_dir = temp_path / "index"
    builder.index_dir.mkdir(parents=True, exist_ok=True)
    
    # Build full index
    builder.build(incremental=False)
    builder.save()
    
    # Load postings and verify positions structure
    assert "asyncio" in builder.postings
    
    # Both docs should match
    doc_ids = list(builder.postings["asyncio"].keys())
    assert len(doc_ids) == 2
    
    # For Doc 1 (id = 1), "asyncio" is in title and content
    # For Doc 2 (id = 2), "asyncio" is in content only
    doc1_postings = builder.postings["asyncio"]["1"]
    doc2_postings = builder.postings["asyncio"]["2"]
    
    assert "title" in doc1_postings
    assert "content" in doc1_postings
    assert "title" not in doc2_postings
    assert "content" in doc2_postings
    
    # Test IndexReader and BM25F ranking weights
    original_reader_init = IndexReader.__init__
    def mock_reader_init(self, index_dir=None, index_type="document"):
        original_reader_init(self, index_dir=str(temp_path / "index"), index_type=index_type)
    monkeypatch.setattr(IndexReader, "__init__", mock_reader_init)
    
    engine = SearchEngine()
    results = engine.search("asyncio")
    
    assert len(results) == 2
    # Title match (Doc 1) should rank higher than content match (Doc 2) due to title field weight = 3.0 vs content = 1.0
    assert results[0]["doc_id"] == 1
    assert results[1]["doc_id"] == 2
    assert results[0]["score"] > results[1]["score"]


def test_phrase_query_parser():
    # Quoted phrase extraction
    phrases, terms = parse_query('asyncio "event loop" python "fast code"')
    assert phrases == ["event loop", "fast code"]
    assert terms == ["asyncio", "python"]
    
    # No phrases
    phrases, terms = parse_query("asyncio event loop")
    assert phrases == []
    assert terms == ["asyncio", "event", "loop"]
    
    # Only phrases
    phrases, terms = parse_query('"asyncio event loop"')
    assert phrases == ["asyncio event loop"]
    assert terms == []


def test_check_phrase_in_field():
    # term -> list of positions
    # Test match: phrase "event loop" (pos p and p+1)
    field_positions = {
        "event": [0, 15],
        "loop": [1, 42]
    }
    assert check_phrase_in_field(["event", "loop"], field_positions) is True
    
    # Test mismatch (not adjacent)
    field_positions = {
        "event": [0, 15],
        "loop": [5, 42]
    }
    assert check_phrase_in_field(["event", "loop"], field_positions) is False
    
    # Test mismatch (wrong order)
    field_positions = {
        "event": [1],
        "loop": [0]
    }
    assert check_phrase_in_field(["event", "loop"], field_positions) is False
    
    # Test multi-word phrase "asyncio event loop"
    field_positions = {
        "asyncio": [14],
        "event": [15, 30],
        "loop": [16, 40]
    }
    assert check_phrase_in_field(["asyncio", "event", "loop"], field_positions) is True


def test_search_engine_strict_phrase_filtering(temp_workspace, monkeypatch):
    db, temp_path = temp_workspace
    
    # Mock database path and IndexReader
    original_db_init = Database.__init__
    def mock_db_init(self, db_path=None):
        original_db_init(self, db_path=str(temp_path / "test_search.db"))
    monkeypatch.setattr(Database, "__init__", mock_db_init)
    
    original_reader_init = IndexReader.__init__
    def mock_reader_init(self, index_dir=None, index_type="document"):
        original_reader_init(self, index_dir=str(temp_path / "index"), index_type=index_type)
    monkeypatch.setattr(IndexReader, "__init__", mock_reader_init)
    
    # Doc 1 contains the exact phrase "event loop"
    db.insert_document(
        url="https://example.com/doc1",
        title="Python Guide",
        content="The event loop is running fine inside asyncio.",
        html_file="1.html",
        content_hash="hash1"
    )
    
    # Doc 2 contains the words but NOT as a phrase
    db.insert_document(
        url="https://example.com/doc2",
        title="Event Guide",
        content="This event is different and we should loop through python collections.",
        html_file="2.html",
        content_hash="hash2"
    )
    
    builder = IndexBuilder()
    builder.index_dir = temp_path / "index"
    builder.index_dir.mkdir(parents=True, exist_ok=True)
    builder.build(incremental=False)
    builder.save()
    
    engine = SearchEngine()
    
    # 1. Unquoted search should return both
    results = engine.search("event loop")
    assert len(results) == 2
    
    # 2. Quoted search should return ONLY Doc 1
    quoted_results = engine.search('"event loop"')
    assert len(quoted_results) == 1
    assert quoted_results[0]["doc_id"] == 1
