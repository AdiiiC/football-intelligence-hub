"""
Transfer News — live confirmed transfers and rumour feed from Transfermarkt.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Transfer News", page_icon="📰", layout="wide")

_CSS = ROOT / "ui" / "styles" / "theme.css"
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES
from data.fetchers.squad import get_clubs_for_league
from data.scrapers.transfermarkt import get_transfer_news
from ui.components.transfer_feed import render_transfer_feed, render_ticker

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📰 Transfer News")
    mode = st.radio("View mode", ["By Club", "League Feed"])
    league = st.selectbox("League", list(TOP_5_LEAGUES.keys()))

    if mode == "By Club":
        clubs = get_clubs_for_league(league)
        club_name = st.selectbox("Club", [c["name"] for c in clubs])
        club = next(c for c in clubs if c["name"] == club_name)
    else:
        club = None
        club_name = ""

    news_type = st.multiselect(
        "Show",
        ["confirmed", "rumour"],
        default=["confirmed", "rumour"],
    )
    max_items = st.slider("Max items", 5, 50, 20)

# ── Load news ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_news(slug, tid):
    raw = get_transfer_news(slug, tid)
    items = []
    for entry in raw.get("confirmed", []):
        if isinstance(entry, dict):
            items.append(entry)
    for entry in raw.get("rumours", []):
        if isinstance(entry, dict):
            items.append(entry)
    return items

# ── Header ─────────────────────────────────────────────────────────────────────
flag = TOP_5_LEAGUES[league]["flag"]
title = f"{flag} {club_name} Transfers" if mode == "By Club" else f"{flag} {league} Transfer News"
_hcol, _rcol = st.columns([8, 1])
_hcol.markdown(f"<h1 style='color:#c9a84c;margin-bottom:4px;'>{title}</h1>", unsafe_allow_html=True)
if _rcol.button("🔄 Refresh", help="Clear cache and fetch latest transfer data"):
    load_news.clear()
    import glob, os
    for _f in glob.glob("data/cache/transfers_*.json"):
        os.remove(_f)
    st.rerun()
st.divider()

if mode == "By Club":
    with st.spinner(f"Loading {club_name} transfer news…"):
        news = load_news(club["tm_slug"], club["tm_id"])
else:
    # League feed: aggregate top clubs
    clubs = get_clubs_for_league(league)[:10]
    all_news = []
    prog = st.progress(0)
    for i, c in enumerate(clubs):
        items = load_news(c["tm_slug"], c["tm_id"])
        for item in items:
            item["_club"] = c["name"]
        all_news.extend(items)
        prog.progress((i + 1) / len(clubs))
    prog.empty()
    # Deduplicate by player name
    seen = set()
    news = []
    for item in all_news:
        key = item.get("name") or item.get("player_name", "")
        if key not in seen:
            seen.add(key)
            news.append(item)

# ── Filter ───────────────────────────────────────────────────────────────────
if news_type:
    news = [n for n in news if n.get("type", "rumour") in news_type]

# Confirmed: show ALL, sorted newest window first. Only cap rumours.
_WINDOW_ORDER = {"Summer 2026": 0, "Winter 2026": 1, "Summer 2025": 2}
confirmed_all = sorted(
    [n for n in news if n.get("type") == "confirmed"],
    key=lambda x: _WINDOW_ORDER.get(x.get("window", ""), 99)
)
rumours_all = [n for n in news if n.get("type") == "rumour"]
news = confirmed_all + rumours_all[:max_items]

# ── Ticker strip ─────────────────────────────────────────────────────────────
confirmed_news = [n for n in news if n.get("type") == "confirmed"]
if confirmed_news:
    st.markdown("**🔴 LIVE TICKER — Confirmed Transfers**")
    render_ticker(confirmed_news[:8])
    st.markdown("<br/>", unsafe_allow_html=True)

# ── Stats bar ────────────────────────────────────────────────────────────────
if news:
    confirmed_count = sum(1 for n in news if n.get("type") == "confirmed")
    rumour_count = sum(1 for n in news if n.get("type") == "rumour")
    total_fees = sum(n.get("fee_m", 0) or 0 for n in news if n.get("type") == "confirmed")

    c1, c2, c3 = st.columns(3)
    c1.metric("Confirmed Transfers", confirmed_count)
    c2.metric("Rumours", rumour_count)
    c3.metric("Total Confirmed Fees", f"€{total_fees:.0f}M")
    st.markdown("<br/>", unsafe_allow_html=True)

# ── Main feed ────────────────────────────────────────────────────────────────
tab_confirmed, tab_rumours, tab_all = st.tabs([
    f"✅ Confirmed ({sum(1 for n in news if n.get('type')=='confirmed')})",
    f"🔍 Rumours ({sum(1 for n in news if n.get('type')=='rumour')})",
    f"📋 All ({len(news)})",
])

with tab_confirmed:
    confirmed = [n for n in news if n.get("type") == "confirmed"]
    if confirmed:
        render_transfer_feed(confirmed, club_name or league)
    else:
        st.info("No confirmed transfers in this feed.")

with tab_rumours:
    rumours = [n for n in news if n.get("type") == "rumour"]
    if rumours:
        render_transfer_feed(rumours, club_name or league)
    else:
        st.info("No transfer rumours in this feed.")

with tab_all:
    if news:
        render_transfer_feed(news, club_name or league)
    else:
        st.warning(
            "No transfer news found. This may be due to:\n"
            "- Off-season (January/July windows are most active)\n"
            "- Network issues connecting to Transfermarkt\n"
            "- Selected club has no recent activity\n\n"
            "Try a different club or check back later."
        )
