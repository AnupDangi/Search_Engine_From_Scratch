import pytest
import tempfile
from pathlib import Path
import shutil
import pypdf

# Generate a small valid PDF using pypdf to test text extraction
from pypdf import PdfWriter

from storage.database import Database
from indexing.index_builder import IndexBuilder
from search.index_reader import IndexReader
from search.search_engine import SearchEngine


@pytest.fixture
def temp_workspace():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_search.db"
    db = Database(db_path=str(db_path))
    yield db, Path(temp_dir)
    db.close()
    shutil.rmtree(temp_dir)


def create_dummy_pdf(filepath: Path, text: str):
    # Helper to generate a basic PDF file with pypdf
    writer = PdfWriter()
    page = writer.add_blank_page(width=72 * 8.5, height=72 * 11)
    
    # We can write text content to the page or mock PdfReader text extraction directly.
    # To be extremely clean and write a real PDF file that pypdf can read:
    # A blank page has no text, so let's write text by creating annotations or just mocking PdfReader
    # page.extract_text() is what pypdf calls.
    # We can write text using a simple PDF string structure or mock it.
    # Actually, generating real text in PDF via pure python writer can be complex,
    # but we can write a simple valid PDF and mock `page.extract_text()` return value inside the test!
    # Let's save a dummy PDF file structure.
    with open(filepath, "wb") as f:
        writer.write(f)


def test_pdf_extraction_and_indexing(temp_workspace, monkeypatch):
    db, temp_path = temp_workspace
    
    # 1. Create a dummy PDF file
    pdf_dir = temp_path / "raw_pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = pdf_dir / "asyncio-notes.pdf"
    
    create_dummy_pdf(pdf_file, "This is a pdf about python asyncio event loops.")
    
    # 2. Mock pypdf.PdfReader to return test text (since our dummy PDF is blank/empty)
    class MockPage:
        def extract_text(self):
            return "This PDF document covers python asyncio event loops and concurrent programming."
            
    class MockPdfReader:
        def __init__(self, path):
            self.pages = [MockPage()]
            self.metadata = {"/Author": "Test Author", "/Title": "Asyncio Notes"}
            
    monkeypatch.setattr(pypdf, "PdfReader", MockPdfReader)
    
    # 3. Create metadata.json flagging this file as a PDF
    html_dir = temp_path / "raw_html"
    html_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "1": {
            "id": 1,
            "url": "https://example.com/asyncio-notes.pdf",
            "html_file": "asyncio-notes.pdf",
            "is_pdf": True
        }
    }
    import json
    with open(html_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f)
        
    # 4. Mock paths in process_documents
    import process_documents
    monkeypatch.setattr(process_documents, "RAW_HTML_DIR", html_dir)
    monkeypatch.setattr(process_documents, "STORAGE_PDF_DIR", pdf_dir)
    
    original_db_init = Database.__init__
    def mock_db_init(self, db_path=None):
        original_db_init(self, db_path=str(temp_path / "test_search.db"))
    monkeypatch.setattr(Database, "__init__", mock_db_init)
    
    monkeypatch.setattr(Database, "close", lambda self: None)
    
    # 5. Run process_documents
    process_documents.process_documents()
    
    # Verify PDF inserted in db
    db.cursor.execute("SELECT title, content, html_file FROM documents WHERE id = 1")
    row = db.cursor.fetchone()
    assert row is not None
    assert row[0] == "Asyncio Notes"
    assert "asyncio event loops" in row[1]
    assert row[2] == "asyncio-notes.pdf"
    
    # 6. Build index
    monkeypatch.setattr("indexing.index_builder.Database.__init__", mock_db_init)
    monkeypatch.setattr("search.search_engine.Database.__init__", mock_db_init)
    
    builder = IndexBuilder()
    builder.index_dir = temp_path / "index"
    builder.index_dir.mkdir(parents=True, exist_ok=True)
    builder.build(incremental=False)
    builder.save()
    
    # Verify indexed
    assert "asyncio" in builder.postings
    
    # 7. Search pointing to this index
    original_reader_init = IndexReader.__init__
    def mock_reader_init(self, index_dir=None, index_type="document"):
        original_reader_init(self, index_dir=str(temp_path / "index"), index_type=index_type)
    monkeypatch.setattr(IndexReader, "__init__", mock_reader_init)
    
    engine = SearchEngine()
    results = engine.search("concurrent")
    
    assert len(results) == 1
    assert results[0]["doc_id"] == 1
    assert results[0]["title"] == "Asyncio Notes"
    assert "asyncio event loops" in results[0]["snippet"]


def test_cdn_hash_filename_filtered():
    """CDN hash filenames and Sanity CDN paths should match _ICON_PATTERNS; descriptive names should not."""
    from search.search_engine import _ICON_PATTERNS
    assert _ICON_PATTERNS.search("ce798d3e23245678901234abcdef") is not None, \
        "CDN hash should match ICON_PATTERNS"
    assert _ICON_PATTERNS.search("cdn.sanity.io/images/abc123") is not None, \
        "Sanity CDN path should match ICON_PATTERNS"
    assert _ICON_PATTERNS.search("python-logo.png") is None, \
        "python-logo.png should NOT match ICON_PATTERNS"
