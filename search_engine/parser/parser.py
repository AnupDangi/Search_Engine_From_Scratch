# parser/parser.py

from bs4 import BeautifulSoup
import re


class HTMLParser:

    def parse(self, html: str):

        soup = BeautifulSoup(html, "html.parser")

        # Remove noisy tags
        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "noscript",
            "svg"
        ]):
            tag.decompose()

        title = ""

        if soup.title:
            title = soup.title.get_text(strip=True)

        text = soup.get_text(
            separator=" ",
            strip=True
        )

        # Remove extra whitespace
        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return {
            "title": title,
            "content": text
        }