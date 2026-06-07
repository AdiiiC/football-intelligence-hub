"""
FBref scraper — advanced per-90 stats and percentile ranks.
Uses the soccerdata library where possible, with direct scraping fallback.
"""

import time
import json
import re
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

from config.settings import SCRAPER_HEADERS, CACHE_DIR, CACHE_TTL_STATS, FBREF_STAT_COLS

BASE_URL = "https://fbref.com"

STAT_PAGES = {
    "standard":   "/en/comps/{league_id}/stats/players/{league_id}-Stats",
    "shooting":   "/en/comps/{league_id}/shooting/players/{league_id}-Shooting",
    "passing":    "/en/comps/{league_id}/passing/players/{league_id}-Passing",
    "defense":    "/en/comps/{league_id}/defense/players/{league_id}-Defensive-Actions",
    "possession": "/en/comps/{league_id}/possession/players/{league_id}-Possession",
    "misc":       "/en/comps/{league_id}/misc/players/{league_id}-Miscellaneous-Stats",
}

SESSION = requests.Session()
SESSION.headers.update(SCRAPER_HEADERS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    p = Path(CACHE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def _load_cache(key: str, ttl: int) -> Optional[list]:
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


def _get_html(url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=20)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            if resp.status_code == 429:
                time.sleep(30)
            time.sleep(3 + attempt * 2)
        except Exception:
            time.sleep(5)
    return None


def _parse_fbref_table(soup: BeautifulSoup, table_id: str) -> pd.DataFrame:
    table = soup.find("table", {"id": table_id})
    if not table:
        return pd.DataFrame()
    try:
        df = pd.read_html(str(table), header=[0, 1])[0]
        df.columns = [
            f"{b}" if a.startswith("Unnamed") else f"{a}_{b}"
            for a, b in df.columns
        ]
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_league_stats(league_id: str, season: str = "2024-2025") -> pd.DataFrame:
    """
    Fetch all player stats for a league from FBref.
    Merges standard + shooting + passing + defense + possession tables.
    Returns a merged DataFrame with per-90 stats.
    """
    cache_key = f"fbref_league_{league_id}_{season.replace('-','_')}"
    cached = _load_cache(cache_key, CACHE_TTL_STATS)
    if cached:
        return pd.DataFrame(cached)

    dfs = {}
    for stat_type, path_tmpl in STAT_PAGES.items():
        path = path_tmpl.format(league_id=league_id)
        url = f"{BASE_URL}{path}"
        soup = _get_html(url)
        if not soup:
            continue
        # FBref table IDs follow patterns like "stats_standard_{league_id}"
        table_id = f"stats_{stat_type}_{league_id}"
        df = _parse_fbref_table(soup, table_id)
        if not df.empty:
            dfs[stat_type] = df
        time.sleep(4)  # FBref rate-limit courtesy

    if not dfs:
        return pd.DataFrame()

    # Merge on player name + squad
    base = dfs.get("standard", pd.DataFrame())
    if base.empty:
        return pd.DataFrame()

    # Identify key columns for merging
    name_col = next((c for c in base.columns if "player" in c), None)
    squad_col = next((c for c in base.columns if "squad" in c), None)
    if not name_col or not squad_col:
        return pd.DataFrame()

    merged = base
    for stat_type, df in dfs.items():
        if stat_type == "standard":
            continue
        nc = next((c for c in df.columns if "player" in c), None)
        sc = next((c for c in df.columns if "squad" in c), None)
        if nc and sc:
            df = df.rename(columns={nc: name_col, sc: squad_col})
            # Drop duplicated columns before merge
            dup_cols = [c for c in df.columns if c in merged.columns and c not in [name_col, squad_col]]
            df = df.drop(columns=dup_cols, errors="ignore")
            merged = merged.merge(df, on=[name_col, squad_col], how="left", suffixes=("", f"_{stat_type}"))

    # Clean: remove header rows, convert numeric
    merged = merged[merged[name_col] != "Player"].copy()
    for col in merged.columns:
        if col not in [name_col, squad_col]:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged.fillna(0)
    merged = merged.rename(columns={name_col: "player_name", squad_col: "squad"})

    result = merged.to_dict(orient="records")
    _save_cache(cache_key, result)
    return merged


def get_player_stats(player_name: str, league_id: str, season: str = "2024-2025") -> dict:
    """
    Get stats for a specific player from the league-wide stats table.
    Returns dict of stat_name → value.
    """
    df = get_league_stats(league_id, season)
    if df.empty:
        return {}

    name_col = "player_name"
    if name_col not in df.columns:
        return {}

    # Fuzzy match on name using rapidfuzz if available
    try:
        from rapidfuzz import process, fuzz
        names = df[name_col].tolist()
        match = process.extractOne(player_name, names, scorer=fuzz.token_sort_ratio, score_cutoff=70)
        if not match:
            return {}
        matched_name = match[0]
        row = df[df[name_col] == matched_name].iloc[0]
    except ImportError:
        mask = df[name_col].str.lower().str.contains(player_name.lower(), na=False)
        matches = df[mask]
        if matches.empty:
            return {}
        row = matches.iloc[0]

    return row.to_dict()


# Map our internal radar stat keys → possible FBref column name fragments
# FBref renames headers between seasons; we fuzzy-match by substring
# ---------------------------------------------------------------------------
# UCL Stats — FBref competition ID 8
# ---------------------------------------------------------------------------
UCL_FBREF_ID = "8"
UCL_SEASON = "2024-2025"

# Key per-90 stats to extract for UCL peer comparison (column fragments)
_UCL_KEY_STATS = {
    "xg_per90":       ["xg_per90", "xg"],
    "npxg_per90":     ["npxg_per90", "npxg"],
    "xga_per90":      ["xg_assist_per90", "xa_per90", "xga"],
    "goals_per90":    ["goals_per90", "gls"],
    "assists_per90":  ["assists_per90", "ast"],
    "shots_per90":    ["sh_per90", "shots"],
    "key_passes_per90": ["kp", "key_passes"],
    "prog_passes_per90": ["prgp", "progressive_passes"],
    "prog_carries_per90": ["prgc", "progressive_carries"],
    "tackles_per90":  ["tkl", "tackles"],
    "interceptions_per90": ["int", "interceptions"],
    "save_pct":       ["save_pct", "sv%"],
    "pressures_per90": ["press", "pressures"],
}

# Domestic league FBref comp IDs
DOMESTIC_COMP_IDS = {
    "EPL":        "9",
    "La_liga":    "12",
    "Bundesliga": "20",
    "Serie_A":    "11",
    "Ligue_1":    "13",
}

# Defensive stats to extract per player (fixes CB/FB Understat gap)
_DOMESTIC_DEF_STATS = {
    "tackles_per90":             ["tkl", "tackles"],
    "tackles_won":               ["tkl_w", "tackles_won"],
    "interceptions_per90":       ["int", "interceptions"],
    "blocks_per90":              ["blocks", "blk"],
    "aerial_duels_won_pct":      ["won%", "aerial_won_pct", "won_pct"],
    "pressures_per90":           ["press", "pressures"],
    "errors_per90":              ["err", "errors"],
    "progressive_passes_per90":  ["prgp", "progressive_passes"],
    "crosses_into_pen_per90":    ["crs_pa", "crosses_into_pen"],
    "prog_carries_per90":        ["prgc", "progressive_carries"],
    "key_passes_per90":          ["kp", "key_passes"],
    "xg_per90":                  ["xg_per90", "xg"],
    "xga_per90":                 ["xag", "xg_assist", "xa"],
    "goals_per90":               ["gls", "goals"],
    "assists_per90":             ["ast", "assists"],
    "save_pct":                  ["save_pct", "sv%"],
}


def get_domestic_player_stats(league: str, season: str = "2024-2025") -> list:
    """
    Fetch per-player defensive + key stats from FBref domestic league pages.
    Covers Standard + Defense + Passing pages to fill CB/FB gap left by Understat.
    Cached 48h. Returns list of dicts keyed by player_name.

    league: Understat league key (EPL, La_liga, Bundesliga, Serie_A, Ligue_1)
    """
    comp_id = DOMESTIC_COMP_IDS.get(league)
    if not comp_id:
        return []

    cache_key = f"fbref_domestic_{league}_{season.replace('-','_')}"
    cached = _load_cache(cache_key, 86400 * 2)
    if cached is not None:
        return cached

    pages_needed = ["standard", "defense", "passing", "possession"]
    dfs = {}
    for stat_type in pages_needed:
        path_tmpl = STAT_PAGES.get(stat_type)
        if not path_tmpl:
            continue
        url = f"{BASE_URL}{path_tmpl.format(league_id=comp_id)}"
        soup = _get_html(url)
        if not soup:
            continue
        table_id = f"stats_{stat_type}_{comp_id}"
        df = _parse_fbref_table(soup, table_id)
        if not df.empty:
            dfs[stat_type] = df
        time.sleep(5)

    if not dfs:
        return []

    base = dfs.get("standard", pd.DataFrame())
    if base.empty:
        return []

    name_col  = next((c for c in base.columns if "player" in c.lower()), None)
    squad_col = next((c for c in base.columns if "squad" in c.lower()), None)
    pos_col   = next((c for c in base.columns if c.lower() in ("pos", "position")), None)
    min_col   = next((c for c in base.columns if "min" in c.lower() and "playing" not in c.lower()), None)
    if not name_col:
        return []

    # Merge all pages
    merged = base.copy()
    for stat_type, df in dfs.items():
        if stat_type == "standard":
            continue
        nc = next((c for c in df.columns if "player" in c.lower()), None)
        sc = next((c for c in df.columns if "squad" in c.lower()), None)
        if nc and sc:
            df = df.rename(columns={nc: name_col, sc: squad_col})
            dup = [c for c in df.columns if c in merged.columns and c not in [name_col, squad_col]]
            df = df.drop(columns=dup, errors="ignore")
            merged = merged.merge(df, on=[name_col, squad_col], how="left", suffixes=("", f"_{stat_type}"))

    merged = merged[merged[name_col] != "Player"].copy()
    for col in merged.columns:
        if col not in (name_col, squad_col, pos_col):
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)

    result = []
    for _, row in merged.iterrows():
        pname = str(row.get(name_col, "")).strip()
        if not pname:
            continue
        minutes = float(row.get(min_col, 0)) if min_col else 0
        if minutes < 90:
            continue
        per90 = max(minutes / 90, 1)

        entry = {
            "player_name": pname,
            "squad":       str(row.get(squad_col, "")) if squad_col else "",
            "position":    str(row.get(pos_col, "")) if pos_col else "",
            "minutes":     int(minutes),
            "league":      league,
        }
        for stat_key, fragments in _DOMESTIC_DEF_STATS.items():
            val = 0.0
            for frag in fragments:
                col = _resolve_col(frag, merged)
                if col and col in row.index:
                    raw = float(row[col]) if row[col] else 0
                    if "per90" in stat_key and stat_key != "save_pct" and stat_key != "aerial_duels_won_pct":
                        val = round(raw / per90, 3)
                    else:
                        val = round(raw, 3)
                    break
            entry[stat_key] = val
        result.append(entry)

    _save_cache(cache_key, result)
    return result


def get_domestic_team_stats(league: str, season: str = "2024-2025") -> dict:
    """
    Fetch team-level aggregate stats from FBref for playstyle detection.
    Returns dict of team_name → {possession_pct, progressive_passes, crosses, aerials_won, pressures, ppda_proxy}
    Cached 48h.
    """
    comp_id = DOMESTIC_COMP_IDS.get(league)
    if not comp_id:
        return {}

    cache_key = f"fbref_team_{league}_{season.replace('-','_')}"
    cached = _load_cache(cache_key, 86400 * 2)
    if cached is not None:
        return cached

    # FBref team stats page
    url = f"{BASE_URL}/en/comps/{comp_id}/stats/squads/{comp_id}-Stats"
    soup = _get_html(url)
    if not soup:
        return {}

    table_id = f"stats_squads_standard_for"
    df = _parse_fbref_table(soup, table_id)
    if df.empty:
        # Try alternate table id
        tables = soup.find_all("table")
        for t in tables:
            try:
                df = pd.read_html(str(t), header=[0, 1])[0]
                df.columns = [f"{b}" if a.startswith("Unnamed") else f"{a}_{b}" for a, b in df.columns]
                df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
                if len(df) > 5:
                    break
            except Exception:
                continue

    if df.empty:
        return {}

    squad_col = next((c for c in df.columns if "squad" in c.lower()), None)
    poss_col  = next((c for c in df.columns if "poss" in c.lower()), None)
    if not squad_col:
        return {}

    result = {}
    for _, row in df.iterrows():
        team = str(row.get(squad_col, "")).strip()
        if not team or team == "Squad":
            continue
        poss = float(row.get(poss_col, 50)) if poss_col else 50
        prgp = float(_resolve_col("prgp", df) and row.get(_resolve_col("prgp", df), 0) or 0)
        prgc = float(_resolve_col("prgc", df) and row.get(_resolve_col("prgc", df), 0) or 0)
        result[team] = {
            "possession_pct": poss,
            "progressive_passes": prgp,
            "progressive_carries": prgc,
        }

    _save_cache(cache_key, result)
    return result


def _resolve_col(fragment: str, df: pd.DataFrame):
    """Find first column containing fragment (case-insensitive)."""
    fl = fragment.lower()
    for c in df.columns:
        if fl == c.lower() or fl in c.lower():
            return c
    return None


def get_ucl_player_stats(season: str = UCL_SEASON) -> list:
    """
    Return per-player UCL stats for a season as a list of dicts.
    Uses FBref standard stats (comp ID 8). Cached 7 days.
    Keys: player_name, squad, position, minutes, xg_per90, goals_per90, etc.
    """
    cache_key = f"ucl_stats_{season.replace('-','_')}"
    cached = _load_cache(cache_key, 86400 * 7)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/en/comps/{UCL_FBREF_ID}/stats/players/{UCL_FBREF_ID}-Stats"
    soup = _get_html(url)
    if not soup:
        return []

    table_id = f"stats_standard_{UCL_FBREF_ID}"
    df = _parse_fbref_table(soup, table_id)
    if df.empty:
        return []

    # Clean header rows
    name_col = next((c for c in df.columns if "player" in c.lower()), None)
    pos_col  = next((c for c in df.columns if c.lower() in ("pos", "position")), None)
    squad_col= next((c for c in df.columns if "squad" in c.lower()), None)
    min_col  = next((c for c in df.columns if c.lower() in ("min", "minutes", "playing time_min")), None)

    if not name_col:
        return []

    df = df[df[name_col] != "Player"].copy()
    df = df.rename(columns={name_col: "player_name"})

    # Convert numeric
    for col in df.columns:
        if col not in ("player_name", pos_col, squad_col):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    result = []
    for _, row in df.iterrows():
        pname = str(row.get("player_name", "")).strip()
        if not pname:
            continue
        minutes = float(row.get(min_col, 0)) if min_col else 0
        if minutes < 90:  # ignore fringe appearances
            continue
        per90 = max(minutes / 90, 1)
        entry = {
            "player_name": pname,
            "squad":       str(row.get(squad_col, "")) if squad_col else "",
            "position":    str(row.get(pos_col, "")) if pos_col else "",
            "minutes":     int(minutes),
        }
        # Extract key stats
        for stat_key, fragments in _UCL_KEY_STATS.items():
            val = 0.0
            for frag in fragments:
                col = _resolve_col(frag, df)
                if col and col in row.index:
                    raw = float(row[col]) if row[col] else 0
                    # Normalize rate stats to per-90 if not already
                    if "per90" in stat_key and stat_key != "save_pct":
                        val = round(raw / per90, 3) if raw else 0
                    else:
                        val = round(raw, 3)
                    break
            entry[stat_key] = val
        result.append(entry)

    _save_cache(cache_key, result)
    return result


_STAT_KEY_ALIASES = {
    "goals_per90":               ["gls", "goals_per90", "gls_per90"],
    "assists_per90":             ["ast", "assists_per90", "ast_per90"],
    "xg_per90":                  ["xg_per90", "xg", "expected_xg"],
    "xg_assist_per90":           ["xag", "xg_assist", "xag_per90", "xa_per90"],
    "npxg_per90":                ["npxg_per90", "npxg"],
    "progressive_carries":       ["prg_c", "progressive_carries", "prgc"],
    "progressive_passes":        ["prg_p", "progressive_passes", "prgp"],
    "pressures":                 ["press", "pressures"],
    "aerial_duels_won_pct":      ["aerial_won", "aerial_pct", "won_pct"],
    "tackles_won":               ["tkl_w", "tackles_won", "tkl"],
    "interceptions":             ["int", "interceptions"],
    "passes_completed_pct":      ["cmp_pct", "passes_completed_pct", "cmp%"],
    "dribbles_completed_pct":    ["succ_pct", "dribbles_completed_pct", "att_drib"],
    "shots_on_target_pct":       ["sot_pct", "sot%", "shots_on_target_pct"],
    "key_passes_per90":          ["kp", "key_passes", "kp_per90"],
    "crosses_into_penalty_area": ["crs_pa", "crosses_into_penalty"],
    "touches_att_pen_area":      ["touch_att_pen", "att_pen"],
    "blocks":                    ["blocks", "blk"],
    "errors":                    ["err", "errors"],
    "save_pct":                  ["save_pct", "save%", "sv%"],
    "psxg_difference":           ["psxg", "psxg_difference", "+/-"],
    "passes_launched_pct":       ["launch_pct", "passes_launched"],
    "crosses_stopped_pct":       ["stp_pct", "crosses_stopped"],
    "def_actions_outside_pen_area": ["def_act", "opa"],
}

# Position groups → FBref "pos" substrings used for peer filtering
_POS_FBREF_MAP = {
    "GK":     ["GK"],
    "CB":     ["CB", "DF"],
    "FB":     ["LB", "RB", "WB", "DF"],
    "DM":     ["DM", "MF", "CM"],
    "CM":     ["CM", "MF"],
    "AM":     ["AM", "MF", "CM"],
    "Winger": ["LW", "RW", "MF", "AM"],
    "ST":     ["FW", "CF", "ST"],
}


def _resolve_stat(stat_key: str, player_stats: dict, league_df: pd.DataFrame):
    """Return (player_value, peer_series) for a stat key, matching aliases against available columns."""
    aliases = _STAT_KEY_ALIASES.get(stat_key, [stat_key])
    df_cols_lower = {c.lower(): c for c in league_df.columns}

    for alias in aliases:
        # exact match
        if alias in df_cols_lower:
            col = df_cols_lower[alias]
            val = player_stats.get(col) or player_stats.get(alias, 0)
            return float(val or 0), league_df[col].dropna()
        # substring match
        for col_lower, col in df_cols_lower.items():
            if alias in col_lower:
                val = player_stats.get(col) or player_stats.get(alias, 0)
                return float(val or 0), league_df[col].dropna()
    return None, None


def get_player_percentiles(player_stats: dict, position_group: str, league_df: pd.DataFrame) -> dict:
    """
    Compute percentile rank for each radar stat key vs positional peers in the league.
    Returns dict of stat_key → percentile (0-100).
    """
    if league_df.empty or not player_stats:
        return {}

    # Filter peer pool by position group when a pos column exists
    peers = league_df
    pos_col = next((c for c in league_df.columns if c.lower() in ("pos", "position")), None)
    if pos_col:
        target_pos_substrs = _POS_FBREF_MAP.get(position_group, [])
        if target_pos_substrs:
            mask = peers[pos_col].fillna("").str.upper().apply(
                lambda p: any(s in p for s in target_pos_substrs)
            )
            filtered = peers[mask]
            if len(filtered) >= 5:   # only filter if we get a usable sample
                peers = filtered

    percentiles = {}
    for stat_key in _STAT_KEY_ALIASES:
        val, peer_series = _resolve_stat(stat_key, player_stats, peers)
        if val is None or peer_series is None or len(peer_series) == 0:
            continue
        pct = float((peer_series < val).sum() / len(peer_series) * 100)
        percentiles[stat_key] = round(pct, 1)

    return percentiles


def get_player_shot_data(player_id_fbref: str) -> list[dict]:
    """
    Scrape shot-level data for a player from FBref shot log.
    Returns list of shot dicts with location, xG, outcome.
    """
    cache_key = f"shots_{player_id_fbref}"
    cached = _load_cache(cache_key, CACHE_TTL_STATS)
    if cached:
        return cached

    url = f"{BASE_URL}/en/players/{player_id_fbref}/shooting"
    soup = _get_html(url)
    if not soup:
        return []

    shots = []
    table = soup.find("table", {"id": re.compile(r"shots_")})
    if not table:
        return shots

    for row in table.find_all("tr"):
        tds = row.find_all("td")
        if not tds or len(tds) < 10:
            continue
        try:
            def _td(i): return tds[i].get_text(strip=True) if i < len(tds) else ""
            shots.append({
                "minute": _td(1),
                "result": _td(3),
                "shot_type": _td(6),
                "xg": float(_td(7)) if _td(7) else 0.0,
                "psxg": float(_td(8)) if _td(8) else 0.0,
                "x": float(_td(10)) if _td(10) else None,
                "y": float(_td(11)) if _td(11) else None,
            })
        except Exception:
            continue

    _save_cache(cache_key, shots)
    return shots
