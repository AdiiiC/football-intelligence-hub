"""
EA FC Official Ratings Scraper.

Source: https://www.ea.com/games/ea-sports-fc/ratings
Method: Parse __NEXT_DATA__ JSON embedded in server-rendered HTML pages.
        100 players per page, paginated via ?page=N
        No Cloudflare, no JS rendering needed — works with plain requests.

Data includes: overallRating, all 40+ stats (PAC/SHO/PAS/DRI/DEF/PHY + sub-attrs),
               official avatarUrl (pulse.ea.com CDN), playerAbilities (PlayStyles), etc.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

from config.settings import SCRAPER_HEADERS, CACHE_DIR, CACHE_TTL_SQUAD

EA_RATINGS_URL = "https://www.ea.com/games/ea-sports-fc/ratings"
PLAYERS_CACHE_FILE = Path(CACHE_DIR) / "ea_all_players.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": SCRAPER_HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_page_data(html: str) -> Optional[dict]:
    """Extract __NEXT_DATA__ JSON from EA ratings page HTML."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _parse_player(raw: dict) -> dict:
    """Normalise a raw EA player dict into a flat, consistent format."""
    stats = raw.get("stats", {})

    def _stat(key: str) -> int:
        entry = stats.get(key, {})
        return int(entry.get("value", 0)) if isinstance(entry, dict) else 0

    position = raw.get("position", {})
    nationality = raw.get("nationality", {})
    team = raw.get("team", {})

    abilities = [a.get("label", "") for a in (raw.get("playerAbilities") or [])]
    alt_positions = [p.get("shortLabel", "") for p in (raw.get("alternatePositions") or [])]

    first = raw.get("firstName", "") or ""
    last  = raw.get("lastName", "") or ""
    common = raw.get("commonName")
    name = common if common else f"{first} {last}".strip()

    # The official EA avatar CDN — high-res portrait
    avatar_url = raw.get("avatarUrl", "")    # e.g. ratings-images-prod.pulse.ea.com/FC25/full/player-portraits/p209331.png
    shield_url = raw.get("shieldUrl", "")    # card shield image

    return {
        "ea_id":            raw.get("id"),
        "rank":             raw.get("rank"),
        "name":             name,
        "first_name":       first,
        "last_name":        last,
        "overall":          raw.get("overallRating", 0),
        "position_code":    position.get("shortLabel", ""),
        "position_label":   position.get("label", ""),
        "alt_positions":    alt_positions,
        "nationality":      nationality.get("label", ""),
        "nat_flag_url":     nationality.get("imageUrl", ""),
        "club_name":        team.get("label", ""),
        "club_logo_url":    team.get("imageUrl", ""),
        "league_name":      raw.get("leagueName", ""),
        "age":              _age_from_dob(raw.get("birthdate", "")),
        "height_cm":        raw.get("height"),
        "weight_kg":        raw.get("weight"),
        "skill_moves":      raw.get("skillMoves"),
        "weak_foot":        raw.get("weakFootAbility"),
        "preferred_foot":   "Right" if raw.get("preferredFoot") == 1 else "Left",
        "play_styles":      abilities,
        # ─── 6 main attributes ───
        "pac":  _stat("pac"),
        "sho":  _stat("sho"),
        "pas":  _stat("pas"),
        "dri":  _stat("dri"),
        "def_": _stat("def"),
        "phy":  _stat("phy"),
        # ─── Sub-attributes ───
        "acceleration":       _stat("acceleration"),
        "sprint_speed":       _stat("sprintSpeed"),
        "finishing":          _stat("finishing"),
        "shot_power":         _stat("shotPower"),
        "long_shots":         _stat("longShots"),
        "volleys":            _stat("volleys"),
        "penalties":          _stat("penalties"),
        "vision":             _stat("vision"),
        "crossing":           _stat("crossing"),
        "fk_accuracy":        _stat("freeKickAccuracy"),
        "short_passing":      _stat("shortPassing"),
        "long_passing":       _stat("longPassing"),
        "curve":              _stat("curve"),
        "agility":            _stat("agility"),
        "balance":            _stat("balance"),
        "reactions":          _stat("reactions"),
        "ball_control":       _stat("ballControl"),
        "dribbling_skill":    _stat("dribbling"),
        "composure":          _stat("composure"),
        "interceptions_attr": _stat("interceptions"),
        "heading_accuracy":   _stat("headingAccuracy"),
        "marking":            _stat("defensiveAwareness"),
        "standing_tackle":    _stat("standingTackle"),
        "sliding_tackle":     _stat("slidingTackle"),
        "jumping":            _stat("jumping"),
        "stamina":            _stat("stamina"),
        "strength":           _stat("strength"),
        "aggression":         _stat("aggression"),
        "positioning":        _stat("positioning"),
        "gk_diving":          _stat("gkDiving"),
        "gk_handling":        _stat("gkHandling"),
        "gk_kicking":         _stat("gkKicking"),
        "gk_positioning":     _stat("gkPositioning"),
        "gk_reflexes":        _stat("gkReflexes"),
        # ─── Image URLs ───
        "ea_avatar_url":    avatar_url,   # official EA portrait (best quality)
        "ea_shield_url":    shield_url,   # EA card shield
        # Also build CDN URLs using ea_id for card faces
        "sofifa_face_url":  _sofifa_url(raw.get("id")),
        "futbin_face_url":  _futbin_url(raw.get("id")),
    }


