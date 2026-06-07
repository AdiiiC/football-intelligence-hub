"""
Squad weakness analyzer and buy/sell recommender.
"""

from typing import Optional
import pandas as pd
import numpy as np

from config.settings import POSITION_GROUPS, STRENGTH_THRESHOLD, WEAKNESS_THRESHOLD


# ---------------------------------------------------------------------------
# Key radar stats per position group (FBref column name fragments)
# ---------------------------------------------------------------------------
POSITION_RADAR_STATS = {
    "GK": ["save_pct", "psxg_difference", "passes_launched_pct", "crosses_stopped_pct", "def_actions_outside_pen_area"],
    "CB": ["blocks", "interceptions", "tackles_won", "aerial_duels_won_pct", "progressive_passes", "errors"],
    "FB": ["progressive_carries", "crosses_into_penalty_area", "tackles_won", "interceptions", "assists_per90", "progressive_passes"],
    "DM": ["pressures", "tackles_won", "interceptions", "passes_completed_pct", "progressive_passes", "aerial_duels_won_pct"],
    "CM": ["progressive_passes", "passes_completed_pct", "xg_assist_per90", "pressures", "progressive_carries", "tackles_won"],
    "AM": ["xg_per90", "xg_assist_per90", "progressive_carries", "dribbles_completed_pct", "key_passes_per90", "shots_on_target_pct"],
    "Winger": ["xg_per90", "dribbles_completed_pct", "progressive_carries", "crosses_into_penalty_area", "xg_assist_per90", "touches_att_pen_area"],
    "ST": ["xg_per90", "goals_per90", "shots_on_target_pct", "aerial_duels_won_pct", "progressive_carries", "npxg_per90"],
}

SELL_CRITERIA_WEIGHTS = {
    "contract_expiring_1yr":  4,
    "contract_expiring_2yr":  2,
    "below_peer_25th":        3,   # per stat below 25th pct vs same-pos peers
    "yoy_decline":            2,   # year-over-year xG/90 drop >25%
    "high_value_peak_window": 2,   # MV ≥ 30M and age ≥ 28
    "squad_surplus":          1,   # positional depth > ideal
    "playstyle_mismatch":     2,   # player style conflicts with team system
}

# Key Understat stats available per position for peer comparison
# GK/CB/FB defensive stats not in Understat → fall back to EA overall percentile
_POS_US_STATS = {
    "GK":     [],                                         # Understat has no GK defensive stats
    "CB":     [],                                         # same
    "FB":     ["key_passes_per90", "xga_per90"],
    "DM":     ["key_passes_per90"],
    "CM":     ["key_passes_per90", "xg_per90"],
    "AM":     ["xg_per90", "xga_per90", "key_passes_per90"],
    "Winger": ["xg_per90", "xga_per90", "key_passes_per90"],
    "ST":     ["xg_per90", "npxg_per90", "goals_per90"],
}

# Key UCL stats to compare per position (from fbref.get_ucl_player_stats)
_POS_UCL_STATS = {
    "GK":     ["save_pct"],
    "CB":     ["tackles_per90", "interceptions_per90", "pressures_per90"],
    "FB":     ["tackles_per90", "interceptions_per90", "key_passes_per90"],
    "DM":     ["tackles_per90", "interceptions_per90", "pressures_per90"],
    "CM":     ["prog_passes_per90", "key_passes_per90", "xg_per90"],
    "AM":     ["xg_per90", "xga_per90", "key_passes_per90"],
    "Winger": ["xg_per90", "xga_per90", "prog_carries_per90"],
    "ST":     ["xg_per90", "npxg_per90", "goals_per90"],
}

# FBref pos strings → position group
_FBREF_POS_MAP = {
    "GK": "GK",
    "CB": "CB", "DF": "CB",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "DM": "DM",
    "CM": "CM", "MF": "CM",
    "AM": "AM",
    "LW": "Winger", "RW": "Winger",
    "FW": "ST", "CF": "ST",
}

# Understat position token → our group
_US_POS_MAP = {
    "GK": "GK", "D": "CB", "DC": "CB", "DL": "FB", "DR": "FB",
    "WBL": "FB", "WBR": "FB", "DM": "DM", "DMC": "DM",
    "MC": "CM", "M": "CM", "MR": "CM", "ML": "CM",
    "AMC": "AM", "AM": "AM", "AML": "Winger", "AMR": "Winger",
    "FW": "ST", "F": "ST", "S": "ST", "ST": "ST",
}

# Ideal positional squad depth (sell if above)
_IDEAL_DEPTH = {"GK": 2, "CB": 4, "FB": 4, "DM": 2, "CM": 3, "AM": 2, "Winger": 4, "ST": 3}


