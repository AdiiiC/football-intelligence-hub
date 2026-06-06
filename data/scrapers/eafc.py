"""
EA FC 26 data layer.

Primary source : Kaggle dataset "rovnez/fc-26-fifa-26-player-data"
                 (FC26_20250921.csv — drop in data/ folder)
Fallback       : Live scrape of sofifa.com via cloudscraper
Image CDN      : cdn.futbin.com/content/fifa25/img/players/{sofifa_id}.png
                 (FutBin CDN serves images by SoFIFA ID and is publicly accessible)
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import SCRAPER_HEADERS, CACHE_DIR, CACHE_TTL_SQUAD

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path("data")
KAGGLE_CSV_CANDIDATES = [
    DATA_DIR / "FC26_20250921.csv",
    DATA_DIR / "fc26_players.csv",
    DATA_DIR / "male_players.csv",
    DATA_DIR / "eafc26_players.csv",
]

# FutBin CDN — serves player face images by SoFIFA numeric ID
FUTBIN_IMG_BASE = "https://cdn.futbin.com/content/fifa25/img/players"
FUTBIN_CARD_BASE = "https://cdn.futbin.com/content/fifa25/img/cards"

# Standard/gold card background image IDs on FutBin CDN
CARD_BG_URLS = {
    "TOTY":   f"{FUTBIN_CARD_BASE}/711.png",
    "IF":     f"{FUTBIN_CARD_BASE}/3.png",
    "GOLD":   f"{FUTBIN_CARD_BASE}/1.png",
    "SILVER": f"{FUTBIN_CARD_BASE}/2.png",
    "BRONZE": f"{FUTBIN_CARD_BASE}/5.png",
}

# ---------------------------------------------------------------------------
# Column mappings from Kaggle dataset → our internal names
# ---------------------------------------------------------------------------
KAGGLE_COL_MAP = {
    "sofifa_id":               "ea_id",
    "short_name":              "short_name",
    "long_name":               "name",
    "player_positions":        "positions_raw",
    "overall":                 "overall",
    "potential":               "potential",
    "value_eur":               "value_eur",
    "wage_eur":                "wage_eur",
    "age":                     "age",
    "dob":                     "dob",
    "height_cm":               "height_cm",
    "weight_kg":               "weight_kg",
    "club_name":               "club_name",
    "league_name":             "league_name",
    "league_level":            "league_level",
    "nationality_name":        "nationality",
    "preferred_foot":          "preferred_foot",
    "weak_foot":               "weak_foot",
    "skill_moves":             "skill_moves",
    "pace":                    "pac",
    "shooting":                "sho",
    "passing":                 "pas",
    "dribbling":               "dri",
    "defending":               "def_",
    "physic":                  "phy",
    # Sub-attributes
    "attacking_crossing":      "crossing",
    "attacking_finishing":     "finishing",
    "attacking_heading_accuracy": "heading_accuracy",
    "attacking_short_passing": "short_passing",
    "attacking_volleys":       "volleys",
    "skill_dribbling":         "dribbling_skill",
    "skill_curve":             "curve",
    "skill_fk_accuracy":       "fk_accuracy",
    "skill_long_passing":      "long_passing",
    "skill_ball_control":      "ball_control",
    "movement_acceleration":   "acceleration",
    "movement_sprint_speed":   "sprint_speed",
    "movement_agility":        "agility",
    "movement_reactions":      "reactions",
    "movement_balance":        "balance",
    "power_shot_power":        "shot_power",
    "power_jumping":           "jumping",
    "power_stamina":           "stamina",
    "power_strength":          "strength",
    "power_long_shots":        "long_shots",
    "mentality_aggression":    "aggression",
    "mentality_interceptions": "interceptions_attr",
    "mentality_positioning":   "positioning",
    "mentality_vision":        "vision",
    "mentality_penalties":     "penalties",
    "mentality_composure":     "composure",
    "defending_marking_awareness": "marking",
    "defending_standing_tackle":   "standing_tackle",
    "defending_sliding_tackle":    "sliding_tackle",
    "goalkeeping_diving":      "gk_diving",
    "goalkeeping_handling":    "gk_handling",
    "goalkeeping_kicking":     "gk_kicking",
    "goalkeeping_positioning": "gk_positioning",
    "goalkeeping_reflexes":    "gk_reflexes",
    "goalkeeping_speed":       "gk_speed",
    "release_clause_eur":      "release_clause_eur",
    "player_face_url":         "player_face_url",   # if present in dataset
}


# ---------------------------------------------------------------------------
# Global in-memory store
# ---------------------------------------------------------------------------
_eafc_df: Optional[pd.DataFrame] = None


def _load_kaggle_csv() -> Optional[pd.DataFrame]:
    """Load the local Kaggle CSV if present, rename columns, add image URL."""
    for path in KAGGLE_CSV_CANDIDATES:
        if path.exists():
            try:
                df = pd.read_csv(path, low_memory=False)
                # Rename known columns
                rename_map = {k: v for k, v in KAGGLE_COL_MAP.items() if k in df.columns}
                df = df.rename(columns=rename_map)

                # Build FutBin image URL from sofifa_id / ea_id
                id_col = "ea_id" if "ea_id" in df.columns else None
                if id_col:
                    df["face_url"] = df[id_col].apply(
                        lambda x: f"{FUTBIN_IMG_BASE}/{int(x)}.png" if pd.notna(x) else ""
                    )

                # Market value in millions
                if "value_eur" in df.columns:
                    df["market_value_m"] = (df["value_eur"] / 1_000_000).round(2)
                if "wage_eur" in df.columns:
                    df["wage_k"] = (df["wage_eur"] / 1_000).round(1)

                return df
            except Exception as e:
                print(f"[eafc] CSV load error: {e}")
    return None


def get_eafc_df() -> Optional[pd.DataFrame]:
    """Return the EA FC DataFrame (cached globally)."""
    global _eafc_df
    if _eafc_df is None:
        _eafc_df = _load_kaggle_csv()
    return _eafc_df


def lookup_player_eafc(name: str, club: str = "") -> Optional[dict]:
    """
    Look up a player in the EA FC dataset by name (and optionally club).
    Returns dict of EA attributes or None.
    """
    df = get_eafc_df()
    if df is None:
        return None

    name_lower = name.lower()
    last = name_lower.split()[-1] if name_lower else ""

    # Try exact short name first
    name_col = next((c for c in ["short_name", "name"] if c in df.columns), None)
    if not name_col:
        return None

    mask = df[name_col].str.lower().str.contains(last, na=False)
    matches = df[mask]

    if club and not matches.empty:
        club_mask = matches.get("club_name", pd.Series(dtype=str)).str.lower().str.contains(
            club.lower().split()[0], na=False
        )
        club_matches = matches[club_mask]
        if not club_matches.empty:
            matches = club_matches

    if matches.empty:
        return None

    # Return best overall match
    if "overall" in matches.columns:
        matches = matches.sort_values("overall", ascending=False)

    return matches.iloc[0].to_dict()


def get_face_url(sofifa_id) -> str:
    """Return FutBin CDN face image URL for a given SoFIFA player ID."""
    if not sofifa_id or pd.isna(sofifa_id):
        return ""
    return f"{FUTBIN_IMG_BASE}/{int(sofifa_id)}.png"


def get_card_bg_url(tier: str) -> str:
    """Return FutBin card background image URL for a card tier."""
    return CARD_BG_URLS.get(tier, CARD_BG_URLS["GOLD"])


def get_club_squad_eafc(club_name: str) -> list[dict]:
    """
    Return all players for a club from the EA FC dataset.
    Used as a cross-reference for attributes.
    """
    df = get_eafc_df()
    if df is None or "club_name" not in df.columns:
        return []

    mask = df["club_name"].str.lower().str.contains(
        club_name.lower().split()[0], na=False
    )
    club_df = df[mask]
    if club_df.empty:
        return []

    return club_df.to_dict(orient="records")


def enrich_with_eafc(player: dict) -> dict:
    """
    Merge EA FC attributes into a player dict from TM/FBref.
    Adds: overall, pac, sho, pas, dri, def_, phy, face_url, ea_id, all sub-attrs.
    """
    ea = lookup_player_eafc(
        player.get("name", ""),
        player.get("club_name", player.get("squad", ""))
    )
    if not ea:
        return player

    enriched = dict(player)
    # Merge EA attrs — don't overwrite existing TM data like market_value_m
    ea_fields = [
        "ea_id", "overall", "potential", "pac", "sho", "pas", "dri", "def_", "phy",
        "face_url", "wage_k", "preferred_foot", "weak_foot", "skill_moves",
        "height_cm", "weight_kg", "release_clause_eur",
        "crossing", "finishing", "heading_accuracy", "short_passing", "volleys",
        "dribbling_skill", "curve", "fk_accuracy", "long_passing", "ball_control",
        "acceleration", "sprint_speed", "agility", "reactions", "balance",
        "shot_power", "jumping", "stamina", "strength", "long_shots",
        "aggression", "interceptions_attr", "positioning", "vision", "penalties",
        "composure", "marking", "standing_tackle", "sliding_tackle",
        "gk_diving", "gk_handling", "gk_kicking", "gk_positioning",
        "gk_reflexes", "gk_speed",
    ]
    for field in ea_fields:
        if field in ea and ea[field] is not None:
            # Only set face_url from EA if TM photo is missing
            if field == "face_url" and enriched.get("photo_url"):
                enriched["ea_face_url"] = ea[field]
            else:
                enriched[field] = ea[field]

    return enriched


def search_players_for_position(
    position_group: str,
    league: Optional[str] = None,
    min_overall: int = 70,
    max_age: int = 28,
    max_value_m: float = 200.0,
    top_n: int = 20,
) -> list[dict]:
    """
    Search the EA FC dataset for players matching position + filters.
    Returns list of player dicts sorted by overall rating.
    """
    df = get_eafc_df()
    if df is None:
        return []

    from config.settings import POSITION_GROUPS

    target_codes = POSITION_GROUPS.get(position_group, [])
    if not target_codes:
        return []

    pos_col = next((c for c in ["positions_raw", "player_positions"] if c in df.columns), None)
    if not pos_col:
        return []

    # Filter by position codes
    pos_mask = df[pos_col].apply(
        lambda x: any(code in str(x).upper().split(",") for code in target_codes)
        if pd.notna(x) else False
    )
    result = df[pos_mask].copy()

    # Filter by overall
    if "overall" in result.columns:
        result = result[result["overall"] >= min_overall]

    # Filter by age
    if "age" in result.columns:
        result = result[result["age"] <= max_age]

    # Filter by market value
    if "market_value_m" in result.columns:
        result = result[result["market_value_m"] <= max_value_m]

    # Filter by league
    if league and "league_name" in result.columns:
        # Exclude players already in target league (look for reinforcements elsewhere)
        pass  # kept open: caller can filter

    # Add face URLs
    if "ea_id" in result.columns:
        result["face_url"] = result["ea_id"].apply(
            lambda x: f"{FUTBIN_IMG_BASE}/{int(x)}.png" if pd.notna(x) else ""
        )

    # Sort
    if "overall" in result.columns:
        result = result.sort_values("overall", ascending=False)

    return result.head(top_n).to_dict(orient="records")


def dataset_available() -> bool:
    """Returns True if the Kaggle CSV is present locally."""
    return any(p.exists() for p in KAGGLE_CSV_CANDIDATES)
