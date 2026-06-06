"""
SoFIFA live scraper — player search and squad data.
Uses cloudscraper to handle intermittent Cloudflare protection.
Falls back gracefully when blocked.

Image CDNs confirmed working:
  - cdn.sofifa.net/players/{id[:3]}/{id[3:]}/26_240.png   (high-res face)
  - cdn.sofifa.net/players/{id[:3]}/{id[3:]}/26_120.png   (thumbnail)
  - cdn.futbin.com/content/fifa25/img/players/{full_id}.png (fallback)
"""

import time
import json
import re
from pathlib import Path
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup

from config.settings import SCRAPER_HEADERS, CACHE_DIR, CACHE_TTL_SQUAD

BASE_URL = "https://sofifa.com"
CDN_BASE = "https://cdn.sofifa.net/players"

_scraper = None


def _get_scraper():
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True}
        )
        _scraper.headers.update({
            "User-Agent": SCRAPER_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        })
    return _scraper


def _cache_path(key: str) -> Path:
    p = Path(CACHE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def _load_cache(key: str, ttl: int):
    cp = _cache_path(key)
    if not cp.exists():
        return None
    if time.time() - cp.stat().st_mtime > ttl:
        return None
    with open(cp) as f:
        return json.load(f)


def _save_cache(key: str, data):
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


def _get_html(url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    """Fetch a URL via cloudscraper. Returns None if blocked."""
    s = _get_scraper()
    for attempt in range(retries):
        try:
            resp = s.get(url, timeout=20)
            if resp.status_code == 200 and "Just a moment" not in resp.text:
                return BeautifulSoup(resp.text, "html.parser")
            time.sleep(3 + attempt * 2)
        except Exception:
            time.sleep(5)
    return None


# ---------------------------------------------------------------------------
# Image URL helpers (no scraping needed)
# ---------------------------------------------------------------------------

def build_face_url(sofifa_id, resolution: str = "26_240") -> str:
    """
    Build the SoFIFA CDN face image URL.
    sofifa_id can be int or str (e.g. 241651 or '241651').
    resolution options: '26_240' (HD), '26_120' (thumb)
    Falls back to FutBin CDN automatically in the HTML img tag via onerror.
    """
    sid = str(int(sofifa_id)) if sofifa_id else ""
    if not sid:
        return ""
    # Pad to at least 6 chars
    sid = sid.zfill(6)
    p1, p2 = sid[:3], sid[3:]
    return f"{CDN_BASE}/{p1}/{p2}/{resolution}.png"


def build_futbin_face_url(sofifa_id) -> str:
    """FutBin CDN fallback — uses the full numeric SoFIFA ID."""
    sid = str(int(sofifa_id)) if sofifa_id else ""
    if not sid:
        return ""
    return f"https://cdn.futbin.com/content/fifa25/img/players/{sid}.png"


def build_img_tag(sofifa_id, size: str = "26_240", css: str = "") -> str:
    primary = build_face_url(sofifa_id, size)
    fallback = build_futbin_face_url(sofifa_id)
    return (
        f'<img src="{primary}" '
        f'onerror="this.onerror=null;this.src=\'{fallback}\'" '
        f'style="{css}" loading="lazy">'
    )


# ---------------------------------------------------------------------------
# SoFIFA player search (live scraping)
# ---------------------------------------------------------------------------

def search_player_sofifa(name: str) -> list[dict]:
    """
    Search SoFIFA for a player by name.
    Returns list of matches with sofifa_id, name, overall, club, face_url.
    """
    cache_key = f"sofifa_search_{name.lower().replace(' ', '_')}"
    cached = _load_cache(cache_key, CACHE_TTL_SQUAD)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/players?keyword={name.replace(' ', '+')}"
    soup = _get_html(url)
    if not soup:
        return []  # Blocked — caller uses Kaggle fallback

    results = []
    # SoFIFA renders players in <tbody> rows
    for row in soup.select("table tbody tr"):
        try:
            link = row.select_one("a[href^='/player/']")
            if not link:
                continue
            href = link["href"]
            pid_match = re.search(r"/player/(\d+)/", href)
            if not pid_match:
                continue
            sofifa_id = pid_match.group(1)

            name_tag = row.select_one(".col-name")
            player_name = name_tag.get_text(strip=True) if name_tag else link.get_text(strip=True)

            overall_tag = row.select_one(".col-oa em")
            overall = int(overall_tag.get_text(strip=True)) if overall_tag else 0

            club_tag = row.select_one("a[href^='/team/']")
            club = club_tag.get_text(strip=True) if club_tag else ""

            pos_tag = row.select_one(".col-name .bp3-tag")
            position = pos_tag.get_text(strip=True) if pos_tag else ""

            results.append({
                "sofifa_id": sofifa_id,
                "name": player_name,
                "overall": overall,
                "club": club,
                "position": position,
                "face_url_hd": build_face_url(sofifa_id, "26_240"),
                "face_url_thumb": build_face_url(sofifa_id, "26_120"),
                "face_url_futbin": build_futbin_face_url(sofifa_id),
            })
        except Exception:
            continue

    _save_cache(cache_key, results)
    return results


def get_player_attributes_sofifa(sofifa_id: str) -> dict:
    """
    Scrape full attributes for a player from their SoFIFA profile page.
    Returns dict with PAC, SHO, PAS, DRI, DEF, PHY and all sub-attributes.
    """
    cache_key = f"sofifa_player_{sofifa_id}"
    cached = _load_cache(cache_key, CACHE_TTL_SQUAD)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/player/{sofifa_id}"
    soup = _get_html(url)
    if not soup:
        return {}

    attrs = {"sofifa_id": sofifa_id}

    try:
        # Overall & potential
        oa = soup.select_one(".col-oa em")
        if oa:
            attrs["overall"] = int(oa.get_text(strip=True))

        # Main 6 attributes (PAC/SHO/PAS/DRI/DEF/PHY)
        for card in soup.select(".stats .text-center"):
            label = card.select_one("span:last-child")
            value = card.select_one("em")
            if label and value:
                key = label.get_text(strip=True).lower()[:3]
                try:
                    attrs[key] = int(value.get_text(strip=True))
                except ValueError:
                    pass

        # Individual sub-attributes
        for attr_row in soup.select(".attr-row"):
            spans = attr_row.select("span")
            for i in range(0, len(spans) - 1, 2):
                val_span = spans[i]
                lbl_span = spans[i + 1]
                try:
                    val = int(re.search(r"\d+", val_span.get_text()).group())
                    lbl = lbl_span.get_text(strip=True).lower().replace(" ", "_")
                    attrs[lbl] = val
                except Exception:
                    pass

        # Player info
        info = soup.select_one(".meta")
        if info:
            attrs["info_text"] = info.get_text(strip=True)

        attrs["face_url_hd"] = build_face_url(sofifa_id, "26_240")
        attrs["face_url_thumb"] = build_face_url(sofifa_id, "26_120")
        attrs["face_url_futbin"] = build_futbin_face_url(sofifa_id)

    except Exception:
        pass

    if len(attrs) > 2:
        _save_cache(cache_key, attrs)

    return attrs


def get_sofifa_id_for_player(name: str, club: str = "") -> Optional[str]:
    """
    Convenience: return best-match SoFIFA ID for a player name.
    Tries live search first, then returns None if blocked.
    """
    results = search_player_sofifa(name)
    if not results:
        return None

    last = name.lower().split()[-1]
    for r in results:
        if last in r["name"].lower():
            if club and club.lower().split()[0] not in r.get("club", "").lower():
                continue
            return r["sofifa_id"]
    return results[0]["sofifa_id"] if results else None