# ── EA PlayStyles → team archetype mapping ─────────────────────────────────
_PLAYSTYLE_CATEGORIES = {
    "possession":     {"Incisive Pass", "Technical", "Whipped Pass", "Pinged Pass", "Tiki Taka"},
    "high_press":     {"Press Proven", "Relentless", "Intercept", "Slide Tackle"},
    "counter_attack": {"Rapid", "First Touch", "Long Ball Pass", "Long Throw"},
    "physical":       {"Aerial+", "Power Header", "Bruiser", "Jockey"},
    "creative":       {"Flair", "Trickster", "Trivela", "Chip Shot"},
}

# Tags a player in each position should have to fit the team's dominant style
_STYLE_POS_REQUIREMENTS = {
    "possession": {
        "GK":     ["Pinged Pass"],
        "CB":     ["Pinged Pass", "Technical"],
        "FB":     ["Whipped Pass", "Pinged Pass"],
        "DM":     ["Technical", "Intercept"],
        "CM":     ["Incisive Pass", "Technical", "Whipped Pass"],
        "AM":     ["Technical", "Incisive Pass"],
        "Winger": ["Technical", "Tiki Taka"],
        "ST":     ["First Touch", "Technical"],
    },
    "high_press": {
        "GK":     [],
        "CB":     ["Intercept", "Slide Tackle"],
        "FB":     ["Slide Tackle", "Relentless"],
        "DM":     ["Intercept", "Slide Tackle", "Relentless"],
        "CM":     ["Press Proven", "Relentless"],
        "AM":     ["Press Proven", "Relentless"],
        "Winger": ["Press Proven", "Rapid"],
        "ST":     ["Press Proven", "Relentless"],
    },
    "counter_attack": {
        "GK":     ["Long Throw"],
        "CB":     [],
        "FB":     ["Rapid"],
        "DM":     [],
        "CM":     ["Long Ball Pass", "First Touch"],
        "AM":     ["First Touch", "Rapid"],
        "Winger": ["Rapid", "Long Ball Pass"],
        "ST":     ["Rapid", "First Touch"],
    },
    "physical": {
        "GK":     ["Aerial+"],
        "CB":     ["Aerial+", "Bruiser", "Power Header"],
        "FB":     [],
        "DM":     ["Aerial+", "Jockey"],
        "CM":     ["Aerial+", "Bruiser"],
        "AM":     [],
        "Winger": [],
        "ST":     ["Aerial+", "Power Header", "Bruiser"],
    },
    "creative": {
        "GK":     [],
        "CB":     [],
        "FB":     ["Flair"],
        "DM":     [],
        "CM":     ["Flair", "Trivela"],
        "AM":     ["Flair", "Trickster", "Trivela"],
        "Winger": ["Flair", "Trickster"],
        "ST":     ["Flair", "Chip Shot"],
    },
}

_STYLE_LABELS = {
    "possession":     "Possession / Technical",
    "high_press":     "High Press / Gegenpressing",
    "counter_attack": "Counter-Attack / Direct",
    "physical":       "Physical / Aerial",
    "creative":       "Creative / Fluid",
}


def _fbref_team_scores(team_name: str, league: str, season: str = "2024-2025") -> dict:
    """
    Derive archetype scores (0-100) from FBref team stats.
    Tries to match team_name to FBref squad names via partial matching.
    """
    try:
        from data.scrapers.fbref import get_domestic_team_stats
        team_stats = get_domestic_team_stats(league, season)
    except Exception:
        return {}
    if not team_stats:
        return {}

    # Fuzzy-match team name
    import unicodedata
    def _n(s): return unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower().strip()
    t_norm = _n(team_name)
    matched = None
    for fbref_team in team_stats:
        if _n(fbref_team) == t_norm or t_norm in _n(fbref_team) or _n(fbref_team) in t_norm:
            matched = fbref_team
            break
    if not matched:
        return {}

    stats = team_stats[matched]
    poss = stats.get("possession_pct", 50)
    prgp = stats.get("progressive_passes", 0)
    prgc = stats.get("progressive_carries", 0)

    # Normalize to 0-100 scores per archetype
    return {
        "possession":     min(100, max(0, (poss - 40) * 3.33)),    # 40%→0, 70%→100
        "high_press":     min(100, max(0, prgp / 3)),               # proxy via prog passes
        "counter_attack": min(100, max(0, prgc / 2)),               # proxy via prog carries
        "physical":       50,                                        # no direct FBref signal
        "creative":       50,                                        # no direct FBref signal
    }