def _age_from_dob(dob_str: str) -> Optional[int]:
    """Parse 'M/D/YYYY HH:MM:SS AM' format to age."""
    if not dob_str:
        return None
    try:
        from datetime import datetime
        dt = datetime.strptime(dob_str.split(" ")[0], "%m/%d/%Y")
        today = datetime.today()
        return today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
    except Exception:
        return None


def _sofifa_url(sofifa_id) -> str:
    if not sofifa_id:
        return ""
    sid = str(int(sofifa_id)).zfill(6)
    return f"https://cdn.sofifa.net/players/{sid[:3]}/{sid[3:]}/26_240.png"


def _futbin_url(sofifa_id) -> str:
    if not sofifa_id:
        return ""
    return f"https://cdn.futbin.com/content/fifa25/img/players/{int(sofifa_id)}.png"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_page(page: int = 1) -> tuple:
    """
    Fetch one page (100 players) from EA ratings.
    Returns (players_list, total_players).
    """
    url = EA_RATINGS_URL if page == 1 else f"{EA_RATINGS_URL}?page={page}"
    try:
        resp = SESSION.get(url, timeout=25)
        if resp.status_code != 200:
            return [], 0
        # __NEXT_DATA__ regex — must handle large HTML (2.6MB)
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not m:
            return [], 0
        data = json.loads(m.group(1))
        rating_details = data["props"]["pageProps"]["ratingDetails"]
        raw_players = rating_details.get("items", [])
        total = rating_details.get("totalItems", 0)
        return [_parse_player(p) for p in raw_players], total
    except Exception as e:
        print(f"[ea_scraper] Page {page} error: {e}")
        return [], 0


