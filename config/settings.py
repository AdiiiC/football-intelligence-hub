"""
Global settings and configuration for Football Intelligence Hub.
"""

# ---------------------------------------------------------------------------
# League & Club Configuration
# ---------------------------------------------------------------------------
TOP_5_LEAGUES = {
    "Premier League": {
        "transfermarkt_id": "GB1",
        "fbref_id": "9",
        "understat_name": "EPL",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    },
    "La Liga": {
        "transfermarkt_id": "ES1",
        "fbref_id": "12",
        "understat_name": "La_liga",
        "flag": "🇪🇸",
    },
    "Bundesliga": {
        "transfermarkt_id": "L1",
        "fbref_id": "20",
        "understat_name": "Bundesliga",
        "flag": "🇩🇪",
    },
    "Serie A": {
        "transfermarkt_id": "IT1",
        "fbref_id": "11",
        "understat_name": "Serie_A",
        "flag": "🇮🇹",
    },
    "Ligue 1": {
        "transfermarkt_id": "FR1",
        "fbref_id": "13",
        "understat_name": "Ligue_1",
        "flag": "🇫🇷",
    },
}

# ---------------------------------------------------------------------------
# HTTP Headers (rotate to reduce scraping blocks)
# ---------------------------------------------------------------------------
SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
CACHE_TTL_SQUAD = 86_400       # 24 hours
CACHE_TTL_TRANSFERS = 3_600    # 1 hour
CACHE_TTL_STATS = 172_800      # 48 hours
CACHE_TTL_MARKET = 86_400      # 24 hours

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
CACHE_DIR = "data/cache"
MODEL_DIR = "models/artifacts"

# ---------------------------------------------------------------------------
# FBref stat columns used across the app
# ---------------------------------------------------------------------------
FBREF_STAT_COLS = [
    "goals_per90", "assists_per90", "xg_per90", "xg_assist_per90",
    "progressive_carries", "progressive_passes", "pressures",
    "aerial_duels_won_pct", "tackles_won", "interceptions",
    "passes_completed_pct", "dribbles_completed_pct",
]

# ---------------------------------------------------------------------------
# Position groups (for squad analysis)
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
