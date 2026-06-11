import asyncio
import aiohttp
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse
import json

from crawler.fetcher import async_fetch_page, async_fetch_binary
from crawler.url_utils import normalize_url, is_same_domain, get_domain, classify_url
from storage.database import Database

class WebCrawler:

    def __init__(self, seed_url, max_pages: int = 100, restrict_domain: bool = True, restrict_path: bool = True, concurrency: int = 10):
        if isinstance(seed_url, list):
            self.seed_urls = [normalize_url(url, "") for url in seed_url]
        else:
            self.seed_urls = [normalize_url(seed_url, "") if seed_url else None]
            self.seed_urls = [url for url in self.seed_urls if url]

        self.restrict_domain = restrict_domain
        self.restrict_path = restrict_path
        self.concurrency = concurrency

        self.allowed_domains = {get_domain(url) for url in self.seed_urls}
        self.allowed_paths = {get_domain(url): urlparse(url).path for url in self.seed_urls}

        self.max_pages = max_pages

        self.visited = set()
        self.queued = set(self.seed_urls)

        self.metadata = {}
        self.page_count = 0
        # NOTE: asyncio.Queue must be created inside the running event loop,
        # so we initialize it lazily in crawl() rather than here.
        self.queue = None

        Path("data/raw_html").mkdir(parents=True, exist_ok=True)
        Path("storage/pdfs").mkdir(parents=True, exist_ok=True)

    def save_html(self, html: str, page_id: int, url: str):
        file_name = f"{page_id}.html"
        filepath = f"data/raw_html/{page_id}.html"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        self.metadata[page_id] = {
            "id": page_id,
            "url": url,
            "html_file": file_name
        }

    def save_pdf(self, content: bytes, page_id: int, url: str):
        file_name = f"{page_id}.pdf"
        filepath = f"storage/pdfs/{file_name}"
        with open(filepath, "wb") as f:
            f.write(content)

        self.metadata[page_id] = {
            "id": page_id,
            "url": url,
            "html_file": file_name,
            "is_pdf": True
        }

    def discover_resources(self, db: Database, html: str, page_url: str, page_id: int):
        soup = BeautifulSoup(html, "html.parser")
        html_links = set()
        images = set()
        pdfs = set()

        # Extract links from <a> tags
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            try:
                full_url = normalize_url(page_url, href)
            except Exception:
                continue

            res_type = classify_url(full_url)
            if res_type == "HTML":
                html_links.add(full_url)
                db.insert_link(page_url, full_url)
            elif res_type == "PDF":
                pdfs.add(full_url)
                db.insert_link(page_url, full_url)
            elif res_type == "IMAGE":
                images.add(full_url)

        # Extract links from <img> tags
        for img_tag in soup.find_all("img", src=True):
            src = img_tag["src"]
            try:
                full_url = normalize_url(page_url, src)
            except Exception:
                continue
            images.add(full_url)

        # Save discovered resources
        resources = {
            "page_url": page_url,
            "html_links": sorted(list(html_links)),
            "images": sorted(list(images)),
            "pdfs": sorted(list(pdfs))
        }

        resources_path = f"data/raw_html/{page_id}_resources.json"
        with open(resources_path, "w", encoding="utf-8") as f:
            json.dump(resources, f, indent=4)

        # Allow new links
        allowed_links = set()
        for link in (html_links | pdfs):
            parsed = urlparse(link)
            if parsed.scheme in {"http", "https"}:
                if not self.restrict_domain:
                    allowed_links.add(link)
                else:
                    link_domain = get_domain(link)
                    if link_domain in self.allowed_domains:
                        if not self.restrict_path or parsed.path.startswith(self.allowed_paths.get(link_domain, "/")):
                            allowed_links.add(link)

        return allowed_links

    async def _worker(self, session: aiohttp.ClientSession, db: Database):
        while True:
            try:
                current_url = await asyncio.wait_for(self.queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # No more URLs coming — worker exits
                break

            try:
                if current_url in self.visited or self.page_count >= self.max_pages:
                    continue

                self.visited.add(current_url)

                # Check if PDF
                if current_url.lower().endswith(".pdf"):
                    print(f"[CRAWLING PDF] {current_url}")
                    content = await async_fetch_binary(current_url, session)
                    if content:
                        self.page_count += 1
                        self.save_pdf(content, self.page_count, current_url)
                else:
                    print(f"[CRAWLING] {current_url}")
                    html = await async_fetch_page(current_url, session)
                    if html:
                        self.page_count += 1
                        current_page_id = self.page_count
                        self.save_html(html, current_page_id, current_url)

                        # Offload BeautifulSoup parsing to a thread
                        links = await asyncio.to_thread(
                            self.discover_resources, db, html, current_url, current_page_id
                        )

                        for link in sorted(links):
                            if link not in self.visited and link not in self.queued:
                                if self.page_count + self.queue.qsize() < self.max_pages * 2:
                                    self.queue.put_nowait(link)
                                    self.queued.add(link)
            finally:
                self.queue.task_done()

    async def crawl(self):
        # Initialize queue here so it belongs to the currently running event loop
        self.queue = asyncio.Queue()
        for url in self.seed_urls:
            self.queue.put_nowait(url)

        db = Database()

        connector = aiohttp.TCPConnector(limit=self.concurrency, ssl=False)
        timeout = aiohttp.ClientTimeout(total=15, connect=5)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            workers = [
                asyncio.create_task(self._worker(session, db))
                for _ in range(self.concurrency)
            ]

            # Wait until all queued items are processed
            await self.queue.join()

            # Cancel any still-running workers (they are blocked on wait_for timeout)
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        with open("data/raw_html/metadata.json", "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=4)

        db.close()
        print(f"\nDone. Crawled {self.page_count} pages.")

