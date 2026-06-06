"""
Squad fetcher — aggregates data from Transfermarkt + EA Ratings
into a unified player object used across the app.
FBref/Understat enrichment is deferred to the Player Profile page
to keep initial squad loads fast (< 5 seconds).
"""

import json
from pathlib import Path

from data.scrapers import transfermarkt as tm
from data.scrapers.ea_ratings import fetch_club_players_live
from config.settings import POSITION_GROUPS, CACHE_DIR, CACHE_TTL_SQUAD, TOP_5_LEAGUES
import time


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


def _normalize_position(raw_pos: str) -> str:
    """Map verbose Transfermarkt position string to short code."""
    mapping = {
        "goalkeeper": "GK",
        "centre-back": "CB", "center-back": "CB",
        "left-back": "LB", "right-back": "RB",
        "left wing-back": "LWB", "right wing-back": "RWB",
        "defensive midfield": "DM", "central midfield": "CM",
        "attacking midfield": "AM",
        "left midfield": "LM", "right midfield": "RM",
        "left winger": "LW", "right winger": "RW",
        "centre-forward": "ST", "center-forward": "ST",
        "second striker": "CF",
    }
    return mapping.get(raw_pos.lower().strip(), raw_pos.upper()[:3])


def _position_group(pos_code: str) -> str:
    for group, codes in POSITION_GROUPS.items():
        if pos_code in codes:
            return group
    return "Other"


