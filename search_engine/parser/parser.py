from bs4 import BeautifulSoup


class HTMLParser:

    def parse(self, html: str) -> dict:

        soup = BeautifulSoup(html, "html.parser")

        for tag_name in ("script", "style", "noscript"):

            for tag in soup.find_all(tag_name):
                tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

        content = soup.get_text(" ", strip=True)

        return {
            "title": title,
            "content": content
        }
