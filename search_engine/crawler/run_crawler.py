from crawler.crawler import WebCrawler


if __name__ == "__main__":

    crawler = WebCrawler(
        seed_url="https://docs.python.org/3/",
        max_pages=100
    )

    crawler.crawl()