# crawler/crawler.py

from bs4 import BeautifulSoup
from pathlib import Path

from crawler.fetcher import fetch_page
from crawler.url_utils import normalize_url, is_same_domain, get_domain
import json

class WebCrawler:

    def __init__(self, seed_url: str, max_pages: int = 100):

        self.seed_url = seed_url
        self.allowed_domain = get_domain(seed_url)

        self.max_pages = max_pages

        self.visited = set()
        self.to_visit = {seed_url}
        self.metadata = {}

        Path("data/raw_html").mkdir(
            parents=True,
            exist_ok=True
        )

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

            if is_same_domain(
                full_url,
                self.allowed_domain
            ):
                links.add(full_url)

        return links

    def crawl(self):

        page_count = 0

        while self.to_visit and page_count < self.max_pages:

            current_url = self.to_visit.pop()

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

            self.to_visit.update(
                links - self.visited
            )

            self.visited.add(current_url)

        with open("data/raw_html/metadata.json","w", encoding="utf-8") as f:
            json.dump(
                self.metadata,
                f,
                indent=4
            )
        print(f"\nDone. Crawled {page_count} pages.")