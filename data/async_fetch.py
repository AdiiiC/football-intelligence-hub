"""
Async scraping utilities using asyncio + httpx.
Provides concurrent fetching for squad enrichment pipeline.
Falls back to synchronous requests if httpx is unavailable.
"""

import asyncio
from typing import Optional

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from config.settings import SCRAPER_HEADERS


async def fetch_url_async(url: str, method: str = "GET", data: dict = None,
                          timeout: int = 20) -> Optional[str]:
    """Fetch a URL asynchronously. Returns response text or None."""
    if not HAS_HTTPX:
        import requests
        try:
            if method == "POST":
                r = requests.post(url, data=data, headers=SCRAPER_HEADERS, timeout=timeout)
            else:
                r = requests.get(url, headers=SCRAPER_HEADERS, timeout=timeout)
            return r.text if r.status_code == 200 else None
        except Exception:
            return None

    async with httpx.AsyncClient(headers=SCRAPER_HEADERS, timeout=timeout, follow_redirects=True) as client:
        try:
            if method == "POST":
                r = await client.post(url, data=data)
            else:
                r = await client.get(url)
            return r.text if r.status_code == 200 else None
        except Exception:
            return None


async def fetch_all_async(requests_list: list[dict]) -> list[Optional[str]]:
    """
    Fetch multiple URLs concurrently.
    requests_list: [{"url": str, "method": str, "data": dict}, ...]
    Returns list of response texts in the same order.
    """
    tasks = [
        fetch_url_async(
            req["url"],
            method=req.get("method", "GET"),
            data=req.get("data"),
        )
        for req in requests_list
    ]
    return await asyncio.gather(*tasks)


def run_async(coro):
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def enrich_players_async(players: list[dict], enrichment_fn, *args) -> list[dict]:
    """
    Run an enrichment function concurrently across a list of players.
    enrichment_fn(player, *args) → dict
    """
    async def _run():
        tasks = [
            asyncio.to_thread(enrichment_fn, p, *args)
            for p in players
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = run_async(_run())
    enriched = []
    for player, result in zip(players, results):
        if isinstance(result, dict):
            enriched.append({**player, **result})
        else:
            enriched.append(player)
    return enriched