def _understat_situation_scores(team_name: str, league: str, season: str = "2025") -> dict:
    """
    Derive archetype scores from Understat team situation xG splits.
    Returns dict of archetype → 0-100 score.
    """
    try:
        from data.scrapers.understat import get_league_player_stats
        players = get_league_player_stats(league, season)
    except Exception:
        return {}
    if not players:
        return {}

    import unicodedata
    def _n(s): return unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower().strip()
    t_norm = _n(team_name)
    team_players = [p for p in players if t_norm in _n(p.get("team", "")) or _n(p.get("team", "")) in t_norm]
    if not team_players:
        return {}

    # Understat gives situation xG in player-level data — we aggregate team totals
    # key_passes and xG proxy open play; no direct counter/set-piece splits in player API
    total_xg = sum(float(p.get("xg_per90", 0) or 0) * max(int(p.get("time", 0) or 0) / 90, 1) for p in team_players)
    total_xa = sum(float(p.get("xa_per90", 0) or 0) * max(int(p.get("time", 0) or 0) / 90, 1) for p in team_players)
    n = max(len(team_players), 1)

    return {
        "possession":     min(100, (total_xa / n) * 100),   # high chance creation → possession
        "high_press":     50,
        "counter_attack": 50,
        "physical":       50,
        "creative":       min(100, (total_xa / n) * 120),
    }


def determine_team_playstyle(squad: list, team_name: str = "", league: str = "") -> dict:
    """
    3-source blended playstyle detection:
      50% FBref domestic team stats
      30% EA FC PlayStyle tags (existing logic)
      20% Understat situation xG (proxy)
    Returns {dominant, scores, description, conflicts, sources}.
    """
    n = len(squad)
    if n == 0:
        return {"dominant": "unknown", "scores": {}, "description": "Insufficient data", "conflicts": [], "sources": {}}

    # ── Source 1: EA PlayStyle tags (30%) ─────────────────────────────────────
    counts = {k: 0 for k in _PLAYSTYLE_CATEGORIES}
    for player in squad:
        tags = set(player.get("play_styles") or [])
        for cat, cat_tags in _PLAYSTYLE_CATEGORIES.items():
            if tags & cat_tags:
                counts[cat] += 1
    ea_scores = {k: round(v / n * 100, 1) for k, v in counts.items()}

    # ── Source 2: FBref team stats (50%) ──────────────────────────────────────
    us_league = league  # Understat league name
    fbref_scores = _fbref_team_scores(team_name, us_league) if team_name and us_league else {}

    # ── Source 3: Understat situation xG (20%) ────────────────────────────────
    us_scores = _understat_situation_scores(team_name, us_league) if team_name and us_league else {}

    # ── Blend ─────────────────────────────────────────────────────────────────
    archetypes = list(_PLAYSTYLE_CATEGORIES.keys())
    blended = {}
    sources_used = {"ea": True, "fbref": bool(fbref_scores), "understat": bool(us_scores)}
    for arch in archetypes:
        ea  = ea_scores.get(arch, 0)
        fb  = fbref_scores.get(arch, ea)   # fall back to EA if FBref missing
        us  = us_scores.get(arch, ea)      # fall back to EA if Understat missing
        if fbref_scores and us_scores:
            blended[arch] = round(0.50 * fb + 0.30 * ea + 0.20 * us, 1)
        elif fbref_scores:
            blended[arch] = round(0.65 * fb + 0.35 * ea, 1)
        else:
            blended[arch] = ea

    dominant = max(blended, key=lambda k: blended[k]) if blended else "unknown"

    # ── Conflict detection ────────────────────────────────────────────────────
    conflicts = []
    if fbref_scores:
        for arch in archetypes:
            ea_v  = ea_scores.get(arch, 0)
            fb_v  = fbref_scores.get(arch, 0)
            delta = abs(ea_v - fb_v)
            if delta > 30:
                if ea_v > fb_v:
                    conflicts.append(
                        f"EA tags suggest **{_STYLE_LABELS[arch]}** ({ea_v:.0f}) but FBref shows low signal ({fb_v:.0f}) "
                        f"— squad built for this style but manager may not be using it"
                    )
                else:
                    conflicts.append(
                        f"FBref confirms **{_STYLE_LABELS[arch]}** ({fb_v:.0f}) but EA tags are low ({ea_v:.0f}) "
                        f"— tactical system exceeds what individual player profiles suggest"
                    )

    return {
        "dominant":    dominant,
        "scores":      blended,
        "ea_scores":   ea_scores,
        "fbref_scores": fbref_scores,
        "description": _STYLE_LABELS.get(dominant, dominant),
        "conflicts":   conflicts,
        "sources":     sources_used,
    }


