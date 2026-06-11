# api/app.py

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import asyncio
import json

from search.search_engine import SearchEngine

app = FastAPI(
    title="Unified Retrieval Platform V2",
    version="2.0.0"
)

# Resolve storage path: api/app.py is in search_engine/api/, so parents[1] = search_engine/
base_dir = Path(__file__).resolve().parents[1]
storage_dir = base_dir / "storage"
storage_dir.mkdir(parents=True, exist_ok=True)
(storage_dir / "images").mkdir(parents=True, exist_ok=True)
(storage_dir / "pdfs").mkdir(parents=True, exist_ok=True)

app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")

engine = SearchEngine()


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


async def _discover_seed_urls(query: str, max_seeds: int = 8) -> list:
    """Discover seed URLs from a text query via Wikipedia + DuckDuckGo."""
    import requests
    from bs4 import BeautifulSoup
    import urllib.parse

    seed_urls = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
    q_encoded = urllib.parse.quote(query)

    # Wikipedia REST API — fast, reliable
    try:
        wiki_api = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={q_encoded}&limit=5&format=json"
        wiki_resp = requests.get(wiki_api, headers=headers, timeout=5)
        wiki_data = wiki_resp.json()
        if len(wiki_data) >= 4:
            seed_urls.extend(u for u in wiki_data[3] if u and u.startswith("http"))
    except Exception as e:
        print(f"[SEEDS] Wikipedia failed: {e}")

    # DuckDuckGo HTML scrape
    if len(seed_urls) < max_seeds:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={q_encoded}"
            resp = requests.get(ddg_url, headers=headers, timeout=8)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__a", href=True):
                href = a["href"]
                if "uddg=" in href:
                    p = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(p.query)
                    if "uddg" in qs:
                        href = urllib.parse.unquote(qs["uddg"][0])
                if href.startswith("http") and href not in seed_urls:
                    seed_urls.append(href)
                if len(seed_urls) >= max_seeds:
                    break
        except Exception as e:
            print(f"[SEEDS] DuckDuckGo failed: {e}")

    # Bing fallback
    if len(seed_urls) < 3:
        try:
            bing_url = f"https://www.bing.com/search?q={q_encoded}"
            resp = requests.get(bing_url, headers=headers, timeout=8)
            soup = BeautifulSoup(resp.text, "html.parser")
            for li in soup.find_all("li", class_="b_algo"):
                a = li.find("a", href=True)
                if a and a["href"].startswith("http") and a["href"] not in seed_urls:
                    seed_urls.append(a["href"])
                if len(seed_urls) >= max_seeds:
                    break
        except Exception as e:
            print(f"[SEEDS] Bing failed: {e}")

    return list(dict.fromkeys(seed_urls))[:max_seeds]


async def _run_crawl_pipeline(seed_urls: list, max_pages: int, label: str = ""):
    """Shared crawl → process → pagerank → index → reload pipeline."""
    from crawler.crawler import WebCrawler
    import process_documents
    from indexing.index_builder import IndexBuilder
    from search.pagerank import PageRankCalculator

    print(f"[CRAWL{label}] Starting: {seed_urls} (max_pages={max_pages})")
    crawler = WebCrawler(seed_url=seed_urls, max_pages=max_pages,
                         restrict_domain=False, restrict_path=False)
    await crawler.crawl()
    await asyncio.to_thread(process_documents.process_documents)
    prc = PageRankCalculator()
    await asyncio.to_thread(prc.calculate_and_save)
    builder = IndexBuilder()
    await asyncio.to_thread(builder.build, True)
    await asyncio.to_thread(builder.save)
    await asyncio.to_thread(builder.close)
    await asyncio.to_thread(engine.reload_indices)
    print(f"[CRAWL{label}] Complete.")


