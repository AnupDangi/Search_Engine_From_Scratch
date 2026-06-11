# tools/generate_mock_website.py

import os
from pathlib import Path
import shutil
import pypdf
from pypdf import PdfWriter
from pypdf.generic import NameObject, DecodedStreamObject, DictionaryObject

def generate_mock_site():
    workspace_root = Path(__file__).resolve().parents[2]
    site_dir = workspace_root / "mock_website"
    site_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating mock website at: {site_dir}")
    
    # 1. Create index.html
    index_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>MiniSearch Unified Search Engine Testbed</title>
</head>
<body style="font-family: sans-serif; padding: 20px; background-color: #fafafa; color: #333;">
    <h1 style="color: #1a73e8;">MiniSearch Engine Testbed (V2)</h1>
    <p>This is the landing page for testing the Python crawler and multi-format indexing pipeline. The system supports full-text search with positional index constraints.</p>
    <p>We are building a Unified Retrieval Platform to support indexing of multiple formats including HTML, images, and PDF documents. This allows users to find text and search by attributes like author and file type.</p>
    
    <h2>Interactive Image Search Target</h2>
    <p>Below is the logo for our search engine test. It features a Python programming snake symbol coupled with artificial intelligence connections.</p>
    <img src="python-logo.png" alt="Python and Artificial Intelligence tech logo" width="300" height="300">
    
    <h2>Documentation Downloads</h2>
    <p>You can view our detailed setup documentation in the following formats:</p>
    <ul>
        <li><a href="about.html">About Page (HTML version)</a></li>
        <li><a href="document.pdf">Unified Search V2 Guide (PDF version)</a></li>
    </ul>
</body>
</html>
"""
    with open(site_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
        
    # 2. Create about.html
    about_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>About MiniSearch Engine v2</title>
</head>
<body style="font-family: sans-serif; padding: 20px; background-color: #fafafa; color: #333;">
    <h1 style="color: #1a73e8;">About the Search Engine Architecture</h1>
    <p>The Unified Retrieval Platform utilizes a BM25F ranking scoring model. BM25F is a variation of BM25 that allows weights to be assigned to different fields such as title, content, and URL components.</p>
    <p>To improve search relevance, the engine uses query term coverage boosting and strict phrase matching. In order to match a phrase, the engine verifies that terms appear adjacent to each other in the index by checking their relative positions.</p>
    <p>We also index images and PDFs incrementally. If a document's SHA-256 content hash has not changed, we skip the index rebuild, conserving computational resources.</p>
    <p>We also support video and audio indexing. By using Whisper and Vision-Language models (VLMs), we transcribe media content and generate visual descriptions of keyframes.</p>
</body>
</html>
"""
    with open(site_dir / "about.html", "w", encoding="utf-8") as f:
        f.write(about_html)

    # 3. Copy visual logo png
    # Path of generated image from model response
    generated_img_path = Path("/Users/anupdangi/.gemini/antigravity-ide/brain/9b28e384-fef6-4f01-be4c-423d2a628987/python_logo_1781094882618.png")
    dest_logo_path = site_dir / "python-logo.png"
    
    if generated_img_path.exists():
        shutil.copy(generated_img_path, dest_logo_path)
        print("Premium logo PNG copied to mock website.")
    else:
        # Fallback to a minimal 1x1 transparent PNG if file doesn't exist
        fallback_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        with open(dest_logo_path, "wb") as f:
            f.write(fallback_png)
        print("Fallback minimal PNG written to mock website.")

    # 4. Create document.pdf
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    
    # Setup fonts
    font_dict = DictionaryObject()
    f1_dict = DictionaryObject()
    f1_dict.update({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica")
    })
    font_dict.update({NameObject("/F1"): f1_dict})
    
    resources = DictionaryObject()
    resources.update({NameObject("/Font"): font_dict})
    page[NameObject("/Resources")] = resources
    
    # Write search-engine related text
    text_content = (
        "This document provides search engine v2 installation guidelines. "
        "Author: John Doe. Subject: retrieval optimization. "
        "We are indexing this PDF file to test the Unified Retrieval Platform."
    )
    text_stream_content = f"BT\n/F1 12 Tf\n50 700 Td\n({text_content}) Tj\nET"
    
    stream_obj = DecodedStreamObject()
    stream_obj.set_data(text_stream_content.encode("ascii"))
    page[NameObject("/Contents")] = stream_obj
    
    # Metadata attributes
    writer.add_metadata({
        "/Author": "John Doe",
        "/Title": "Unified Search V2 Guide"
    })
    
    with open(site_dir / "document.pdf", "wb") as f:
        writer.write(f)
    print("PDF document.pdf created on mock website.")
    print("Mock website generation completed successfully.")

if __name__ == "__main__":
    generate_mock_site()
