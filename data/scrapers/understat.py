"""
Understat scraper — xG timelines, shot maps, rolling form.
Uses the understat JSON API embedded in each page.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

from config.settings import SCRAPER_HEADERS, CACHE_DIR, CACHE_TTL_STATS

BASE_URL = "https://understat.com"
SESSION = requests.Session()
SESSION.headers.update(SCRAPER_HEADERS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    p = Path(CACHE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def _load_cache(key: str, ttl: int) -> Optional[dict]:
    cp = _cache_path(key)
    if not cp.exists():
        return None
    age = time.time() - cp.stat().st_mtime
    if age > ttl:
        return None
    with open(cp) as f:
        return json.load(f)


def _save_cache(key: str, data) -> None:
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


def _extract_json_var(html: str, var_name: str) -> Optional[dict]:
    """Extract JSON-encoded JS variable from Understat page source."""
    pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html)
    if not match:
        return None
    try:
        raw = match.group(1).encode("utf-8").decode("unicode_escape")
        return json.loads(raw)
    except Exception:
        return None


def _get_page(url: str) -> Optional[str]:
    try:
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def _get_player_data(player_id: str) -> Optional[dict]:
    """
    Fetch full player data from Understat using the XHR endpoint.
    Requires a session cookie from visiting the player page first.
    """
    cache_key = f"us_playerdata_{player_id}"
    cached = _load_cache(cache_key, CACHE_TTL_STATS)
    if cached is not None:
        return cached

    # Establish session by visiting the player page first (gets PHPSESSID)
    page_url = f"{BASE_URL}/player/{player_id}"
    page_resp = SESSION.get(page_url, timeout=15)
    if page_resp.status_code != 200:
        return None

    data_resp = SESSION.get(
        f"{BASE_URL}/getPlayerData/{player_id}",
        headers={**_XHR_HEADERS, "Referer": page_url},
        cookies=page_resp.cookies,
        timeout=20,
    )
    if data_resp.status_code != 200:
        return None

    try:
        data = data_resp.json()
    except Exception:
        return None

    _save_cache(cache_key, data)
    return data


def get_player_shots(player_id: str, season: str = "2024") -> list[dict]:
    """
    Fetch shot data for an Understat player.
    Returns list of normalized shot dicts. Filters to given season if provided.
    """
    data = _get_player_data(player_id)
    if not data:
        return []

    raw_shots = data.get("shots", [])
    result = []
    for s in raw_shots:
        if season and str(s.get("season", "")) != str(season):
            continue
        try:
            result.append({
                "id": s.get("id", ""),
                "minute": int(s.get("minute", 0)),
                "result": s.get("result", ""),
                "x": float(s.get("X", 0)) * 100,   # scale 0-1 → 0-100
                "y": float(s.get("Y", 0)) * 100,
                "xg": float(s.get("xG", 0)),
                "situation": s.get("situation", ""),
                "season": s.get("season", ""),
                "shot_type": s.get("shotType", ""),
                "date": s.get("date", ""),
                "player_assisted": s.get("player_assisted", ""),
                "last_action": s.get("lastAction", ""),
            })
        except Exception:
            continue
    return result


def get_player_xg_timeline(player_id: str, season: str = "2024") -> list[dict]:
    """
    Return per-match xG/xA timeline for a player in a season.
    """
    data = _get_player_data(player_id)
    if not data:
        return []

    timeline = []
    for m in data.get("matches", []):
        if str(m.get("season", "")) != str(season):
            continue
        try:
            timeline.append({
                "date": m.get("date", ""),
                "home_team": m.get("h_team", ""),
                "away_team": m.get("a_team", ""),
                "xg": float(m.get("xG", 0)),
                "xga": float(m.get("xGChain", 0)),
                "goals": int(m.get("goals", 0)),
                "assists": int(m.get("assists", 0)),
                "time_played": int(m.get("time", 0)),
                "position": m.get("position", ""),
            })
        except Exception:
            continue

    timeline.sort(key=lambda x: x["date"])
    return timeline


def search_player_understat(name: str, league: str = "EPL", season: str = "2024") -> Optional[dict]:
    """
    Search Understat for a player by name within a league via POST API.
    Returns the best-matching player dict with their Understat ID.
    """
    cache_key = f"us_search_{league}_{season}_{name.lower().replace(' ', '_')}"
    cached = _load_cache(cache_key, 86400 * 7)
    if cached:
        return cached

    try:
        resp = SESSION.post(
            f"{BASE_URL}/main/getPlayersStats/",
            data={"league": league, "season": season},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        players = resp.json().get("players", [])
    except Exception:
        return None

    name_lower = name.lower()
    # Normalize: strip accents for comparison
    import unicodedata
    def _norm(s):
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

    name_norm = _norm(name)
    best = None
    best_score = 0
    for p in players:
        p_name = p.get("player_name", "")
        p_norm = _norm(p_name)
        if p_norm == name_norm:
            best = p
            break
        if name_norm in p_norm or p_norm in name_norm:
            # Prefer longer match (more specific)
            score = len(set(name_norm.split()) & set(p_norm.split()))
            if score > best_score:
                best = p
                best_score = score

    if best:
        _save_cache(cache_key, best)
    return best


def get_player_understat_url(player_id: str) -> str:
    """Return the Understat player page URL for iframe embedding."""
    return f"{BASE_URL}/player/{player_id}"



def get_league_player_stats(league: str = "EPL", season: str = "2024") -> list[dict]:
    """
    Fetch all player stats for a league from Understat via POST API.
    Returns list of player stat dicts.
    """
    cache_key = f"us_league_{league}_{season}"
    cached = _load_cache(cache_key, CACHE_TTL_STATS)
    if cached is not None:
        return cached

    try:
        resp = SESSION.post(
            f"{BASE_URL}/main/getPlayersStats/",
            data={"league": league, "season": season},
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        players = resp.json().get("players", [])
    except Exception:
        return []

    result = []
    for p in players:
        try:
            minutes = max(int(p.get("time", 1)), 1)
            per90 = minutes / 90
            result.append({
                "id":           p.get("id", ""),
                "player_name":  p.get("player_name", ""),
                "team":         p.get("team_title", ""),
                "games":        int(p.get("games", 0)),
                "goals":        int(p.get("goals", 0)),
                "assists":      int(p.get("assists", 0)),
                "shots":        int(p.get("shots", 0)),
                "time":         minutes,
                "xG":           float(p.get("xG", 0)),
                "xA":           float(p.get("xA", 0)),
                "npxG":         float(p.get("npxG", 0)),
                "key_passes":   int(p.get("key_passes", 0)),
                "position":     p.get("position", ""),
                "xg_per90":     round(float(p.get("xG", 0)) / per90, 3),
                "xa_per90":     round(float(p.get("xA", 0)) / per90, 3),
                "npxg_per90":   round(float(p.get("npxG", 0)) / per90, 3),
            })
        except Exception:
            continue

    _save_cache(cache_key, result)
    return result
