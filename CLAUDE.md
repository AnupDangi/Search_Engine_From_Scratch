# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from the `search_engine/` directory unless noted.

```bash
# Install dependencies
pip install -r search_engine/requirements.txt

# Run the API server (from search_engine/)
cd search_engine && uvicorn api.app:app --reload

# Run the full pipeline (clean + crawl + index) against mock_website/ — run from repo root
python search_engine/tools/run_pipeline.py

# Run crawler manually (from search_engine/)
python crawler/run_crawler.py

# Process crawled documents into DB
python process_documents.py

# Calculate PageRank from crawled links
python -c "from search.pagerank import PageRankCalculator; p=PageRankCalculator(); p.calculate_and_save()"

# Build search index
python -c "from indexing.index_builder import IndexBuilder; b=IndexBuilder(); b.build(); b.save(); b.close()"

# Run all tests (from search_engine/)
cd search_engine && python -m pytest tests/

# Run a single test file
cd search_engine && python -m pytest tests/test_v2_0_core.py -v

# Run a single test
cd search_engine && python -m pytest tests/test_v2_0_core.py::test_database_and_incremental_flow -v
```

**API endpoints:**

- `GET /search?q=asyncio&limit=10` — main search (web, PDFs, images)
- `GET /search/images?q=diagram&limit=10` — image-only search
- `GET /suggest?q=py` — query autocomplete from `query_logs`
- `GET /crawl?url=https://example.com&max_pages=100` — trigger synchronous crawl + index
- `GET /crawl?q=python+asyncio&max_pages=30` — discover seed URLs then crawl
- `GET /health` — liveness check
- `GET /` — built-in dark-themed search UI ("MINISEARCH V2.2")

## Architecture

### Pipeline (sequential stages)

```
WebCrawler → process_documents.py → PageRankCalculator → IndexBuilder → SearchEngine → FastAPI
```

1. **Crawler** (`crawler/`) — async (`aiohttp`) BFS crawler. Classifies URLs into HTML/PDF/IMAGE/VIDEO/AUDIO. Saves HTML to `data/raw_html/`, PDFs to `storage/pdfs/`, writes `data/raw_html/metadata.json` keyed by page_id. `run_pipeline.py` serves `mock_website/` on port 8000 via Python's built-in HTTP server for local testing.

2. **Document Processor** (`process_documents.py`) — reads `metadata.json`, processes HTML (via `parser/parser.py` + BeautifulSoup) and PDFs (via `pypdf`). Downloads images to `storage/images/` with SHA256 dedup. Inserts into SQLite with `content_hash` for change detection. Uses `ThreadPoolExecutor` for parallelism.

3. **PageRank** (`search/pagerank.py`) — iterative PageRank (damping=0.85) over the `links` table. Saves scores back to `documents.pagerank`. Must run after crawling, before indexing.

4. **Index Builder** (`indexing/index_builder.py`) — builds positional inverted index from SQLite. Outputs `data/index/postings.json`, `doc_stats.json`, `image_postings.json`, `image_doc_stats.json`. Supports incremental updates (only re-indexes docs with `indexed_at IS NULL`).

5. **Search Engine** (`search/search_engine.py`) — query pipeline:
   - `QueryUnderstanding` — detects doc_type preference (PDF/IMAGE) and domain boosts from query tokens
   - `QueryProcessor` — tokenize + Porter stem
   - `Retriever` — candidate lookup from `IndexReader`
   - `BM25Ranker` — BM25F with per-field weights
   - `SnippetGenerator` — extracts context window around matched terms

   Final doc score blends 5 components: `bm25f=0.50, phrase_prox=0.20, authority=0.15, freshness=0.10, url_match=0.05`. Double-quoted query terms trigger strict positional phrase filtering before scoring.

6. **API** (`api/app.py`) — FastAPI. `GET /search` uses `asyncio.to_thread` for both search calls. If no local results, schedules a background crawl (`_background_crawl`) that discovers seeds via Wikipedia → DuckDuckGo → Bing and re-indexes. Query responses are cached in `query_cache` table.

### Storage layout

| Path              | Purpose                                                                    |
| ----------------- | -------------------------------------------------------------------------- |
| `data/search.db`  | SQLite: `documents`, `images`, `links`, `query_logs`, `query_cache` tables |
| `data/raw_html/`  | Crawled HTML files + `metadata.json`                                       |
| `data/index/`     | JSON index files (postings, doc_stats, corpus_stats)                       |
| `storage/pdfs/`   | Downloaded PDF binaries                                                    |
| `storage/images/` | Downloaded image binaries (SHA256-named)                                   |

### Key design constraints

- **SQLite thread safety:** `Database` uses `RLock` on all writes. API handlers use `asyncio.to_thread` for every search call to avoid blocking the event loop. Thread-safety concern documented in commit `655c239`.
- **Working directory sensitivity:** Most paths are relative. Run API/scripts from `search_engine/` or the pipeline tool sets `sys.path` explicitly. `IndexReader` and `IndexBuilder` default to `data/index/` relative to CWD. `Database` defaults to `data/search.db` relative to CWD.
- **Incremental indexing:** `IndexBuilder.build(incremental=True)` (default) only processes documents where `indexed_at IS NULL`. Full rebuild: `incremental=False`.
- **Image dedup:** Images are deduplicated by SHA256 hash before download; skips files < 2KB and common icon/badge URLs.
- **Schema migrations:** `Database.__init__` does live `ALTER TABLE` / `DROP TABLE` migrations on startup to handle schema evolution — no separate migration tool.

### V3 planned (not yet implemented)

Dense embeddings, hybrid BM25F + vector retrieval, cross-encoder re-ranking. Placeholders in `search/future_design_placeholders.py`.
