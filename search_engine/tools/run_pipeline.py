# tools/run_pipeline.py

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
import asyncio

# 1. Clean up old databases, raw data, and index states for clean verification
print("=== Cleaning previous crawler and index states ===")
workspace_root = Path(__file__).resolve().parents[2]
search_engine_dir = workspace_root / "search_engine"

paths_to_clean = [
    workspace_root / "data/search.db",
    workspace_root / "data/index",
    workspace_root / "data/raw_html",
    workspace_root / "storage/pdfs",
    workspace_root / "storage/images"
]

for path in paths_to_clean:
    if path.exists():
        if path.is_file():
            os.remove(path)
            print(f"Removed file: {path.name}")
        else:
            shutil.rmtree(path)
            print(f"Removed directory: {path.name}")
            
# Create raw_html folder
(workspace_root / "data/raw_html").mkdir(parents=True, exist_ok=True)

# Add search_engine to path so we can import modules properly
sys.path.insert(0, str(search_engine_dir))

from crawler.crawler import WebCrawler
import process_documents
from indexing.index_builder import IndexBuilder
from search.pagerank import PageRankCalculator

def run_pipeline():
    # 2. Start mock website local HTTP server as a background subprocess
    print("\n=== Starting local web server ===")
    mock_website_dir = workspace_root / "mock_website"
    
    server_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8001", "--bind", "127.0.0.1", "--directory", str(mock_website_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("Local HTTP server launched on http://127.0.0.1:8001/")
    time.sleep(1.5)  # Wait for socket to bind

    try:
        # 3. Run crawler pointing to local test bed
        print("\n=== Launching WebCrawler V3 (Async) ===")
        crawler = WebCrawler(seed_url="http://127.0.0.1:8001/", max_pages=10)
        asyncio.run(crawler.crawl())
        
        # 4. Process raw HTML and raw PDF documents
        print("\n=== Processing Extracted Documents ===")
        process_documents.process_documents()

        # 4b. Calculate PageRank
        print("\n=== Calculating PageRank ===")
        prc = PageRankCalculator()
        prc.calculate_and_save()
        
        # 5. Build positional BM25F index
        print("\n=== Building Search Indices ===")
        builder = IndexBuilder()
        builder.build(incremental=False)
        builder.save()
        builder.summary()
        builder.close()
        
        print("\n=== Pipeline Execution Completed Successfully ===")
        
    finally:
        # 6. Shut down mock web server
        print("\n=== Stopping local web server ===")
        server_process.terminate()
        server_process.wait()
        print("Local HTTP server stopped.")

if __name__ == "__main__":
    run_pipeline()