async def _background_crawl(q: str):
    """Background task: discover seeds for query and crawl+index."""
    try:
        seed_urls = await _discover_seed_urls(q, max_seeds=8)
        if not seed_urls:
            print(f"[FALLBACK] No seed URLs found for '{q}'.")
            return
        await _run_crawl_pipeline(seed_urls, max_pages=30, label=" FALLBACK")
    except Exception as e:
        print(f"[FALLBACK ERROR] {e}")


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of results")
):
    # Check query cache first
    cached = await asyncio.to_thread(engine.db.get_cached_response, q)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # Retrieve documents and images
    doc_results = await asyncio.to_thread(engine.search, q, limit)
    img_results = await asyncio.to_thread(engine.search_images, q, limit)

    # If no local results, schedule background crawl and return immediately
    if not doc_results and not img_results:
        asyncio.create_task(_background_crawl(q))
        response = {
            "query": q,
            "web": [],
            "pdfs": [],
            "images": [],
            "fallback_scheduled": True,
            "retry_after": 10,
        }
        await asyncio.to_thread(engine.db.log_query, q, 0)
        return response

    # Group documents by doc_type
    web_results = [d for d in doc_results if d.get("doc_type", "HTML") == "HTML"]
    pdf_results = [d for d in doc_results if d.get("doc_type") == "PDF"]

    response = {
        "query": q,
        "web": web_results,
        "pdfs": pdf_results,
        "images": img_results,
        "fallback_scheduled": False,
    }

    # Log query and cache response
    total = len(web_results) + len(pdf_results) + len(img_results)
    await asyncio.to_thread(engine.db.log_query, q, total)
    await asyncio.to_thread(engine.db.set_cached_response, q, json.dumps(response))

    return response


@app.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=1, description="Query prefix for suggestions")
):
    suggestions = await asyncio.to_thread(engine.db.get_suggestions, q)
    return {"suggestions": suggestions}


@app.get("/search/images")
def search_images(
    q: str = Query(
        ...,
        min_length=1,
        description="Image search query"
    ),
    limit: int = Query(
        10,
        ge=1,
        le=20,
        description="Maximum number of results"
    )
):
    results = engine.search_images(
        q,
        limit=limit
    )
    return {
        "query": q,
        "count": len(results),
        "results": results
    }


@app.get("/crawl")
async def crawl_website(
    url: str = Query(None, description="Direct URL to crawl"),
    q: str = Query(None, description="Search query — auto-discovers seed URLs"),
    max_pages: int = Query(100, ge=1, le=200, description="Max pages to crawl")
):
    import urllib.parse as _urlparse

    try:
        raw = url or q
        if not raw:
            return {"status": "error", "message": "Provide url= or q= parameter."}

        # Determine if input is a URL or a plain query
        seed_urls = []
        _parsed = _urlparse.urlparse(raw)
        if _parsed.scheme in ("http", "https") and _parsed.netloc:
            # Direct URL
            seed_urls = [raw]
            label = raw
        else:
            # Plain query or bare domain — discover seeds
            # Try bare domain first
            if " " not in raw and "." in raw:
                candidate = f"https://{raw}"
                _p2 = _urlparse.urlparse(candidate)
                if _p2.netloc:
                    seed_urls = [candidate]
                    label = candidate
            if not seed_urls:
                # Full query-based discovery
                seed_urls = await _discover_seed_urls(raw, max_seeds=8)
                label = f"query '{raw}'"

        if not seed_urls:
            return {"status": "error", "message": f"Could not find seed URLs for '{raw}'."}

        await _run_crawl_pipeline(seed_urls, max_pages=max_pages, label=" CRAWL")

        return {
            "status": "success",
            "message": f"Crawled & indexed up to {max_pages} pages for {label}.",
            "seeds": seed_urls,
        }
    except Exception as e:
        return {"status": "error", "message": f"Crawl failed: {str(e)}"}


