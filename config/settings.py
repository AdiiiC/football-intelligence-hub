"""
Global settings and configuration for Football Intelligence Hub.
Single source of truth for all IDs, TTLs, paths, and constants.
"""

import os
import random
from pathlib import Path

# Load .env if present (local dev — optional)
_ENV = Path(__file__).parent.parent / ".env"
if _ENV.exists():
    for line in _ENV.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Load Streamlit secrets if running on Streamlit Cloud
try:
    import streamlit as st
    _secrets = dict(st.secrets)
    for _k, _v in _secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass

# ---------------------------------------------------------------------------
# League & Club Configuration — single source of truth for all IDs
# ---------------------------------------------------------------------------
TOP_5_LEAGUES = {
    "Premier League": {
        "transfermarkt_id": "GB1",
        "fbref_id":         "9",
        "understat_name":   "EPL",
        "flag":             "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    },
    "La Liga": {
        "transfermarkt_id": "ES1",
        "fbref_id":         "12",
        "understat_name":   "La_liga",
        "flag":             "🇪🇸",
    },
    "Bundesliga": {
        "transfermarkt_id": "L1",
        "fbref_id":         "20",
        "understat_name":   "Bundesliga",
        "flag":             "🇩🇪",
    },
    "Serie A": {
        "transfermarkt_id": "IT1",
        "fbref_id":         "11",
        "understat_name":   "Serie_A",
        "flag":             "🇮🇹",
    },
    "Ligue 1": {
        "transfermarkt_id": "FR1",
        "fbref_id":         "13",
        "understat_name":   "Ligue_1",
        "flag":             "🇫🇷",
    },
}

# Reverse lookup helpers
UNDERSTAT_TO_LEAGUE = {v["understat_name"]: k for k, v in TOP_5_LEAGUES.items()}
FBREF_ID_TO_LEAGUE  = {v["fbref_id"]: k for k, v in TOP_5_LEAGUES.items()}
TM_ID_TO_LEAGUE     = {v["transfermarkt_id"]: k for k, v in TOP_5_LEAGUES.items()}

# Current season strings
CURRENT_SEASON_FBREF      = os.environ.get("CURRENT_SEASON_FBREF", "2024-2025")
CURRENT_SEASON_UNDERSTAT  = os.environ.get("CURRENT_SEASON_UNDERSTAT", "2025")
CURRENT_SEASON_TM         = os.environ.get("CURRENT_SEASON_TM", "2024")

# ---------------------------------------------------------------------------
# HTTP Headers — rotating User-Agents to reduce cloud IP blocking
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Chrome on Linux (common cloud UA — keep one to avoid looking suspicious)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

def get_scraper_headers() -> dict:
    """Return headers with a randomly chosen User-Agent."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/",
        "DNT": "1",
    }

# Static headers for backward-compat (scrapers that don't call get_scraper_headers)
SCRAPER_HEADERS = get_scraper_headers()

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
CACHE_TTL_SQUAD     = int(os.environ.get("CACHE_TTL_SQUAD",     86_400))    # 24h
CACHE_TTL_TRANSFERS = int(os.environ.get("CACHE_TTL_TRANSFERS", 3_600))     # 1h
CACHE_TTL_STATS     = int(os.environ.get("CACHE_TTL_STATS",     172_800))   # 48h
CACHE_TTL_MARKET    = int(os.environ.get("CACHE_TTL_MARKET",    86_400))    # 24h

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
CACHE_DIR  = os.environ.get("CACHE_DIR",  "data/cache")
MODEL_DIR  = os.environ.get("MODEL_DIR",  "models/artifacts")

# ---------------------------------------------------------------------------
# FBref stat columns
# ---------------------------------------------------------------------------
FBREF_STAT_COLS = [
    "goals_per90", "assists_per90", "xg_per90", "xg_assist_per90",
    "progressive_carries", "progressive_passes", "pressures",
    "aerial_duels_won_pct", "tackles_won", "interceptions",
    "passes_completed_pct", "dribbles_completed_pct",
]

# ---------------------------------------------------------------------------
POSITION_GROUPS = {
    "GK": ["GK"],
    "CB": ["CB"],
    "FB": ["LB", "RB", "LWB", "RWB"],
    "DM": ["DM", "CDM"],
    "CM": ["CM", "MF"],
    "AM": ["AM", "CAM"],
    "Winger": ["LW", "RW", "LM", "RM"],
    "ST": ["ST", "CF", "FW"],
}

# ---------------------------------------------------------------------------
# Fit analysis thresholds (percentile)
# ---------------------------------------------------------------------------
STRENGTH_THRESHOLD = 70    # above this → "will thrive"
WEAKNESS_THRESHOLD = 40    # below this → "must adapt"