def _playstyle_fit(player: dict, team_style: dict) -> tuple:
    """
    Returns (score 0–100, label str) for how well a player fits the team style.
    """
    dominant = team_style.get("dominant", "unknown")
    pos_group = player.get("position_group", "")
    player_tags = set(player.get("play_styles") or [])
    desc = team_style.get("description", dominant)
    required = _STYLE_POS_REQUIREMENTS.get(dominant, {}).get(pos_group, [])
    if not required:
        return 65, "Style match neutral (no specific tag requirement for position)"
    matches = sum(1 for tag in required if tag in player_tags)
    score = round(matches / len(required) * 100)
    if score >= 67:
        return score, f"Strong fit for {desc} system"
    elif score >= 34:
        return score, f"Partial fit for {desc} — some style attributes missing"
    return score, f"Style mismatch: {desc} system needs different play attributes"


def _get_top6_teams(us_players: list) -> set:
    """Infer top-6 teams by total Understat xG (strong proxy for league table position)."""
    team_xg: dict = {}
    for p in us_players:
        team = p.get("team", "")
        xg = float(p.get("xG", 0) or 0)
        team_xg[team] = team_xg.get(team, 0) + xg
    return set(sorted(team_xg, key=lambda t: -team_xg[t])[:6])


def _us_norm_name(s: str) -> str:
    import unicodedata
    _MAP = str.maketrans({"Ø":"O","ø":"o","Æ":"AE","æ":"ae","ß":"ss"})
    s = s.translate(_MAP)
    return unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower().strip()


def _peer_percentile(player_val: float, peer_vals: list) -> float:
    """Return percentile rank of player_val within peer_vals (0–100)."""
    if not peer_vals:
        return 50.0
    return sum(1 for v in peer_vals if v < player_val) / len(peer_vals) * 100


