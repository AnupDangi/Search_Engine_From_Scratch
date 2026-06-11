# crawler/fetcher.py

import aiohttp
import asyncio

async def async_fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    headers = {
        "User-Agent": "SearchKing_nep/0.1"
    }

    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            response.raise_for_status()
            text = await response.text(encoding="utf-8")
            return text

    except Exception as e:
        print(f"[ERROR] async fetch HTML {url}: {e}")
        return None

async def async_fetch_binary(url: str, session: aiohttp.ClientSession) -> bytes:
    headers = {
        "User-Agent": "SearchKing_nep/0.1"
    }

    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            response.raise_for_status()
            content = await response.read()
            return content

    except Exception as e:
        print(f"[ERROR] async fetch binary {url}: {e}")
        return None
