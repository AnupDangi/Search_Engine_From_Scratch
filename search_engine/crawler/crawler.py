# crawler/crawler.py

from bs4 import BeautifulSoup
import heapq
from pathlib import Path
from urllib.parse import urlparse

from crawler.fetcher import fetch_page
from crawler.url_utils import normalize_url, is_same_domain, get_domain
import json

class WebCrawler:

    def __init__(self, seed_url: str, max_pages: int = 100):

        self.seed_url = normalize_url(seed_url, "")
        self.allowed_domain = get_domain(self.seed_url)
        self.allowed_path_prefix = urlparse(self.seed_url).path

        self.max_pages = max_pages

        self.visited = set()
        self.to_visit = []
        self.queued = {self.seed_url}
        self.queue_counter = 0
        self._queue_url(self.seed_url)
        self.metadata = {}

        Path("data/raw_html").mkdir(
            parents=True,
            exist_ok=True
        )

    def _priority(self, url: str) -> int:

        path = urlparse(url).path

        priority_prefixes = (
            ("/3/library/", 0),
            ("/3/tutorial/", 1),
            ("/3/reference/", 2),
            ("/3/howto/", 3),
            ("/3/faq/", 4),
            ("/3/whatsnew/", 5),
            ("/3/extending/", 7),
            ("/3/c-api/", 8)
        )

        for prefix, priority in priority_prefixes:

            if path.startswith(prefix):
                return priority

        return 6

    def _queue_url(self, url: str):

        heapq.heappush(
            self.to_visit,
            (
                self._priority(url),
                self.queue_counter,
                url
            )
        )
        self.queue_counter += 1

    def save_html(self, html: str, page_id: int,url:str):

        file_name=f"{page_id}.html"

        filepath = f"data/raw_html/{page_id}.html"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        self.metadata[page_id] = {
            "id": page_id,
            "url": url,
            "html_file": file_name
        }

    def extract_links(self, html: str, current_url: str):

        soup = BeautifulSoup(html, "html.parser")

        links = set()

        for tag in soup.find_all("a", href=True):

            href = tag["href"]

            full_url = normalize_url(
                current_url,
                href
            )

            parsed_url = urlparse(full_url)

            if (
                parsed_url.scheme in {"http", "https"}
                and is_same_domain(
                    full_url,
                    self.allowed_domain
                )
                and parsed_url.path.startswith(
                    self.allowed_path_prefix
                )
            ):
                links.add(full_url)

        return links

    def crawl(self):

        page_count = 0

        while self.to_visit and page_count < self.max_pages:

            _priority, _counter, current_url = heapq.heappop(
                self.to_visit
            )

            if current_url in self.visited:
                continue

            print(f"[CRAWLING] {current_url}")

            html = fetch_page(current_url)

            if not html:
                continue

            page_count += 1

            self.save_html(
                html,
                page_count,
                current_url
            )

            links = self.extract_links(
                html,
                current_url
            )

            for link in sorted(links):

                if (
                    link not in self.visited
                    and link not in self.queued
                ):
                    self._queue_url(link)
                    self.queued.add(link)

            self.visited.add(current_url)

        with open("data/raw_html/metadata.json","w", encoding="utf-8") as f:
            json.dump(
                self.metadata,
                f,
                indent=4
            )
        print(f"\nDone. Crawled {page_count} pages.")