def recommend_sales(squad: list, us_league: str = "") -> list:
    """
    Sell candidate scoring with tenure-aware analysis.
      t >= 2 yrs: successive-season YoY + top-6 league peer comparison + UCL stats
      t >= 1 yr:  current-season stats + playstyle compatibility check + UCL stats
      t < 1 yr:   only contract & age/value signals (too early to judge)
    EA card rating is NOT used as a sell signal.
    """
    from collections import Counter
    import re
    from datetime import date

    current_year = date.today().year

    # ── Understat (3 seasons for multi-year YoY) ──────────────────────────────
    peers_2025: list = []
    peers_2024: list = []
    peers_2023: list = []
    if us_league:
        try:
            from data.scrapers.understat import get_league_player_stats
            peers_2025 = get_league_player_stats(us_league, "2025")
            peers_2024 = get_league_player_stats(us_league, "2024")
            peers_2023 = get_league_player_stats(us_league, "2023")
        except Exception:
            pass

    # ── Top-6 teams by total xG (proxy for league table) ──────────────────────
    top6_teams: set = _get_top6_teams(peers_2025) if peers_2025 else set()

    # ── UCL peers ──────────────────────────────────────────────────────────────
    ucl_peers: list = []
    try:
        from data.scrapers.fbref import get_ucl_player_stats
        ucl_peers = get_ucl_player_stats()
    except Exception:
        pass

    ucl_by_pos: dict = {}
    for up in ucl_peers:
        pos_str = up.get("position", "")
        pg = next((_FBREF_POS_MAP.get(t) for t in pos_str.upper().split(",") if _FBREF_POS_MAP.get(t)), None)
        if pg:
            ucl_by_pos.setdefault(pg, []).append(up)

    ucl_by_name: dict = {}
    for up in ucl_peers:
        ucl_by_name[_us_norm_name(up.get("player_name", ""))] = up

    # ── Team playstyle from EA tags ────────────────────────────────────────────
    team_style = determine_team_playstyle(squad)

    def _get_peers(pos_group: str, season_players: list,
                   min_minutes: int = 450, teams_filter: set = None) -> list:
        result = []
        for p in season_players:
            if teams_filter and p.get("team", "") not in teams_filter:
                continue
            toks = p.get("position", "").split()
            pg = next((_US_POS_MAP.get(t.upper()) for t in toks if _US_POS_MAP.get(t.upper())), None)
            if pg == pos_group and int(p.get("time", 0)) >= min_minutes:
                result.append(p)
        return result

    pos_counts = Counter(p.get("position_group", "Other") for p in squad)

    sell_candidates = []
    for player in squad:
        score = 0
        reasons = []

        age = int(player.get("age", 0)) if str(player.get("age", "0")).isdigit() else 0
        mv = player.get("market_value_m", 0) or 0
        contract = player.get("contract_expiry", "")
        pos_group = player.get("position_group", "")
        overall = player.get("overall") or 0
        us_data = player.get("understat") or {}
        us_minutes = us_data.get("us_minutes", 0)
        name_norm = _us_norm_name(player.get("name", ""))

        # Years at current club (None when joined_year not yet scraped)
        joined_year = player.get("joined_year")
        years_at_club = (current_year - int(joined_year)) if joined_year else None

        # ── Skip if only/essential player in position ──────────────────────
        if pos_counts.get(pos_group, 0) <= 1:
            continue

        # ── Contract expiry (always applies) ──────────────────────────────
        m = re.search(r"(\d{4})", str(contract))
        if m:
            expiry = int(m.group(1))
            years_left = expiry - current_year
            if years_left <= 1:
                score += SELL_CRITERIA_WEIGHTS["contract_expiring_1yr"]
                reasons.append(f"Contract expires {expiry} — sell now or lose on a free")
            elif years_left <= 2:
                score += SELL_CRITERIA_WEIGHTS["contract_expiring_2yr"]
                reasons.append(f"Contract expires {expiry} — sell within 2 years at peak value")

        # ── Stat & style signals (gated on tenure) ────────────────────────
        # t < 1 year: skip — too soon to judge a new signing on stats
        if years_at_club is None or years_at_club >= 1:

            # t >= 2 yrs: compare vs top-6 peers; otherwise full league
            use_top6 = years_at_club is not None and years_at_club >= 2
            peer_filter = top6_teams if use_top6 else None
            peer_label  = "top-6 league" if use_top6 else "league"

            # ── Domestic stat comparison ───────────────────────────────────
            us_stat_keys = _POS_US_STATS.get(pos_group, [])
            if us_minutes >= 450 and us_stat_keys and peers_2025:
                pos_peers = _get_peers(pos_group, peers_2025, teams_filter=peer_filter)
                for stat_key in us_stat_keys:
                    player_val = player.get(stat_key) or 0
                    peer_vals = [p.get(stat_key, 0) or 0 for p in pos_peers]
                    if len(peer_vals) >= 5:
                        pct = _peer_percentile(player_val, peer_vals)
                        if pct < 25:
                            score += SELL_CRITERIA_WEIGHTS["below_peer_25th"]
                            lbl = stat_key.replace("_per90", "").replace("_", " ").upper()
                            reasons.append(
                                f"Below-average {lbl} vs {peer_label} same-position peers "
                                f"({pct:.0f}th percentile, {player_val:.2f}/90)"
                            )
                            break

            # ── UCL peer comparison (latest season only) ───────────────────
            ucl_stat_keys = _POS_UCL_STATS.get(pos_group, [])
            ucl_pos_peers = ucl_by_pos.get(pos_group, [])
            player_ucl = ucl_by_name.get(name_norm)

            if ucl_stat_keys and ucl_pos_peers:
                if player_ucl and (player_ucl.get("minutes") or 0) >= 180:
                    for stat_key in ucl_stat_keys:
                        player_val = player_ucl.get(stat_key) or 0
                        peer_vals = [
                            p.get(stat_key) or 0
                            for p in ucl_pos_peers if (p.get("minutes") or 0) >= 180
                        ]
                        if len(peer_vals) >= 4:
                            pct = _peer_percentile(player_val, peer_vals)
                            if pct >= 75:
                                score -= 2  # UCL-level performer — strong keep
                                lbl = stat_key.replace("_per90", "").replace("_", " ").upper()
                                reasons.append(
                                    f"UCL performer: {lbl} at {pct:.0f}th pct vs UCL peers — strong keep"
                                )
                                break
                            elif pct < 25:
                                score += SELL_CRITERIA_WEIGHTS["below_peer_25th"]
                                lbl = stat_key.replace("_per90", "").replace("_", " ").upper()
                                reasons.append(
                                    f"Below UCL median {lbl} ({pct:.0f}th pct vs UCL peers)"
                                )
                                break

            # ── Playstyle compatibility (t >= 1 year) ─────────────────────
            fit_score, fit_label = _playstyle_fit(player, team_style)
            if fit_score < 34:
                score += SELL_CRITERIA_WEIGHTS["playstyle_mismatch"]
                reasons.append(fit_label)
            elif fit_score >= 67:
                score -= 1  # style pillar — keep signal
                reasons.append(f"{fit_label} — keep signal")

            # ── Multi-season YoY decline (t >= 2 years) ───────────────────
            if years_at_club is not None and years_at_club >= 2:
                if us_minutes >= 450 and pos_group in ("ST", "Winger", "AM", "CM", "DM") and peers_2024:
                    prev24 = next(
                        (p for p in peers_2024
                         if _us_norm_name(p.get("player_name", "")) == name_norm), None
                    )
                    if prev24:
                        curr_xg = player.get("xg_per90") or 0
                        prev_xg24 = prev24.get("xg_per90") or 0
                        if prev_xg24 > 0.05 and curr_xg < prev_xg24 * 0.75:
                            score += SELL_CRITERIA_WEIGHTS["yoy_decline"]
                            reasons.append(
                                f"xG/90 declined '24→'25: {prev_xg24:.2f}→{curr_xg:.2f} "
                                f"(−{(1 - curr_xg / prev_xg24) * 100:.0f}%)"
                            )
                        # Sustained two-season decline check
                        if peers_2023:
                            prev23 = next(
                                (p for p in peers_2023
                                 if _us_norm_name(p.get("player_name", "")) == name_norm), None
                            )
                            if prev23:
                                prev_xg23 = prev23.get("xg_per90") or 0
                                if prev_xg23 > 0.05 and prev_xg24 < prev_xg23 * 0.75:
                                    score += SELL_CRITERIA_WEIGHTS["yoy_decline"]
                                    reasons.append(
                                        f"Sustained decline '23→'24 too: {prev_xg23:.2f}→{prev_xg24:.2f} — "
                                        "confirmed two-year downward trend"
                                    )

        # ── Peak sell window (always applies) ─────────────────────────────
        if mv >= 30 and age >= 28:
            score += SELL_CRITERIA_WEIGHTS["high_value_peak_window"]
            reasons.append(f"Market value €{mv:.0f}M at age {age} — sell before value decline")

        # ── Squad surplus (always applies) ────────────────────────────────
        ideal = _IDEAL_DEPTH.get(pos_group, 3)
        if pos_counts.get(pos_group, 0) > ideal:
            best_mv = max(
                (p.get("market_value_m") or 0) for p in squad if p.get("position_group") == pos_group
            )
            if (mv or 0) < best_mv:
                score += SELL_CRITERIA_WEIGHTS["squad_surplus"]
                reasons.append(f"Squad surplus at {pos_group} ({pos_counts[pos_group]} players, ideal {ideal})")

        if score > 0:
            sell_candidates.append({
                **player,
                "sell_score": score,
                "sell_reasons": reasons,
                "estimated_sale_fee_m": round(mv * (1.1 if age < 28 else 0.85), 1),
            })

    sell_candidates.sort(key=lambda x: x["sell_score"], reverse=True)
    return sell_candidates


