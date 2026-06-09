# crawler/url_utils.py

from urllib.parse import urljoin, urlparse


def normalize_url(base_url: str, link: str) -> str:
    return urljoin(base_url, link)


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def is_same_domain(url: str, allowed_domain: str) -> bool:
    return get_domain(url) == allowed_domain