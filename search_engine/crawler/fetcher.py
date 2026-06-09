# crawler/fetcher.py

import requests


def fetch_page(url: str) -> str :
    headers = {
        "User-Agent": "SearchKing_nep/0.1"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        return response.text

    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return None
    
