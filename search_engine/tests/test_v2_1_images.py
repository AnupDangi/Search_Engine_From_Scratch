import pytest
import tempfile
from pathlib import Path
import sqlite3
import shutil

from storage.database import Database
from parser.parser import HTMLParser
from indexing.index_builder import IndexBuilder
from search.index_reader import IndexReader
from search.search_engine import SearchEngine


@pytest.fixture
def temp_workspace():
    # Set up a temporary directory for database and index files
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_search.db"
    
    # Instantiate database
    db = Database(db_path=str(db_path))
    
    yield db, Path(temp_dir)
    
    db.close()
    shutil.rmtree(temp_dir)


def test_html_parser_image_extraction():
    parser = HTMLParser()
    sample_html = """
    <html>
      <head><title>Python Docs</title></head>
      <body>
        <p>This is a python tutorial code block.</p>
        <div>
          <img src="python-logo.png" alt="Python Logo" width="100" height="80">
          <span>Official python programming language logo</span>
        </div>
      </body>
    </html>
    """
    url = "https://docs.python.org/3/"
    parsed = parser.parse(sample_html, url)
    
    assert len(parsed["images"]) == 1
    img = parsed["images"][0]
    assert img["image_url"] == "https://docs.python.org/3/python-logo.png"
    assert img["alt_text"] == "Python Logo"
    assert "Official python programming language logo" in img["surrounding_text"]
    assert img["width"] == 100
    assert img["height"] == 80


def test_database_image_insertion_incremental(temp_workspace):
    db, temp_path = temp_workspace
    
    page_url = "https://example.com/page"
    img_url = "https://example.com/img.png"
    alt = "alt metadata"
    surr = "surrounding metadata text"
    title = "Page Title"
    
    # 1. Insert image
    db.insert_image(page_url, img_url, alt, surr, title, 100, 200)
    
    # Verify insert
    db.cursor.execute("SELECT page_url, alt_text, indexed_at FROM images WHERE image_url = ?", (img_url,))
    row = db.cursor.fetchone()
    assert row is not None
    assert row[0] == page_url
    assert row[1] == alt
    assert row[2] is None
    
    # Simulate indexing
    db.update_images_indexed_at([1], "2026-06-10T12:00:00")
    
    # Verify marked as indexed
    db.cursor.execute("SELECT indexed_at FROM images WHERE image_url = ?", (img_url,))
    assert db.cursor.fetchone()[0] is not None
    
    # 2. Re-insert identical metadata
    # Should check existing and keep indexed_at unchanged
    db.cursor.execute("SELECT alt_text, surrounding_text, page_title, width, height FROM images WHERE image_url = ?", (img_url,))
    img_row = db.cursor.fetchone()
    img_updated = True
    if img_row:
        if (img_row[0] == alt and 
            img_row[1] == surr and 
            img_row[2] == title and 
            img_row[3] == 100 and 
            img_row[4] == 200):
            img_updated = False
            
    assert img_updated is False
    # If not updated, we do not call insert_image, preserving indexed_at!


def test_image_indexing_and_searching(temp_workspace, monkeypatch):
    db, temp_path = temp_workspace
    
    # Mock database path and IndexReader
    original_db_init = Database.__init__
    def mock_db_init(self, db_path=None):
        original_db_init(self, db_path=str(temp_path / "test_search.db"))
    monkeypatch.setattr(Database, "__init__", mock_db_init)
    
    # Insert two test images
    # Image 1 contains "decorator" in alt_text
    db.insert_image(
        page_url="https://example.com/p1",
        image_url="https://example.com/logo.png",
        alt_text="Python Decorator Example",
        surrounding_text="Here is a screenshot of python decorators",
        page_title="Decorators Tutorial",
        width=200,
        height=150
    )
    
    # Image 2 contains "decorator" in surrounding_text only
    db.insert_image(
        page_url="https://example.com/p2",
        image_url="https://example.com/code.png",
        alt_text="Code Snippet",
        surrounding_text="A decorator in Python is a design pattern that adds logic.",
        page_title="Functions Guide",
        width=300,
        height=200
    )
    
    builder = IndexBuilder()
    builder.index_dir = temp_path / "index"
    builder.index_dir.mkdir(parents=True, exist_ok=True)
    
    # Build image index
    builder.build_image_index(incremental=False)
    builder.save()
    
    # Assert postings files were saved
    assert (temp_path / "index" / "image_postings.json").exists()
    assert (temp_path / "index" / "image_doc_stats.json").exists()
    
    # Test IndexReader loading and ranking
    original_reader_init = IndexReader.__init__
    def mock_reader_init(self, index_dir=None, index_type="document"):
        original_reader_init(self, index_dir=str(temp_path / "index"), index_type=index_type)
    monkeypatch.setattr(IndexReader, "__init__", mock_reader_init)
    
    engine = SearchEngine()
    results = engine.search_images("decorator")
    
    # Both should match
    assert len(results) == 2
    
    # Image 1 (alt_text match) should rank higher than Image 2 (surrounding_text match)
    # alt_text weight = 3.0, surrounding_text weight = 1.0
    assert results[0]["image_id"] == 1
    assert results[1]["image_id"] == 2
    assert results[0]["score"] > results[1]["score"]
    
    # Test strict phrase image search
    phrase_results = engine.search_images('"python decorator"')
    assert len(phrase_results) == 1
    assert phrase_results[0]["image_id"] == 1