def historical_transfer_grade(player: dict) -> dict:
    """
    Grade a past transfer based on:
      - fee paid vs current market value delta
      - EA overall rating vs squad average at acquisition age

    Returns {grade, label, delta_m, delta_pct, rationale}
    """
    fee_paid = player.get("fee_paid_m") or 0
    current_mv = player.get("market_value_m") or 0

    # Determine delta
    if fee_paid > 0 and current_mv > 0:
        delta_m = current_mv - fee_paid
        delta_pct = (delta_m / fee_paid) * 100
    elif fee_paid == 0 and current_mv > 0:
        # Free transfer that is now valuable
        delta_m = current_mv
        delta_pct = 100.0
    else:
        delta_m = 0.0
        delta_pct = 0.0

    # Grade thresholds (%)
    if delta_pct >= 50:
        grade, label, color = "A+", "Bargain", "#3ddc84"
    elif delta_pct >= 15:
        grade, label, color = "A",  "Good Value", "#2ecc71"
    elif delta_pct >= -10:
        grade, label, color = "B",  "Fair Deal",  "#c9a84c"
    elif delta_pct >= -30:
        grade, label, color = "C",  "Slight Overpay", "#ff8c00"
    else:
        grade, label, color = "D",  "Overpaid", "#e74c3c"

    rationale_parts = []
    if fee_paid > 0:
        rationale_parts.append(f"Paid €{fee_paid:.0f}M → now worth €{current_mv:.0f}M ({delta_pct:+.0f}%)")
    elif current_mv > 0:
        rationale_parts.append(f"Free transfer, now valued at €{current_mv:.0f}M")
    else:
        rationale_parts.append("Insufficient fee/value data to grade")

    return {
        "grade":     grade,
        "label":     label,
        "color":     color,
        "delta_m":   round(delta_m, 1),
        "delta_pct": round(delta_pct, 1),
        "rationale": " | ".join(rationale_parts),
    }


def _get_stat(player: dict, stat: str) -> float:
    """Pull a stat from player top-level, fbref dict, or understat dict."""
    # Check top-level first (promoted from Understat during enrichment)
    top = player.get(stat)
    if top is not None:
        try:
            return float(top)
        except (ValueError, TypeError):
            pass
    fbref = player.get("fbref", {}) or {}
    understat = player.get("understat", {}) or {}
    # Try exact match first
    for d in [fbref, understat]:
        val = d.get(stat)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    # Try partial match in fbref
    for k, v in fbref.items():
        if stat in k:
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
    return 0.0


