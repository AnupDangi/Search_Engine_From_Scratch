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