def fetch_all_players(max_pages: int = 180, delay: float = 1.0) -> list[dict]:
    """
    Fetch all EA FC players (all pages). Saves to cache.
    max_pages: safety cap (17,873 players ÷ 100 = ~179 pages)
    delay: seconds between requests (be respectful)
    Returns complete list of normalised player dicts.
    """
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    all_players = []
    first_batch, total = fetch_page(1)
    if not first_batch:
        return []

    all_players.extend(first_batch)
    total_pages = min(max_pages, (total + 99) // 100)
    print(f"[ea_scraper] {total} players across {total_pages} pages")

    for page in range(2, total_pages + 1):
        time.sleep(delay)
        batch, _ = fetch_page(page)
        if not batch:
            print(f"[ea_scraper] Empty page {page}, stopping")
            break
        all_players.extend(batch)
        if page % 10 == 0:
            print(f"[ea_scraper] Progress: {len(all_players)}/{total}")

    # Cache to disk
    with open(PLAYERS_CACHE_FILE, "w") as f:
        json.dump(all_players, f)
    print(f"[ea_scraper] Done — {len(all_players)} players cached.")
    return all_players


def load_cached_players() -> list[dict]:
    """Load players from disk cache if available."""
    if PLAYERS_CACHE_FILE.exists():
        with open(PLAYERS_CACHE_FILE) as f:
            return json.load(f)
    return []


def get_all_players(force_refresh: bool = False) -> list[dict]:
    """
    Return all EA players. Uses disk cache if fresh (< 48h), else re-fetches.
    This is the main entry point used by the rest of the app.
    """
    import time as _time
    if not force_refresh and PLAYERS_CACHE_FILE.exists():
        age = _time.time() - PLAYERS_CACHE_FILE.stat().st_mtime
        if age < CACHE_TTL_SQUAD * 2:  # 48h TTL
            return load_cached_players()

    return fetch_all_players()


def search_player_ea(name: str, club: str = "") -> Optional[dict]:
    """
    Search for a player in the EA dataset by name.
    Loads from cache. Falls back to fetching page 1 only if cache is cold.
    """
    players = load_cached_players()
    if not players:
        players, _ = fetch_page(1)

    name_lower = name.lower()
    last = name_lower.split()[-1]

    candidates = [p for p in players if last in p.get("name", "").lower()]
    if club:
        club_filtered = [p for p in candidates if club.lower().split()[0] in p.get("club_name", "").lower()]
        if club_filtered:
            candidates = club_filtered

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.get("overall", 0))


def get_club_players_ea(club_name: str) -> list[dict]:
    """Return all EA-rated players for a club from cache."""
    players = load_cached_players()
    if not players:
        return []
    term = club_name.lower().split()[0]
    return [p for p in players if term in p.get("club_name", "").lower()]


# ── EA team ID registry ───────────────────────────────────────────────────────
# Populated on first call to get_ea_team_id_map() from ratingsFilters.
_TEAM_ID_MAP: dict = {}        # lowercase club label → ea int id
_TEAM_ID_PRIORITY: dict = {}   # top-5 men's leagues only (preferred)
_TEAM_ID_CACHE = Path(CACHE_DIR) / "ea_team_ids.json"
_TEAM_ID_PRIORITY_CACHE = Path(CACHE_DIR) / "ea_team_ids_priority.json"


def get_ea_team_id_map() -> dict:
    """Return a {lowercase_club_label: ea_team_id} mapping from EA ratingsFilters.
    
    Men's top-5 league teams take priority over women's teams to avoid
    EA team ID collisions (e.g. Real Madrid men vs Real Madrid women).
    """
    global _TEAM_ID_MAP, _TEAM_ID_PRIORITY
    if _TEAM_ID_MAP:
        return _TEAM_ID_MAP

    # Try disk cache
    if _TEAM_ID_CACHE.exists():
        with open(_TEAM_ID_CACHE) as f:
            _TEAM_ID_MAP = json.load(f)
        if _TEAM_ID_PRIORITY_CACHE.exists():
            with open(_TEAM_ID_PRIORITY_CACHE) as f:
                _TEAM_ID_PRIORITY = json.load(f)
        return _TEAM_ID_MAP

    # Men's top-5 leagues: group IDs from EA ratingsFilters
    # (Premier League, La Liga, Bundesliga, Serie A, Ligue 1)
    TOP_5_LEAGUE_LABELS = {
        "premier league", "laliga ea sports", "ea sports fc bundesliga",
        "bundesliga", "serie a", "ligue 1 uber eats", "ligue 1",
        "la liga", "seria a",
    }

    try:
        resp = SESSION.get(EA_RATINGS_URL, timeout=20)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', resp.text, re.DOTALL)
        if not m:
            return {}
        data = json.loads(m.group(1))
        team_groups = data["props"]["pageProps"]["ratingsFilters"]["teamGroups"]

        # Two-pass: first index all, then overwrite with top-5 men's leagues
        result = {}
        priority = {}
        for group in team_groups:
            group_label = group.get("label", "").lower()
            is_top5 = any(label in group_label for label in TOP_5_LEAGUE_LABELS)
            for team in (group.get("teams") or []):
                label = team.get("label", "").lower()
                tid = team.get("id")
                if label and tid:
                    result[label] = tid        # may be overwritten
                    if is_top5:
                        priority[label] = tid  # top-5 wins any collision

        result.update(priority)  # top-5 overwrite women's/lower leagues
        _TEAM_ID_MAP = result
        _TEAM_ID_PRIORITY = priority
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        with open(_TEAM_ID_CACHE, "w") as f:
            json.dump(result, f)
        with open(_TEAM_ID_PRIORITY_CACHE, "w") as f:
            json.dump(priority, f)
        return result
    except Exception:
        return {}