def _squad_positional_averages(squad: list[dict]) -> dict[str, dict]:
    """Compute per-position-group average stats for the squad."""
    from collections import defaultdict
    group_stats = defaultdict(list)
    for p in squad:
        pg = p.get("position_group", "Other")
        if pg == "Other":
            continue
        stat_vals = {}
        for stat in sum(POSITION_RADAR_STATS.values(), []):
            stat_vals[stat] = _get_stat(p, stat)
        group_stats[pg].append(stat_vals)

    averages = {}
    for pg, player_stats_list in group_stats.items():
        if not player_stats_list:
            continue
        avg = {}
        all_keys = set(k for d in player_stats_list for k in d)
        for k in all_keys:
            vals = [d.get(k, 0) for d in player_stats_list]
            avg[k] = float(np.mean(vals))
        averages[pg] = avg
    return averages


def analyze_squad_weaknesses(squad: list[dict], league_df: pd.DataFrame = None) -> list[dict]:
    """
    Identify weak positions by comparing squad stats to league baseline.
    Returns list of {position_group, weakness_score, weak_stats, recommendation}.
    """
    if league_df is None or league_df.empty:
        return _heuristic_analysis(squad)

    squad_avgs = _squad_positional_averages(squad)
    weaknesses = []

    for pos_group, radar_stats in POSITION_RADAR_STATS.items():
        if pos_group not in squad_avgs:
            continue
        squad_group_avg = squad_avgs[pos_group]
        weak_stats = []
        scores = []

        for stat in radar_stats:
            squad_val = squad_group_avg.get(stat, 0)
            # League percentile of this value
            stat_col = next((c for c in league_df.columns if stat in c), None)
            if stat_col:
                peer_vals = league_df[stat_col].dropna().values
                if len(peer_vals) > 0:
                    pct = float((peer_vals < squad_val).sum() / len(peer_vals) * 100)
                    scores.append(pct)
                    if pct < WEAKNESS_THRESHOLD:
                        weak_stats.append({"stat": stat, "percentile": round(pct, 1)})

        avg_score = float(np.mean(scores)) if scores else 50.0
        weaknesses.append({
            "position_group": pos_group,
            "weakness_score": round(100 - avg_score, 1),
            "weak_stats": weak_stats,
            "priority": "HIGH" if avg_score < WEAKNESS_THRESHOLD else ("MEDIUM" if avg_score < 55 else "LOW"),
        })

    weaknesses.sort(key=lambda x: x["weakness_score"], reverse=True)
    return weaknesses


def _heuristic_analysis(squad: list[dict]) -> list[dict]:
    """Fallback heuristic when no league_df is available."""
    from collections import Counter
    pos_counts = Counter(p.get("position_group", "Other") for p in squad)
    ideal_counts = {"GK": 2, "CB": 4, "FB": 4, "DM": 2, "CM": 3, "AM": 2, "Winger": 4, "ST": 3}
    result = []
    for pos, ideal in ideal_counts.items():
        actual = pos_counts.get(pos, 0)
        deficit = max(0, ideal - actual)
        result.append({
            "position_group": pos,
            "weakness_score": deficit * 20.0,
            "weak_stats": [],
            "priority": "HIGH" if deficit >= 2 else ("MEDIUM" if deficit == 1 else "LOW"),
        })
    result.sort(key=lambda x: x["weakness_score"], reverse=True)
    return result


def recommend_buys(
    weaknesses: list[dict],
    candidate_pool: list[dict] = None,
    budget_m: float = 200.0,
    max_age: int = 27,
    top_n: int = 5,
) -> list[dict]:
    """
    For each weak position, find best-matching candidates from the pool.
    candidate_pool: list of player dicts (from Transfermarkt + stats).
    Returns flat sorted list of recommended players.
    """
    if not candidate_pool:
        return []

    recommendations = []
    seen_names = set()

    high_priority = [w for w in weaknesses if w["priority"] in ("HIGH", "MEDIUM")]

    for weakness in high_priority:
        pos_group = weakness["position_group"]
        radar_stats = POSITION_RADAR_STATS.get(pos_group, [])

        # Filter candidates — skip budget/age checks when data is unavailable
        candidates = [
            p for p in candidate_pool
            if p.get("position_group") == pos_group
            and (p.get("age") is None or (int(p["age"]) <= max_age if str(p["age"]).isdigit() else True))
            and (p.get("market_value_m") is None or p["market_value_m"] <= budget_m)
        ]

        # Score candidates
        scored = []
        for c in candidates:
            score = 0.0
            for stat in radar_stats:
                score += _get_stat(c, stat)
            try:
                age = int(c.get("age", 25))
                score += (28 - age) * 0.5
            except (ValueError, TypeError):
                pass
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        for _, p in scored[:top_n]:
            name = p.get("name", "")
            if name not in seen_names:
                seen_names.add(name)
                recommendations.append({**p, "target_position": pos_group})

    recommendations.sort(key=lambda x: (x.get("overall") or 0, x.get("xg_per90") or 0), reverse=True)
    return recommendations