@app.get("/", response_class=HTMLResponse)
def index_ui():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title> MINISEARCH UI Unified Search Engine</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Grotesk:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #03001e;
            --surface: rgba(255, 255, 255, 0.03);
            --surface-hover: rgba(255, 255, 255, 0.07);
            --border: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(255, 255, 255, 0.15);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --primary: #8b5cf6;
            --primary-glow: rgba(139, 92, 246, 0.4);
            --accent: #06b6d4;
            --accent-glow: rgba(6, 182, 212, 0.4);
            --badge-html: #10b981;
            --badge-pdf: #f97316;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background: radial-gradient(circle at 50% 0%, #1e1145 0%, #030014 60%);
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }

        header {
            text-align: center;
            margin-bottom: 30px;
            width: 100%;
            max-width: 800px;
        }

        .logo-container {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            margin-bottom: 12px;
        }

        .logo-glow {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 3.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #a78bfa 0%, #06b6d4 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            filter: drop-shadow(0 0 15px var(--primary-glow));
            letter-spacing: -2px;
        }

        .version-badge {
            font-size: 0.8rem;
            padding: 3px 8px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid var(--border);
            border-radius: 20px;
            color: var(--accent);
            font-weight: 600;
            align-self: center;
            letter-spacing: 1px;
        }

        .tagline {
            font-size: 1.1rem;
            color: var(--text-secondary);
            font-weight: 300;
            letter-spacing: 0.5px;
        }

        .search-container {
            width: 100%;
            max-width: 800px;
            margin-bottom: 24px;
        }

        .search-box {
            position: relative;
            display: flex;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 6px 10px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(10px);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .search-box:focus-within {
            border-color: var(--primary);
            box-shadow: 0 0 25px var(--primary-glow);
            background: rgba(255, 255, 255, 0.05);
        }

        .search-input {
            width: 100%;
            background: transparent;
            border: none;
            outline: none;
            padding: 14px 20px;
            color: var(--text-primary);
            font-size: 1.2rem;
            font-family: inherit;
        }

        .search-input::placeholder {
            color: var(--text-muted);
        }

        .search-btn {
            background: linear-gradient(135deg, var(--primary) 0%, #7c3aed 100%);
            color: white;
            border: none;
            padding: 12px 28px;
            border-radius: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3);
        }

        .search-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(139, 92, 246, 0.5);
        }

        .search-btn:active {
            transform: translateY(1px);
        }

        .tabs-container {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
            width: 100%;
            max-width: 800px;
            justify-content: center;
        }

        .tab-btn {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 10px 20px;
            border-radius: 12px;
            font-size: 0.95rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .tab-btn:hover {
            background: var(--surface-hover);
            color: var(--text-primary);
            border-color: var(--border-hover);
        }

        .tab-btn.active {
            background: rgba(139, 92, 246, 0.15);
            border-color: var(--primary);
            color: var(--text-primary);
            box-shadow: 0 0 15px rgba(139, 92, 246, 0.2);
        }

        .stats-line {
            width: 100%;
            max-width: 800px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 16px;
            font-weight: 300;
            letter-spacing: 0.5px;
        }

        .results-container {
            width: 100%;
            max-width: 800px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .result-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }

        .result-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: transparent;
            transition: background 0.3s;
        }

        .result-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
            background: var(--surface-hover);
        }

        .result-card.html:hover::before {
            background: var(--badge-html);
        }

        .result-card.pdf:hover::before {
            background: var(--badge-pdf);
        }

        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 6px;
            gap: 15px;
        }

        .result-title-link {
            color: var(--text-primary);
            font-size: 1.3rem;
            font-weight: 600;
            text-decoration: none;
            transition: color 0.2s;
            font-family: 'Space Grotesk', sans-serif;
        }

        .result-title-link:hover {
            color: #c084fc;
        }

        .meta-badges {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .badge {
            font-size: 0.75rem;
            padding: 4px 10px;
            border-radius: 8px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }

        .badge.type-html {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge.type-pdf {
            background: rgba(249, 115, 22, 0.15);
            color: #fb923c;
            border: 1px solid rgba(249, 115, 22, 0.3);
        }

        .badge.score {
            background: rgba(6, 182, 212, 0.15);
            color: #22d3ee;
            border: 1px solid rgba(6, 182, 212, 0.3);
        }

        .result-domain-line {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85rem;
            color: var(--accent);
            margin-bottom: 12px;
        }

        .result-url-text {
            color: var(--text-muted);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 450px;
            text-decoration: none;
        }

        .result-url-text:hover {
            text-decoration: underline;
        }

        .result-snippet {
            font-size: 0.95rem;
            color: var(--text-secondary);
            line-height: 1.6;
        }

        .result-author {
            margin-top: 12px;
            font-size: 0.85rem;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        /* Inline Images Carousel on All tab */
        .inline-images-section {
            margin: 10px 0;
            padding: 20px;
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid var(--border);
            border-radius: 16px;
        }

        .inline-images-title {
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .inline-images-list {
            display: flex;
            gap: 15px;
            overflow-x: auto;
            padding-bottom: 10px;
        }

        .inline-images-list::-webkit-scrollbar {
            height: 6px;
        }

        .inline-images-list::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
        }

        .inline-image-item {
            flex: 0 0 160px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.3s;
        }

        .inline-image-item:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
        }

        .inline-image-thumb {
            width: 100%;
            height: 100px;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .inline-image-thumb img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }

        .inline-image-meta {
            padding: 8px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* Image Grid Layout */
        .images-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 20px;
            width: 100%;
            max-width: 800px;
        }

        .image-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.3s;
            backdrop-filter: blur(10px);
        }

        .image-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-4px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4);
        }

        .image-preview-container {
            width: 100%;
            height: 160px;
            background: #000;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            border-bottom: 1px solid var(--border);
            position: relative;
        }

        .image-preview {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            transition: transform 0.5s;
        }

        .image-card:hover .image-preview {
            transform: scale(1.05);
        }

        .image-content {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-grow: 1;
        }

        .image-title {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-primary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .image-alt {
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-style: italic;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 38px;
        }

        .image-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: auto;
            padding-top: 8px;
            border-top: 1px solid rgba(255,255,255,0.05);
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        mark {
            background: rgba(234, 179, 8, 0.25);
            color: #facc15;
            padding: 2px 4px;
            border-radius: 4px;
            font-weight: 600;
        }

        .loader {
            display: none;
            width: 50px;
            height: 50px;
            border: 3px solid rgba(139, 92, 246, 0.1);
            border-radius: 50%;
            border-top-color: var(--primary);
            animation: spin 1s ease-in-out infinite;
            margin: 40px auto;
        }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
            font-size: 1.1rem;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        @media (max-width: 600px) {
            .logo-glow {
                font-size: 2.5rem;
            }
            .search-input {
                padding: 10px;
                font-size: 1rem;
            }
            .search-btn {
                padding: 10px 18px;
            }
        }

        /* Pagination */
        .pagination-container {
            width: 100%;
            max-width: 800px;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px 0 10px;
            gap: 12px;
        }

        .pagination-label {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.6rem;
            font-weight: 800;
            letter-spacing: -1px;
        }

        .pagination-label span {
            color: var(--primary);
        }

        .pagination-pages {
            display: flex;
            gap: 4px;
            align-items: center;
            flex-wrap: wrap;
            justify-content: center;
        }

        .page-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 8px 14px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1rem;
            font-family: inherit;
            transition: all 0.2s;
            min-width: 42px;
            height: 42px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .page-btn:hover {
            background: var(--surface-hover);
            color: var(--text-primary);
        }

        .page-btn.active {
            color: var(--primary);
            font-weight: 700;
            border-bottom: 3px solid var(--primary);
            border-radius: 0;
        }

        .page-btn.arrow {
            font-size: 1.3rem;
            color: var(--primary);
        }

        .page-btn.arrow:hover {
            background: rgba(139, 92, 246, 0.1);
        }

        /* Collapsible crawl panel styling */
        .crawl-panel {
            width: 100%;
            max-width: 800px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 24px;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.3);
            transition: all 0.3s;
        }

        .crawl-panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            font-weight: 600;
            color: var(--text-primary);
            user-select: none;
            font-family: 'Space Grotesk', sans-serif;
        }

        .crawl-panel-body {
            margin-top: 15px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            overflow: hidden;
        }

        .crawl-input-group {
            display: flex;
            gap: 10px;
        }

        .crawl-url-input {
            flex-grow: 1;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 16px;
            color: var(--text-primary);
            font-family: inherit;
            outline: none;
        }

        .crawl-url-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 10px var(--accent-glow);
        }

        .crawl-pages-input {
            width: 80px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
            color: var(--text-primary);
            font-family: inherit;
            text-align: center;
            outline: none;
        }

        .crawl-submit-btn {
            background: linear-gradient(135deg, var(--accent) 0%, #0891b2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 4px 15px rgba(6, 182, 212, 0.3);
        }

        .crawl-submit-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(6, 182, 212, 0.5);
        }

        .crawl-status {
            font-size: 0.9rem;
            color: var(--text-secondary);
            padding: 12px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            display: none;
            line-height: 1.5;
        }
    </style>