def fetch_club_players_live(tm_club_name: str) -> list[dict]:
    """
    Fetch all EA-rated players for a club using the ?team= filter.
    Falls back to name-based filtering of cached players.

    tm_club_name: Club name as returned by Transfermarkt (e.g. "Arsenal FC")
    Returns list of normalised EA player dicts.
    """
    # Build team ID map
    get_ea_team_id_map()  # ensures _TEAM_ID_MAP and _TEAM_ID_PRIORITY are loaded
    team_map = _TEAM_ID_MAP
    priority_map = _TEAM_ID_PRIORITY  # top-5 men's leagues only

    _ABBR = {
        "utd": "united", "fc": "", "afc": "", "cf": "", "sc": "", "ac": "",
        "hotspur": "spurs", "wanderers": "", "athletic": "",
        "man": "manchester",
        "wolves": "wolverhampton",
        "spurs": "tottenham",
        "villa": "aston villa",
        "bvb": "dortmund",
        "psg": "paris",
    }
    def _norm_label(s: str) -> str:
        tokens = []
        for t in s.lower().split():
            tokens.append(_ABBR.get(t, t))
        return " ".join(t for t in tokens if t).strip()

    def _best_match(search_map: dict) -> tuple:
        name_norm = _norm_label(tm_club_name)
        name_tokens = set(name_norm.split())
        best_id = None
        best_score = -1
        for label, tid in search_map.items():
            label_norm = _norm_label(label)
            if label_norm == name_norm:
                return tid, 200.0  # exact match wins immediately
            label_tokens = set(label_norm.split())
            shared = name_tokens & label_tokens
            if not shared:
                continue
            union = name_tokens | label_tokens
            score = len(shared) / len(union) * 100
            if name_norm in label_norm or label_norm in name_norm:
                score += 20
            if score > best_score:
                best_score = score
                best_id = tid
        return best_id, best_score

    # Search priority map (men's top-5) first, then fall back to full map
    ea_team_id, score = _best_match(priority_map)
    if ea_team_id is None or score < 30:
        ea_team_id, score = _best_match(team_map)
    if score < 30:
        ea_team_id = None

    if ea_team_id is None:
        # Fallback: filter cached players
        return get_club_players_ea(tm_club_name)

    # Check per-club cache
    club_cache = Path(CACHE_DIR) / f"ea_club_{ea_team_id}.json"
    if club_cache.exists():
        age = time.time() - club_cache.stat().st_mtime
        if age < CACHE_TTL_SQUAD * 2:
            with open(club_cache) as f:
                return json.load(f)

    try:
        url = f"{EA_RATINGS_URL}?team={ea_team_id}"
        resp = SESSION.get(url, timeout=20)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', resp.text, re.DOTALL)
        if not m:
            return get_club_players_ea(tm_club_name)
        data = json.loads(m.group(1))
        raw_items = data["props"]["pageProps"]["ratingDetails"]["items"]
        players = [_parse_player(p) for p in raw_items]
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        with open(club_cache, "w") as f:
            json.dump(players, f)
        return players
    except Exception:
        return get_club_players_ea(tm_club_name)
