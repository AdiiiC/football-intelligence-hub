"""
Transfer Targets — squad weakness analysis, buy/sell recommendations, price prediction.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Transfer Targets", page_icon="🎯", layout="wide")

_CSS = ROOT / "ui" / "styles" / "theme.css"
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES, POSITION_GROUPS
from data.fetchers.squad import get_clubs_for_league, get_enriched_squad
from models.squad_analyzer import analyze_squad_weaknesses, recommend_buys, recommend_sales
from data.scrapers.understat import get_league_player_stats
from models.price_predictor import predict_transfer_fee
from ui.components.stat_charts import build_weakness_chart
from ui.components.fifa_card import render_fifa_card, render_card_grid, render_single_card

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎯 Transfer Targets")
    league = st.selectbox("League", list(TOP_5_LEAGUES.keys()))
    clubs = get_clubs_for_league(league)
    club_name = st.selectbox("Club", [c["name"] for c in clubs])
    club = next(c for c in clubs if c["name"] == club_name)

    st.markdown("---")
    st.markdown("**Transfer Budget**")
    budget = st.slider("Max budget (€M)", 0, 250, 80, step=5)
    max_age = st.slider("Max player age", 18, 35, 28)
    top_n = st.slider("Show top N targets", 3, 15, 8)

# ── Load squad ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def load_squad(slug, tid, ln):
    return get_enriched_squad(slug, tid, ln, club_display_name=club_name)


@st.cache_data(ttl=86400 * 2, show_spinner=False)
def load_league_ea_players(ln: str) -> list:
    """Fetch EA players for every club in a league, merge into one list."""
    from data.scrapers.ea_ratings import fetch_club_players_live
    from concurrent.futures import ThreadPoolExecutor, as_completed
    clubs = get_clubs_for_league(ln)
    all_players = {}
    def _fetch(club):
        try:
            return fetch_club_players_live(club["name"])
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_fetch, c): c for c in clubs}
        for fut in as_completed(futures):
            for p in fut.result():
                pid = p.get("ea_id") or p.get("name", "")
                if pid:
                    all_players[pid] = p
    return list(all_players.values())


@st.cache_data(ttl=86400, show_spinner=False)
def load_candidate_pool(ln: str, squad_names: tuple, budget_m: float, max_age_val: int) -> list:
    """Build a transfer candidate pool from Understat league stats, enriched with EA data."""
    import unicodedata

    us_league = TOP_5_LEAGUES.get(ln, {}).get("understat_name", "")
    if not us_league:
        return []
    try:
        us_players = get_league_player_stats(us_league, "2025")
    except Exception:
        return []

    # Load EA data for all clubs in this league (cached separately)
    ea_players = load_league_ea_players(ln)

    _CHAR_MAP = str.maketrans({
        "Ø":"O","ø":"o","Æ":"AE","æ":"ae","Þ":"TH","þ":"th",
        "Ð":"D","ð":"d","ß":"ss","Œ":"OE","œ":"oe",
    })
    def _norm(s):
        s = s.translate(_CHAR_MAP)
        return unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower().strip()

    squad_norms = {_norm(n) for n in squad_names}

    # Build EA lookup indexes
    ea_by_last: dict = {}
    ea_by_full: dict = {}
    for ep in ea_players:
        en = _norm(ep.get("name", ""))
        ea_by_full[en] = ep
        last = en.split()[-1] if en else ""
        ea_by_last.setdefault(last, []).append((en, ep))

    def _find_ea(name: str):
        nm = _norm(name)
        if nm in ea_by_full:
            return ea_by_full[nm]
        for en, ep in ea_by_full.items():
            if en and (en in nm or nm in en):
                return ep
        last = nm.split()[-1] if nm else ""
        cands = ea_by_last.get(last, [])
        if len(cands) == 1:
            return cands[0][1]
        if len(cands) > 1:
            tokens = set(nm.split())
            return max(cands, key=lambda kv: sum(1 for t in tokens if t in kv[0]))[1]
        return None

    _US_POS_MAP = {
        "GK": "GK",
        "D": "CB", "DC": "CB",
        "DL": "FB", "DR": "FB", "WBL": "FB", "WBR": "FB",
        "DM": "DM", "DMC": "DM",
        "MC": "CM", "M": "CM", "MR": "CM", "ML": "CM",
        "AMC": "AM", "AM": "AM",
        "AML": "Winger", "AMR": "Winger", "W": "Winger",
        "FW": "ST", "ST": "ST", "CF": "ST", "F": "ST", "S": "ST",
    }

    candidates = []
    for p in us_players:
        pname = p.get("player_name", "")
        if _norm(pname) in squad_norms:
            continue
        pos_tokens = p.get("position", "").split()
        pos_group = next((_US_POS_MAP.get(t.upper()) for t in pos_tokens if _US_POS_MAP.get(t.upper())), None)
        if not pos_group:
            continue

        minutes = max(int(p.get("time", 1)), 1)
        candidate = {
            "name":           pname,
            "club_name":      p.get("team", ""),
            "position_group": pos_group,
            "xg_per90":       p.get("xg_per90", 0.0),
            "xga_per90":      p.get("xa_per90", 0.0),
            "npxg_per90":     p.get("npxg_per90", 0.0),
            "goals_per90":    round(float(p.get("goals", 0)) / (minutes / 90), 3),
            "assists_per90":  round(float(p.get("assists", 0)) / (minutes / 90), 3),
            "us_games":       p.get("games", 0),
            "us_minutes":     minutes,
            "market_value_m": None,
            "age":            None,
            "overall":        None,
            "ea_avatar_url":  None,
        }

        # Enrich with EA attributes (portrait, overall, PAC/SHO/PAS/DRI/DEF/PHY)
        ea = _find_ea(pname)
        if ea:
            for key in ("overall", "pac", "sho", "pas", "dri", "def_", "phy",
                        "ea_avatar_url", "ea_shield_url", "sofifa_face_url",
                        "age", "market_value_m",
                        "acceleration", "sprint_speed", "finishing", "shot_power",
                        "long_shots", "vision", "crossing", "short_passing",
                        "long_passing", "agility", "ball_control", "dribbling_skill",
                        "composure", "interceptions_attr", "heading_accuracy",
                        "marking", "standing_tackle", "positioning",
                        "jumping", "stamina", "strength", "aggression",
                        "skill_moves", "weak_foot", "preferred_foot",
                        "gk_diving", "gk_handling", "gk_kicking",
                        "gk_positioning", "gk_reflexes",
                        "nat_flag_url", "club_logo_url"):
                val = ea.get(key)
                if val is not None:
                    candidate[key] = val

        candidates.append(candidate)
    return candidates


with st.spinner(f"Analysing {club_name}…"):
    squad = load_squad(club["tm_slug"], club["tm_id"], league)

if not squad:
    st.warning("Could not load squad data.")
    st.stop()

flag = TOP_5_LEAGUES[league]["flag"]
st.markdown(
    f"<h1 style='color:#c9a84c;'>{flag} {club_name} — Transfer Intelligence</h1>",
    unsafe_allow_html=True,
)
st.divider()

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_buy, tab_sell, tab_weakness = st.tabs(["🟢 Buy Targets", "🔴 Sell Candidates", "📉 Squad Weaknesses"])

# ── Tab: Squad Weaknesses ────────────────────────────────────────────────────
with tab_weakness:
    st.subheader("Squad Weakness Analysis")
    with st.spinner("Analysing squad strengths and weaknesses…"):
        try:
            weaknesses = analyze_squad_weaknesses(squad)
        except Exception as e:
            weaknesses = []
            st.error(f"Analysis error: {e}")

    if weaknesses:
        fig = build_weakness_chart(weaknesses)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Identified Gaps")
        for w in weaknesses:
            severity_color = "#ff5555" if w.get("severity") == "critical" else "#c9a84c"
            st.markdown(
                f"<div style='background:#111e2e;border:1px solid #1e3045;border-radius:8px;"
                f"padding:12px 16px;margin:6px 0;border-left:3px solid {severity_color};'>"
                f"<b style='color:{severity_color};'>{w.get('position_group','')}</b> "
                f"— {w.get('description', '')}"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("No critical weaknesses detected in the current squad!")

# ── Tab: Buy Targets ─────────────────────────────────────────────────────────
with tab_buy:
    st.subheader(f"Recommended Signings (budget: €{budget}M, max age: {max_age})")

    with st.spinner("Generating transfer targets…"):
        try:
            squad_names = tuple(p.get("name", "") for p in squad)
            candidate_pool = load_candidate_pool(league, squad_names, budget, max_age)
            if weaknesses and candidate_pool:
                targets = recommend_buys(weaknesses, candidate_pool=candidate_pool, budget_m=budget, max_age=max_age, top_n=top_n)
            else:
                targets = []
        except Exception as e:
            targets = []
            st.error(f"Recommendation error: {e}")

    if targets:
        # Cards view
        render_card_grid(targets, cols=4, show_price=True)

        st.markdown("---")
        st.markdown("#### Detailed Analysis")
        for t in targets:
            with st.expander(f"📊 {t.get('name','Player')}  ·  OVR {t.get('overall','—')}  ·  {t.get('club_name','')}", expanded=False):
                col_card, col_info = st.columns([1, 2])
                with col_card:
                    render_single_card(t, compact=True)
                with col_info:
                    # Estimate market value from EA overall if not available from TM
                    mv = t.get("market_value_m") or 0
                    if not mv:
                        overall = t.get("overall") or 0
                        if overall >= 87:   mv = 90.0
                        elif overall >= 84: mv = 60.0
                        elif overall >= 81: mv = 35.0
                        elif overall >= 78: mv = 20.0
                        elif overall >= 74: mv = 12.0
                        elif overall >= 70: mv = 6.0
                        else:               mv = 3.0
                        # xG bonus for attackers
                        xg = t.get("xg_per90", 0) or 0
                        if xg > 0.4: mv *= 1.3
                        elif xg > 0.25: mv *= 1.15
                    try:
                        t_with_mv = {**t, "market_value_m": mv}
                        pred = predict_transfer_fee(t_with_mv, league)
                        st.metric("Estimated Fee", f"€{pred['median_m']:.1f}M")
                        st.write(f"Range: €{pred['lower_m']:.0f}M – €{pred['upper_m']:.0f}M")
                        st.caption(f"Confidence: {pred['confidence']}")
                        for reason in pred.get("reasoning", []):
                            st.write(f"• {reason}")
                    except Exception:
                        st.metric("Market Value", f"€{mv:.1f}M")
    else:
        st.info("No targets found within the specified budget and age constraints. Try increasing the budget.")

# ── Tab: Sell Candidates ─────────────────────────────────────────────────────
with tab_sell:
    st.subheader("Players to Consider Selling")

    with st.spinner("Identifying sell candidates…"):
        try:
            us_league = TOP_5_LEAGUES.get(league, {}).get("understat_name", "")
            sell_candidates = recommend_sales(squad, us_league=us_league)
        except Exception as e:
            sell_candidates = []
            st.error(f"Error: {e}")

    if sell_candidates:
        for candidate in sell_candidates:
            with st.container():
                col_card, col_info = st.columns([1, 3])
                with col_card:
                    render_single_card(candidate, compact=True)
                with col_info:
                    st.markdown(
                        f"**{candidate.get('name','')}** · "
                        f"{candidate.get('position_code','')} · "
                        f"Age {candidate.get('age','')}"
                    )
                    reasons = candidate.get("sell_reasons", [])
                    for r in reasons:
                        st.write(f"• {r}")
                    try:
                        pred = predict_transfer_fee(candidate, league)
                        st.success(f"Potential fee: €{pred['median_m']:.1f}M (range €{pred['lower_m']:.0f}M–€{pred['upper_m']:.0f}M)")
                    except Exception:
                        mv = candidate.get("market_value_m", 0) or 0
                        if mv:
                            st.success(f"Market value: €{mv:.1f}M")
                st.divider()
    else:
        st.info("No strong sell candidates identified in the current squad.")
