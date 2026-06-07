"""
Global settings and configuration for Football Intelligence Hub.
Single source of truth for all IDs, TTLs, paths, and constants.
"""

import os
from pathlib import Path

# Load .env if present (optional — app works without it)
_ENV = Path(__file__).parent.parent / ".env"
if _ENV.exists():
    for line in _ENV.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

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
# HTTP Headers
# ---------------------------------------------------------------------------
SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

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
