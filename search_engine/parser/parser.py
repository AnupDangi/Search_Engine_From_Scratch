from bs4 import BeautifulSoup
from urllib.parse import urljoin
from crawler.url_utils import normalize_url


class HTMLParser:

    def parse(self, html: str, page_url: str = "") -> dict:

        soup = BeautifulSoup(html, "html.parser")

        # Extract images before decomposing scripts/styles
        images = []
        for img in soup.find_all("img", src=True):
            src = img["src"]
            try:
                # Normalize relative URL
                img_url = normalize_url(page_url, src) if page_url else src
            except Exception:
                img_url = urljoin(page_url, src)

            alt = img.get("alt", "").strip()

            # Extract surrounding parent text
            parent = img.parent
            surrounding_text = ""
            if parent:
                # Get text of parent node, excluding script/style tags
                for bad_tag in parent.find_all(["script", "style"]):
                    bad_tag.decompose()
                surrounding_text = parent.get_text(" ", strip=True)
                if len(surrounding_text) > 300:
                    surrounding_text = surrounding_text[:300]

            width = img.get("width")
            height = img.get("height")

            images.append({
                "image_url": img_url,
                "alt_text": alt,
                "surrounding_text": surrounding_text,
                "width": int(width) if width and width.isdigit() else None,
                "height": int(height) if height and height.isdigit() else None
            })

        for tag_name in ("script", "style", "noscript"):

            for tag in soup.find_all(tag_name):
                tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

        # H1/H2 headings as a separate high-signal field
        heading_parts = []
        for tag in soup.find_all(["h1", "h2"]):
            text = tag.get_text(" ", strip=True)
            if text:
                heading_parts.append(text)
        heading = " ".join(heading_parts)

        # Meta description — good snippet source
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": lambda n: n and n.lower() == "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "").strip()

        content = soup.get_text(" ", strip=True)

        return {
            "title": title,
            "heading": heading,
            "meta_description": meta_desc,
            "content": content,
            "images": images,
        }