def get_enriched_squad(club_slug: str, club_id: str, league_name: str) -> list[dict]:
    """
    Returns enriched squad: Transfermarkt squad + EA FC attributes.
    Fast path — no FBref/Understat calls here (those are loaded per-player
    in the Player Profile page only).
    """
    cache_key = f"enriched_{club_id}"
    cached = _load_cache(cache_key, CACHE_TTL_SQUAD)
    if cached:
        return cached

    # 1. Base squad from Transfermarkt
    squad = tm.get_squad(club_slug, club_id)
    if not squad:
        return []

    # 2. Fetch all EA players for this club via the ?team= filter (fast, ~1 request)
    ea_players = fetch_club_players_live(club_slug.replace("-", " "))

    # 3. Fetch Understat league stats (single POST, returns xG/xA/goals per player)
    understat_stats = {}
    try:
        from data.scrapers.understat import get_league_player_stats
        from config.settings import TOP_5_LEAGUES
        us_league = TOP_5_LEAGUES.get(league_name, {}).get("understat_name", "")
        if us_league:
            us_players = get_league_player_stats(us_league, "2025")
            import unicodedata as _ud
            _CHAR_MAP_US = str.maketrans({
                "Ø":"O","ø":"o","Æ":"AE","æ":"ae","Þ":"TH","þ":"th",
                "Ð":"D","ð":"d","ß":"ss","Œ":"OE","œ":"oe",
            })
            def _us_norm(s):
                s = s.translate(_CHAR_MAP_US)
                return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
            for up in us_players:
                minutes = max(int(up.get("time", 1)), 1)
                per90 = minutes / 90
                understat_stats[_us_norm(up.get("player_name", ""))] = {
                    "xg_per90":         up.get("xg_per90",  0.0),
                    "xga_per90":        up.get("xa_per90",  0.0),
                    "npxg_per90":       up.get("npxg_per90", 0.0),
                    "goals_per90":      round(float(up.get("goals",   0)) / per90, 3),
                    "assists_per90":    round(float(up.get("assists",  0)) / per90, 3),
                    "shots_per90":      round(float(up.get("shots",   0)) / per90, 3),
                    "key_passes_per90": round(float(up.get("key_passes", 0)) / per90, 3),
                    "us_minutes": minutes,
                    "us_games":   int(up.get("games", 0)),
                }
    except Exception:
        pass

    # Build multiple lookup indexes for robust matching
    def _norm(s):
        """Lowercase + strip accents for fuzzy matching."""
        import unicodedata
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

    # Index: every token in EA name → player (handles "Gabriel", "Vinícius Jr.", etc.)
    ea_by_token = {}
    for ep in ea_players:
        ep_norm = _norm(ep.get("name", ""))
        for token in ep_norm.split():
            if len(token) >= 3:  # skip short tokens like "jr", "de"
                ea_by_token.setdefault(token, []).append(ep)
    # Also index by full normalised name
    ea_by_full = {_norm(ep.get("name", "")): ep for ep in ea_players}

    def _find_ea_match(tm_name):
        """Multi-strategy TM name → EA player match."""
        nm = _norm(tm_name)
        # 1. Exact full name
        if nm in ea_by_full:
            return ea_by_full[nm]
        # 2. EA name contained in TM name or vice versa
        for en, ep in ea_by_full.items():
            if en and (en in nm or nm in en):
                return ep
        # 3. Last token of TM name in EA index
        tokens = nm.split()
        if tokens:
            last = tokens[-1]
            candidates = ea_by_token.get(last, [])
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                # Prefer the one that shares the most tokens
                best = max(candidates, key=lambda ep: sum(
                    1 for t in tokens if t in _norm(ep.get("name", ""))
                ))
                return best
        # 4. First token of TM name (single-name players like "Gabriel")
        if tokens:
            first = tokens[0]
            candidates = ea_by_token.get(first, [])
            if candidates:
                return candidates[0]
        return None

    # 4. Merge
    # Build Understat lookup indexes once before the merge loop
    import unicodedata as _ud2
    _CHAR_MAP2 = str.maketrans({
        "Ø":"O","ø":"o","Æ":"AE","æ":"ae","Þ":"TH","þ":"th",
        "Ð":"D","ð":"d","ß":"ss","Œ":"OE","œ":"oe",
    })
    def _us_norm2(s):
        s = s.translate(_CHAR_MAP2)
        return _ud2.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

    # Index 1: full normalized name → stats
    # Index 2: last token (surname) → list of (full_key, stats) for fallback
    us_by_full = {}
    us_by_last = {}
    for us_key, us_val in understat_stats.items():
        us_by_full[us_key] = us_val
        last_tok = us_key.split()[-1] if us_key else ""
        us_by_last.setdefault(last_tok, []).append((us_key, us_val))

    def _find_us_match(name):
        nm = _us_norm2(name)
        # 1. Exact full name
        if nm in us_by_full:
            return us_by_full[nm]
        # 2. Understat name contained in TM name or vice versa
        for uk, uv in us_by_full.items():
            if uk and (uk in nm or nm in uk):
                return uv
        # 3. Surname match — pick entry with most shared tokens
        tokens = nm.split()
        if tokens:
            last = tokens[-1]
            candidates = us_by_last.get(last, [])
            if len(candidates) == 1:
                return candidates[0][1]
            if len(candidates) > 1:
                best = max(candidates, key=lambda kv: sum(1 for t in tokens if t in kv[0]))
                return best[1]
        return None

    enriched = []
    for player in squad:
        pos_code = _normalize_position(player.get("position", ""))
        pos_group = _position_group(pos_code)

        ea_match = _find_ea_match(player["name"])

        enriched_player = {**player, "position_code": pos_code, "position_group": pos_group}
        if ea_match:
            # Overlay EA attributes (don't overwrite name/age/market_value from TM)
            for key in ("overall", "pac", "sho", "pas", "dri", "def_", "phy",
                        "acceleration", "sprint_speed", "finishing", "shot_power",
                        "long_shots", "volleys", "penalties", "vision", "crossing",
                        "fk_accuracy", "short_passing", "long_passing", "curve",
                        "agility", "balance", "reactions", "ball_control",
                        "dribbling_skill", "composure", "interceptions_attr",
                        "heading_accuracy", "marking", "standing_tackle",
                        "sliding_tackle", "jumping", "stamina", "strength",
                        "aggression", "positioning",
                        "gk_diving", "gk_handling", "gk_kicking",
                        "gk_positioning", "gk_reflexes",
                        "skill_moves", "weak_foot", "preferred_foot",
                        "play_styles", "ea_avatar_url", "ea_shield_url",
                        "sofifa_face_url", "futbin_face_url",
                        "ea_id", "height_cm", "weight_kg",
                        "club_logo_url", "nat_flag_url"):
                val = ea_match.get(key)
                if val is not None:
                    enriched_player[key] = val
            # Use TM age if available, else EA
            if not enriched_player.get("age"):
                enriched_player["age"] = ea_match.get("age")

        # Attach Understat per-90 stats
        if understat_stats:
            us_match = _find_us_match(player.get("name", ""))
            if us_match:
                enriched_player["understat"] = us_match
                for stat in ("xg_per90", "xga_per90", "npxg_per90", "goals_per90",
                             "assists_per90", "shots_per90", "key_passes_per90"):
                    if stat in us_match:
                        enriched_player[stat] = us_match[stat]

        enriched.append(enriched_player)

    _save_cache(cache_key, enriched)
    return enriched


def get_clubs_for_league(league_name: str) -> list[dict]:
    """Load clubs from leagues.json for the given league."""
    leagues_file = Path("config/leagues.json")
    if not leagues_file.exists():
        return []
    with open(leagues_file) as f:
        data = json.load(f)
    return data.get(league_name, [])
