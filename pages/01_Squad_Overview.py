"""
Squad Overview — formation pitch, FIFA card grid, depth chart.
"""

import json
import sys
from pathlib import Path

import streamlit as st

# ── Project root on path ─────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Squad Overview", page_icon="🏟", layout="wide")

_CSS = (ROOT / "ui" / "styles" / "theme.css")
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES
from data.fetchers.squad import get_clubs_for_league, get_enriched_squad
from ui.components.formation import render_formation, FORMATION_POSITIONS
from ui.components.fifa_card import render_card_grid

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏟 Squad Overview")
    league = st.selectbox("League", list(TOP_5_LEAGUES.keys()))
    clubs = get_clubs_for_league(league)
    club_names = [c["name"] for c in clubs]
    club_name = st.selectbox("Club", club_names)
    club = next((c for c in clubs if c["name"] == club_name), clubs[0])

    formation = st.selectbox(
        "Formation",
        list(FORMATION_POSITIONS.keys()),
        index=0,
    )
    st.markdown("---")
    view_mode = st.radio("View", ["Formation + Cards", "Cards Only", "Formation Only"])

# ── Load squad ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def load_squad(slug, tid, league_name):
    return get_enriched_squad(slug, tid, league_name)

with st.spinner(f"Loading {club_name} squad…"):
    squad = load_squad(club["tm_slug"], club["tm_id"], league)

# ── Header ───────────────────────────────────────────────────────────────────
col_title, col_meta = st.columns([3, 1])
with col_title:
    flag = TOP_5_LEAGUES[league]["flag"]
    st.markdown(
        f"<h1 style='color:#c9a84c;margin-bottom:4px;'>{flag} {club_name}</h1>"
        f"<p style='color:#8899aa;font-size:.9rem;margin:0;'>{league} · {len(squad)} players in squad</p>",
        unsafe_allow_html=True,
    )
with col_meta:
    if squad:
        total_val = sum(p.get("market_value_m", 0) or 0 for p in squad)
        avg_age = sum(int(p.get("age") or 25) for p in squad) / len(squad)
        st.metric("Squad Value", f"€{total_val:.0f}M")
        st.metric("Avg Age", f"{avg_age:.1f}")

st.divider()

# ── Main content ─────────────────────────────────────────────────────────────
if not squad:
    st.warning("Could not load squad data. Check network connection and try again.")
    st.stop()

if view_mode in ("Formation + Cards", "Formation Only"):
    st.subheader("📐 Formation")
    try:
        fig = render_formation(squad, formation, club_name)
        if fig:
            st.pyplot(fig)
    except Exception as e:
        st.error(f"Formation render error: {e}")

if view_mode in ("Formation + Cards", "Cards Only"):
    st.subheader("🃏 Squad Cards")

    # Filter controls
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        pos_filter = st.multiselect(
            "Filter by position",
            ["All", "GK", "DEF", "MID", "ATT"],
            default=["All"],
        )
    with col_f2:
        min_ovr = st.slider("Min OVR", 40, 99, 60)
    with col_f3:
        sort_by = st.selectbox("Sort by", ["Overall", "Market Value", "Age", "Name"])

    # Apply filters
    filtered = squad[:]
    if "All" not in pos_filter and pos_filter:
        pos_map = {
            "GK": ["GK"],
            "DEF": ["CB", "LB", "RB", "LWB", "RWB"],
            "MID": ["CM", "DM", "AM", "CAM", "CDM", "LM", "RM"],
            "ATT": ["ST", "CF", "LW", "RW", "FW"],
        }
        allowed = set()
        for group in pos_filter:
            allowed.update(pos_map.get(group, []))
        filtered = [p for p in filtered if p.get("position_code", "") in allowed]

    filtered = [p for p in filtered if (p.get("overall") or p.get("market_value_m", 0) or 0) >= min_ovr or True]

    # Sort
    if sort_by == "Overall":
        filtered = sorted(filtered, key=lambda p: p.get("overall", 0), reverse=True)
    elif sort_by == "Market Value":
        filtered = sorted(filtered, key=lambda p: p.get("market_value_m", 0) or 0, reverse=True)
    elif sort_by == "Age":
        filtered = sorted(filtered, key=lambda p: p.get("age", 99) or 99)
    else:
        filtered = sorted(filtered, key=lambda p: p.get("name", ""))

    if filtered:
        render_card_grid(filtered, cols=6, show_price=True)
    else:
        st.info("No players match the current filters.")

# ── Depth chart table ────────────────────────────────────────────────────────
with st.expander("📋 Full Squad Table"):
    import pandas as pd

    rows = []
    for p in sorted(squad, key=lambda x: x.get("overall") or 0, reverse=True):
        rows.append({
            "Name": p.get("name", ""),
            "Pos": p.get("position_code", ""),
            "Age": int(p.get("age") or 0) or None,
            "OVR": int(p.get("overall")) if p.get("overall") else None,
            "PAC": int(p.get("pac")) if p.get("pac") else None,
            "SHO": int(p.get("sho")) if p.get("sho") else None,
            "PAS": int(p.get("pas")) if p.get("pas") else None,
            "DRI": int(p.get("dri")) if p.get("dri") else None,
            "DEF": int(p.get("def_")) if p.get("def_") else None,
            "PHY": int(p.get("phy")) if p.get("phy") else None,
            "Value": f"€{p.get('market_value_m',0):.1f}M" if p.get("market_value_m") else "",
            "Contract": p.get("contract_expiry", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)
