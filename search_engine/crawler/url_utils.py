# crawler/url_utils.py

from urllib.parse import urldefrag, urljoin, urlparse, urlunparse


def normalize_url(base_url: str, link: str) -> str:
    joined_url = urljoin(base_url, link)
    defragged_url, _fragment = urldefrag(joined_url)

    parsed = urlparse(defragged_url)

    return urlunparse(
        parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower()
        )
    )


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def is_same_domain(url: str, allowed_domain: str) -> bool:
    return get_domain(url) == allowed_domain


def classify_url(url: str) -> str:
    path = urlparse(url).path.lower()
    # If the URL ends with html/htm, is a directory, or has no file extension, classify as HTML
    if path.endswith((".html", ".htm")) or path.endswith("/") or not path.split("/")[-1].count("."):
        return "HTML"
    elif path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")):
        return "IMAGE"
    elif path.endswith(".pdf"):
        return "PDF"
    elif path.endswith((".mp4", ".webm", ".ogg", ".avi", ".mov", ".flv")):
        return "VIDEO"
    elif path.endswith((".mp3", ".wav", ".aac", ".flac", ".m4a")):
        return "AUDIO"
    else:
        return "OTHER"