</head>
<body>

    <header>
        <div class="logo-container">
            <h1 class="logo-glow">MINISEARCH</h1>
            <span class="version-badge">V2.2</span>
        </div>
        <p class="tagline">Unified Multi-Modal Retrieval Platform</p>
    </header>

    <div class="search-container">
        <div class="search-box">
            <input type="text" id="searchInput" class="search-input" placeholder="Search Python, asyncio, John Doe..." autocomplete="off">
            <button id="searchBtn" class="search-btn">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                Search
            </button>
        </div>
    </div>    <div class="crawl-panel">
        <div class="crawl-panel-header" onclick="toggleCrawlPanel()">
            <span style="display: flex; align-items: center; gap: 8px;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
                Index a Specific Website
            </span>
            <span id="crawlPanelArrow">▼</span>
        </div>
        <div class="crawl-panel-body" id="crawlPanelBody">
            <p style="font-size: 0.9rem; color: var(--text-secondary); line-height: 1.6;">
                🌐 <strong>Tip:</strong> Searching automatically finds and indexes pages from Wikipedia, DuckDuckGo, and Bing when results are not cached locally.<br>
                Use this panel only when you want to index a <em>specific website</em> by URL.
            </p>
            <div class="crawl-input-group">
                <input type="text" id="crawlUrlInput" class="crawl-url-input" placeholder="URL or query (e.g. 'python asyncio' or https://docs.python.org)" autocomplete="off">
                <input type="number" id="crawlPagesInput" class="crawl-pages-input" value="100" min="1" max="200" title="Max pages to crawl">
                <button id="crawlSubmitBtn" class="crawl-submit-btn" onclick="triggerDynamicCrawl()">Crawl &amp; Index</button>
            </div>
            <div class="crawl-status" id="crawlStatus"></div>
        </div>
    </div>

    <div class="tabs-container">
        <button class="tab-btn active" id="tab-all" onclick="switchTab('all')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
            All
        </button>
        <button class="tab-btn" id="tab-web" onclick="switchTab('web')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
            Web Pages
        </button>
        <button class="tab-btn" id="tab-images" onclick="switchTab('images')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
            Images
        </button>
        <button class="tab-btn" id="tab-pdfs" onclick="switchTab('pdfs')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
            PDFs
        </button>
    </div>

    <div class="stats-line" id="statsLine" style="display: none;"></div>
    <div class="loader" id="loader"></div>

    <div class="results-container" id="resultsContainer">
        <div class="empty-state">Enter a query to start searching.</div>
    </div>

    <script>
        let currentTab = 'all';
        let searchData = null; // Cache search responses
        let currentPage = 1;
        const RESULTS_PER_PAGE = 10;
        let crawlPanelOpen = true;

        function toggleCrawlPanel() {
            const body = document.getElementById('crawlPanelBody');
            const arrow = document.getElementById('crawlPanelArrow');
            crawlPanelOpen = !crawlPanelOpen;
            if (crawlPanelOpen) {
                body.style.display = 'flex';
                arrow.innerText = '▼';
            } else {
                body.style.display = 'none';
                arrow.innerText = '▲';
            }
        }

        async function triggerDynamicCrawl() {
            const urlInput = document.getElementById('crawlUrlInput');
            const pagesInput = document.getElementById('crawlPagesInput');
            const statusDiv = document.getElementById('crawlStatus');
            const submitBtn = document.getElementById('crawlSubmitBtn');

            const input = urlInput.value.trim();
            const maxPages = parseInt(pagesInput.value) || 100;

            if (!input) {
                statusDiv.style.display = 'block';
                statusDiv.style.color = '#f87171';
                statusDiv.innerHTML = '❌ Please enter a URL or search query.';
                return;
            }

            // Detect URL vs plain query
            let crawlEndpoint;
            let isUrl = false;
            try {
                const parsed = new URL(input);
                if (['http:', 'https:'].includes(parsed.protocol)) {
                    isUrl = true;
                }
            } catch (_) {}

            if (isUrl) {
                crawlEndpoint = `/crawl?url=${encodeURIComponent(input)}&max_pages=${maxPages}`;
            } else {
                crawlEndpoint = `/crawl?q=${encodeURIComponent(input)}&max_pages=${maxPages}`;
            }

            statusDiv.style.display = 'block';
            statusDiv.style.color = 'var(--text-secondary)';
            const label = isUrl ? `<b>${escapeHtml(input)}</b>` : `query "<b>${escapeHtml(input)}</b>"`;
            statusDiv.innerHTML = `⏳ Discovering seeds for ${label} and crawling (limit: ${maxPages} pages)... Please wait.`;
            submitBtn.disabled = true;
            submitBtn.style.opacity = '0.5';

            try {
                const response = await fetch(crawlEndpoint);
                const result = await response.json();

                if (result.status === 'success') {
                    statusDiv.style.color = '#34d399';
                    statusDiv.innerHTML = `✅ ${escapeHtml(result.message)}`;
                    urlInput.value = '';
                    if (searchInput.value.trim()) {
                        performSearch();
                    }
                } else {
                    statusDiv.style.color = '#f87171';
                    statusDiv.innerHTML = `❌ Crawl failed: ${escapeHtml(result.message)}`;
                }
            } catch (err) {
                statusDiv.style.color = '#f87171';
                statusDiv.innerHTML = `❌ Network error starting crawl.`;
            } finally {
                submitBtn.disabled = false;
                submitBtn.style.opacity = '1';
            }
        }
        const searchInput = document.getElementById('searchInput');
        const searchBtn = document.getElementById('searchBtn');
        const resultsContainer = document.getElementById('resultsContainer');
        const statsLine = document.getElementById('statsLine');
        const loader = document.getElementById('loader');

        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                triggerSearch();
            }
        });

        searchBtn.addEventListener('click', triggerSearch);

        function switchTab(tab) {
            currentTab = tab;
            currentPage = 1;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`tab-${tab}`).classList.add('active');
            if (searchData) {
                renderResults();
            } else if (searchInput.value.trim()) {
                performSearch();
            }
        }

        function triggerSearch() {
            searchData = null; // Reset cache on new query
            currentPage = 1;
            performSearch();
        }

        async function performSearch() {
            const query = searchInput.value.trim();
            if (!query) return;

            resultsContainer.innerHTML = '';
            statsLine.style.display = 'none';
            loader.style.display = 'block';
            loader.innerHTML = '<div style="color: var(--text-secondary); font-size:0.9rem; margin-top: 8px;">🔍 Searching local index...</div>';

            try {
                const response = await fetch(`/search?q=${encodeURIComponent(query)}&limit=100`);
                searchData = await response.json();

                loader.style.display = 'none';
                loader.innerHTML = '';

                // Show fallback banner if the web was crawled live
                if (searchData.fallback_triggered) {
                    const sources = (searchData.fallback_sources || []).map(s => `<a href="${s}" target="_blank" style="color:var(--accent);word-break:break-all;">${escapeHtml(s)}</a>`).join('<br>');
                    const banner = document.createElement('div');
                    banner.style.cssText = 'background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.25);border-radius:12px;padding:12px 16px;margin-bottom:16px;font-size:0.85rem;color:var(--text-secondary);line-height:1.6;';
                    banner.innerHTML = `🌐 <strong style="color:var(--accent)">Live web search triggered</strong> — no local results found. Crawled & indexed:<br>${sources || '(no URLs found)'}`;
                    resultsContainer.appendChild(banner);
                }

                renderResults();
            } catch (err) {
                loader.style.display = 'none';
                loader.innerHTML = '';
                resultsContainer.innerHTML = `<div class="empty-state" style="color: #ef4444;">Error retrieving results. Is the API server running?</div>`;
            }
        }

        function renderResults() {
            if (!searchData) return;

            const web = searchData.web || [];
            const pdfs = searchData.pdfs || [];
            const images = searchData.images || [];

            const totalResults = web.length + pdfs.length + images.length;
            if (totalResults === 0) {
                statsLine.style.display = 'none';
                resultsContainer.className = 'results-container';
                resultsContainer.innerHTML = `<div class="empty-state">No matching results found for "${escapeHtml(searchInput.value)}".</div>`;
                return;
            }

            // Display stats line
            statsLine.style.display = 'block';
            statsLine.innerHTML = `About ${web.length} web pages, ${pdfs.length} PDFs, and ${images.length} images found.`;

            if (currentTab === 'all') {
                // Build combined list: interleave web + pdfs, images shown inline
                const combined = [];
                const webSlice1 = web.slice(0, 3);
                const webRest = web.slice(3);
                combined.push(...webSlice1);
                combined.push(...pdfs);
                combined.push(...webRest);

                const totalPages = Math.ceil(combined.length / RESULTS_PER_PAGE);
                const page = Math.min(currentPage, totalPages || 1);
                const start = (page - 1) * RESULTS_PER_PAGE;
                const pageItems = combined.slice(start, start + RESULTS_PER_PAGE);

                resultsContainer.className = 'results-container';
                let html = '';

                // Show inline images block only on page 1
                if (page === 1 && images.length > 0) {
                    html += `
                        <div class="inline-images-section">
                            <div class="inline-images-title">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                                Images for ${escapeHtml(searchInput.value)}
                            </div>
                            <div class="inline-images-list">
                                ${images.slice(0, 5).map(img => {
                                    const imgScr = img.local_path ? `/${img.local_path}` : img.image_url;
                                    return `
                                        <div class="inline-image-item">
                                            <div class="inline-image-thumb">
                                                <img src="${escapeHtml(imgScr)}" alt="${escapeHtml(img.alt_text)}" onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=150';">
                                            </div>
                                            <div class="inline-image-meta" title="${escapeHtml(img.page_title)}">
                                                ${escapeHtml(img.page_title || 'Image')}
                                            </div>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        </div>
                    `;
                }

                html += pageItems.map(doc => renderDocCard(doc)).join('');
                resultsContainer.innerHTML = html;
                resultsContainer.appendChild(buildPagination(page, totalPages));

            } else if (currentTab === 'web') {
                resultsContainer.className = 'results-container';
                if (web.length === 0) {
                    resultsContainer.innerHTML = '<div class="empty-state">No web pages found.</div>';
                } else {
                    const totalPages = Math.ceil(web.length / RESULTS_PER_PAGE);
                    const page = Math.min(currentPage, totalPages);
                    const start = (page - 1) * RESULTS_PER_PAGE;
                    resultsContainer.innerHTML = web.slice(start, start + RESULTS_PER_PAGE).map(doc => renderDocCard(doc)).join('');
                    resultsContainer.appendChild(buildPagination(page, totalPages));
                }

            } else if (currentTab === 'images') {
                resultsContainer.className = 'images-grid';
                if (images.length === 0) {
                    resultsContainer.innerHTML = '<div class="empty-state">No images found.</div>';
                } else {
                    const totalPages = Math.ceil(images.length / RESULTS_PER_PAGE);
                    const page = Math.min(currentPage, totalPages);
                    const start = (page - 1) * RESULTS_PER_PAGE;
                    const pageImgs = images.slice(start, start + RESULTS_PER_PAGE);
                    resultsContainer.innerHTML = pageImgs.map(img => {
                        const imageSrc = img.local_path ? `/${img.local_path}` : img.image_url;
                        return `
                            <div class="image-card">
                                <div class="image-preview-container">
                                    <img src="${escapeHtml(imageSrc)}" class="image-preview" alt="${escapeHtml(img.alt_text)}" onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=400';">
                                </div>
                                <div class="image-content">
                                    <div class="image-title" title="${escapeHtml(img.page_title)}">${escapeHtml(img.page_title || 'Untitled Page')}</div>
                                    <div class="image-alt" title="${escapeHtml(img.alt_text)}">${escapeHtml(img.alt_text || 'No alt text')}</div>
                                    <div class="image-meta">
                                        <span class="badge score">Score: ${img.score.toFixed(2)}</span>
                                        <span>${img.width || '?'}x${img.height || '?'}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');
                    resultsContainer.appendChild(buildPagination(page, totalPages));
                }

            } else if (currentTab === 'pdfs') {
                resultsContainer.className = 'results-container';
                if (pdfs.length === 0) {
                    resultsContainer.innerHTML = '<div class="empty-state">No PDF documents found.</div>';
                } else {
                    const totalPages = Math.ceil(pdfs.length / RESULTS_PER_PAGE);
                    const page = Math.min(currentPage, totalPages);
                    const start = (page - 1) * RESULTS_PER_PAGE;
                    resultsContainer.innerHTML = pdfs.slice(start, start + RESULTS_PER_PAGE).map(doc => renderDocCard(doc)).join('');
                    resultsContainer.appendChild(buildPagination(page, totalPages));
                }
            }
        }

        function buildPagination(page, totalPages) {
            const wrapper = document.createElement('div');
            wrapper.className = 'pagination-container';
            if (totalPages <= 1) return wrapper;

            // Logo label
            const label = document.createElement('div');
            label.className = 'pagination-label';
            label.innerHTML = `Mini<span>S</span>earch`;
            wrapper.appendChild(label);

            const pages = document.createElement('div');
            pages.className = 'pagination-pages';

            // Prev arrow
            if (page > 1) {
                const prev = document.createElement('button');
                prev.className = 'page-btn arrow';
                prev.innerHTML = '&#8249;';
                prev.title = 'Previous';
                prev.onclick = () => goToPage(page - 1);
                pages.appendChild(prev);
            }

            // Page number buttons with ellipsis like Google
            const pageNums = getPageRange(page, totalPages);
            pageNums.forEach(p => {
                if (p === '...') {
                    const span = document.createElement('span');
                    span.className = 'page-btn';
                    span.style.cursor = 'default';
                    span.textContent = '...';
                    pages.appendChild(span);
                } else {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (p === page ? ' active' : '');
                    btn.textContent = p;
                    btn.onclick = () => goToPage(p);
                    pages.appendChild(btn);
                }
            });

            // Next arrow
            if (page < totalPages) {
                const next = document.createElement('button');
                next.className = 'page-btn arrow';
                next.innerHTML = '&#8250;';
                next.title = 'Next';
                next.onclick = () => goToPage(page + 1);
                pages.appendChild(next);
            }

            wrapper.appendChild(pages);
            return wrapper;
        }

        function getPageRange(current, total) {
            if (total <= 10) {
                return Array.from({length: total}, (_, i) => i + 1);
            }
            const pages = [];
            if (current <= 5) {
                for (let i = 1; i <= 7; i++) pages.push(i);
                pages.push('...', total);
            } else if (current >= total - 4) {
                pages.push(1, '...');
                for (let i = total - 6; i <= total; i++) pages.push(i);
            } else {
                pages.push(1, '...', current - 2, current - 1, current, current + 1, current + 2, '...', total);
            }
            return pages;
        }

        function goToPage(p) {
            currentPage = p;
            renderResults();
            window.scrollTo({top: 0, behavior: 'smooth'});
        }

        function renderDocCard(doc) {
            const isPdf = doc.doc_type === 'PDF';
            const docClass = isPdf ? 'pdf' : 'html';
            const badgeClass = isPdf ? 'type-pdf' : 'type-html';
            const targetLink = isPdf && doc.html_file ? `/storage/pdfs/${doc.html_file}` : doc.url;
            
            return `
                <div class="result-card ${docClass}">
                    <div class="result-header">
                        <a href="${escapeHtml(targetLink)}" target="_blank" class="result-title-link">${escapeHtml(doc.title || 'Untitled Document')}</a>
                        <div class="meta-badges">
                            <span class="badge ${badgeClass}">${doc.doc_type || 'HTML'}</span>
                            <span class="badge score">Score: ${doc.score.toFixed(2)}</span>
                        </div>
                    </div>
                    <div class="result-domain-line">
                        <span>🌐 ${escapeHtml(doc.domain || 'localhost')}</span>
                        <a href="${escapeHtml(doc.url)}" target="_blank" class="result-url-text">${escapeHtml(doc.url)}</a>
                    </div>
                    <p class="result-snippet">${doc.snippet || 'No snippet available.'}</p>
                    ${doc.author ? `
                        <div class="result-author">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                            Author: ${escapeHtml(doc.author)}
                        </div>
                    ` : ''}
                </div>
            `;
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }
    </script>
</body>
</html>
"""
    return html_content

