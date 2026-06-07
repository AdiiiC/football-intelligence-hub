"""
Understat scraper — xG timelines, shot maps, rolling form.
Uses the understat JSON API embedded in each page.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import random

import requests

from config.settings import get_scraper_headers, CACHE_DIR, CACHE_TTL_STATS

BASE_URL = "https://understat.com"
SESSION = requests.Session()
SESSION.headers.update(get_scraper_headers())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    """Return a writable cache directory, falling back to /tmp."""
    p = Path(CACHE_DIR)
    try:
        p.mkdir(parents=True, exist_ok=True)
        (p / ".write_test").touch()
        (p / ".write_test").unlink(missing_ok=True)
        return p
    except OSError:
        return Path("/tmp/football_cache")


def _cache_path(key: str) -> Path:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


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


def _get_page(url: str, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            SESSION.headers.update(get_scraper_headers())
            resp = SESSION.get(url, timeout=20)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429:
                time.sleep(30 + random.uniform(0, 10))
                continue
            time.sleep(2 ** attempt + random.uniform(0, 2))
        except Exception:
            time.sleep(2 ** attempt + random.uniform(0, 2))
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
    Fetch player data (shots, matches, groups) from Understat via GET.
    Must visit the player page first to obtain a PHPSESSID cookie,
    then GET getPlayerData/{id} with X-Requested-With header.
    """
    cache_key = f"us_playerdata_{player_id}"
    cached = _load_cache(cache_key, CACHE_TTL_STATS)
    if cached is not None:
        return cached

    page_url = f"{BASE_URL}/player/{player_id}"
    page_resp = SESSION.get(page_url, timeout=15)
    if page_resp.status_code != 200:
        return None

    data_resp = SESSION.get(
        f"{BASE_URL}/getPlayerData/{player_id}",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": page_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
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


def search_player_understat(name: str, league: str = "EPL", season: str = "2025") -> Optional[dict]:
    """
    Search Understat for a player by name within a league via POST API.
    Returns the best-matching player dict with their Understat ID.
    Tries current season first, falls back to previous season automatically.
    Matches on full name, partial containment, or last-name token overlap.
    """
    import unicodedata

    def _norm(s: str) -> str:
        _MAP = str.maketrans({"Ø": "O", "ø": "o", "Æ": "AE", "æ": "ae", "ß": "ss"})
        return unicodedata.normalize("NFKD", s.translate(_MAP)).encode("ascii", "ignore").decode().lower().strip()

    def _best_match(players: list, name_norm: str) -> Optional[dict]:
        name_tokens = name_norm.split()
        name_surname = name_tokens[-1] if name_tokens else ""
        best = None
        best_score = 0
        for p in players:
            p_norm = _norm(p.get("player_name", ""))
            p_tokens = p_norm.split()
            p_surname = p_tokens[-1] if p_tokens else ""
            # Exact full match
            if p_norm == name_norm:
                return p
            # Full containment
            if name_norm in p_norm or p_norm in name_norm:
                score = 50 + len(set(name_tokens) & set(p_tokens))
                if score > best_score:
                    best, best_score = p, score
                continue
            # Surname-to-surname match (last token of both names)
            if name_surname and p_surname == name_surname:
                score = 30
                if score > best_score:
                    best, best_score = p, score
                continue
            # Multi-token overlap only (≥2 tokens must match)
            shared = set(name_tokens) & set(p_tokens)
            if len(shared) >= 2:
                score = len(shared) * 10
                if score > best_score:
                    best, best_score = p, score
        return best

    name_norm = _norm(name)
    # Try requested season first, then adjacent seasons
    seasons_to_try = [season]
    try:
        s_int = int(season)
        for delta in [1, -1]:
            alt = str(s_int + delta)
            if alt not in seasons_to_try:
                seasons_to_try.append(alt)
    except ValueError:
        pass

    for szn in seasons_to_try:
        cache_key = f"us_search_{league}_{szn}_{name_norm.replace(' ', '_')}"
        cached = _load_cache(cache_key, 86400 * 7)
        if cached:
            return cached
        try:
            resp = SESSION.post(
                f"{BASE_URL}/main/getPlayersStats/",
                data={"league": league, "season": szn},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            players = resp.json().get("players", [])
        except Exception:
            continue

        best = _best_match(players, name_norm)
        if best:
            _save_cache(cache_key, best)
            return best

    return None


def get_player_understat_url(player_id: str) -> str:
    """Return the Understat player page URL for iframe embedding."""
    return f"{BASE_URL}/player/{player_id}"


def get_player_season_summary(player_id: str) -> list[dict]:
    """
    Return per-season stat summary from groups['season'].
    Each dict: season, team, apps, minutes, goals, assists, shots, xG, xA, xG90, xA90, npxG
    """
    data = _get_player_data(player_id)
    if not data:
        return []
    seasons_raw = (data.get("groups") or {}).get("season", [])
    result = []
    for row in seasons_raw:
        try:
            mins = max(int(row.get("time", 1)), 1)
            per90 = mins / 90
            xg = float(row.get("xG", 0))
            xa = float(row.get("xA", 0))
            result.append({
                "season":  str(int(row.get("season", 0))) + "/" + str(int(row.get("season", 0)) + 1),
                "team":    row.get("team", ""),
                "apps":    int(row.get("games", 0)),
                "minutes": mins,
                "goals":   int(row.get("goals", 0)),
                "assists": int(row.get("assists", 0)),
                "shots":   int(row.get("shots", 0)),
                "xG":      round(xg, 2),
                "xA":      round(xa, 2),
                "npxG":    round(float(row.get("npxG", 0)), 2),
                "xG90":    round(xg / per90, 2),
                "xA90":    round(xa / per90, 2),
            })
        except Exception:
            continue
    # Sort newest first
    result.sort(key=lambda r: r["season"], reverse=True)
    return result



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