def fit_analysis(player: dict, club_squad: list[dict], club_name: str) -> dict:
    """
    Generate a fit analysis: where the player will thrive vs. where they must adapt.
    Returns {thrives: [...], must_adapt: [...], overall_fit_score: float}.
    """
    pos_group = player.get("position_group", "")
    radar_stats = POSITION_RADAR_STATS.get(pos_group, [])

    # Club style fingerprint (average of squad stats)
    squad_avgs = _squad_positional_averages(club_squad)
    club_style = squad_avgs.get(pos_group, {})

    thrives = []
    must_adapt = []
    fit_scores = []

    stat_labels = {
        "xg_per90": "Goalscoring (xG/90)",
        "xg_assist_per90": "Chance creation (xA/90)",
        "progressive_carries": "Ball progression",
        "progressive_passes": "Progressive passing",
        "pressures": "Pressing intensity",
        "tackles_won": "Defensive work rate",
        "dribbles_completed_pct": "1v1 dribbling",
        "aerial_duels_won_pct": "Aerial ability",
        "passes_completed_pct": "Passing accuracy",
        "crosses_into_penalty_area": "Crossing",
        "interceptions": "Reading of play",
        "shots_on_target_pct": "Shot accuracy",
    }

    for stat in radar_stats:
        player_val = _get_stat(player, stat)
        club_val = club_style.get(stat, 0)

        if club_val == 0:
            continue

        # How does player compare to what club needs?
        ratio = player_val / club_val if club_val else 1.0
        label = stat_labels.get(stat, stat.replace("_", " ").title())

        if ratio >= 1.2:
            thrives.append(f"**{label}** — exceeds club average ({player_val:.2f} vs {club_val:.2f})")
            fit_scores.append(90)
        elif ratio >= 0.9:
            fit_scores.append(70)
        elif ratio >= 0.6:
            must_adapt.append(f"**{label}** — below club requirement ({player_val:.2f} vs {club_val:.2f})")
            fit_scores.append(45)
        else:
            must_adapt.append(f"**{label}** — significant gap to bridge ({player_val:.2f} vs {club_val:.2f})")
            fit_scores.append(25)

    # ── EA attribute fallback (always runs if stat-based yields < 2 results) ──
    if len(fit_scores) < 2:
        _EA_MAP = [
            ("pac", "Pace / Acceleration"),
            ("sho", "Shooting ability"),
            ("pas", "Passing range"),
            ("dri", "Dribbling & ball control"),
            ("def_", "Defensive positioning"),
            ("phy", "Physical presence"),
        ]
        squad_ea = {}
        for attr, _ in _EA_MAP:
            vals = [float(p.get(attr, 0) or 0) for p in club_squad if p.get(attr)]
            squad_ea[attr] = float(np.mean(vals)) if vals else 0.0

        for attr, label in _EA_MAP:
            player_val = float(player.get(attr, 0) or 0)
            club_val = squad_ea.get(attr, 0)
            if club_val == 0 or player_val == 0:
                continue
            ratio = player_val / club_val
            if ratio >= 1.10:
                thrives.append(
                    f"**{label}** — above squad average ({player_val:.0f} vs {club_val:.0f})"
                )
                fit_scores.append(88)
            elif ratio >= 0.92:
                fit_scores.append(72)
            elif ratio >= 0.80:
                must_adapt.append(
                    f"**{label}** — slightly below squad standard ({player_val:.0f} vs {club_val:.0f})"
                )
                fit_scores.append(50)
            else:
                must_adapt.append(
                    f"**{label}** — significant gap to bridge ({player_val:.0f} vs {club_val:.0f})"
                )
                fit_scores.append(28)

    overall = float(np.mean(fit_scores)) if fit_scores else 60.0

    return {
        "thrives": thrives,
        "must_adapt": must_adapt,
        "overall_fit_score": round(overall, 1),
        "fit_grade": "A" if overall >= 80 else ("B" if overall >= 65 else ("C" if overall >= 50 else "D")),
    }
