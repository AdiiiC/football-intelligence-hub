"""
Head-to-Head Player Comparison — side-by-side radar, stats, and xG timeline.
"""

import sys
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Compare Players", page_icon="⚔️", layout="wide")

_CSS = ROOT / "ui" / "styles" / "theme.css"
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES
from data.fetchers.squad import get_clubs_for_league, get_enriched_squad
from data.scrapers.understat import search_player_understat, get_player_xg_timeline, get_player_season_summary

DARK_BG = "#0d1b2a"
GOLD    = "#c9a84c"
BLUE    = "#3498db"


def _pick_player(col_key: str, label: str):
    with st.sidebar:
        st.markdown(f"### {label}")
        league = st.selectbox("League", list(TOP_5_LEAGUES.keys()), key=f"lg_{col_key}")
        clubs = get_clubs_for_league(league)
        club_name = st.selectbox("Club", [c["name"] for c in clubs], key=f"cl_{col_key}")
        club = next(c for c in clubs if c["name"] == club_name)

        @st.cache_data(ttl=86400, show_spinner=False)
        def _squad(slug, tid, ln, club_dn=""):
            return get_enriched_squad(slug, tid, ln, club_display_name=club_dn)

        with st.spinner(f"Loading {club_name}…"):
            squad = _squad(club["tm_slug"], club["tm_id"], league, club_dn=club_name)

        player_names = [p.get("name", "") for p in squad]
        sel = st.selectbox("Player", player_names, key=f"pl_{col_key}")
        player = next((p for p in squad if p.get("name") == sel), None)
        return player, league


st.markdown("## ⚔️ Head-to-Head Comparison")
st.caption("Compare two players side-by-side — attributes, xG, and season stats.")

with st.sidebar:
    st.markdown("---")

p1, league1 = _pick_player("p1", "🔵 Player 1")

with st.sidebar:
    st.markdown("---")

p2, league2 = _pick_player("p2", "🔴 Player 2")

if not p1 or not p2:
    st.info("Select two players from the sidebar.")
    st.stop()

# ── Attribute radar ──────────────────────────────────────────────────────────
ATTRS = ["pac", "sho", "pas", "dri", "def_", "phy"]
ATTR_LABELS = ["Pace", "Shooting", "Passing", "Dribbling", "Defending", "Physicality"]

vals1 = [p1.get(a, 0) or 0 for a in ATTRS]
vals2 = [p2.get(a, 0) or 0 for a in ATTRS]

fig_radar = go.Figure()
fig_radar.add_trace(go.Scatterpolar(
    r=vals1 + [vals1[0]],
    theta=ATTR_LABELS + [ATTR_LABELS[0]],
    fill="toself",
    name=p1.get("name", "Player 1"),
    line_color=BLUE,
    fillcolor=f"rgba(52,152,219,0.2)",
))
fig_radar.add_trace(go.Scatterpolar(
    r=vals2 + [vals2[0]],
    theta=ATTR_LABELS + [ATTR_LABELS[0]],
    fill="toself",
    name=p2.get("name", "Player 2"),
    line_color="#e74c3c",
    fillcolor=f"rgba(231,76,60,0.2)",
))
fig_radar.update_layout(
    polar=dict(
        bgcolor=DARK_BG,
        radialaxis=dict(visible=True, range=[0, 100], color="#8899aa"),
        angularaxis=dict(color="#8899aa"),
    ),
    paper_bgcolor=DARK_BG,
    plot_bgcolor=DARK_BG,
    legend=dict(font=dict(color="white")),
    margin=dict(t=20, b=20),
    height=380,
)

st.plotly_chart(fig_radar, use_container_width=True)
st.markdown("---")

# ── Attribute bars ───────────────────────────────────────────────────────────
def _attr_bar(label, v1, v2, name1, name2):
    col_l, col_bar, col_r = st.columns([1, 4, 1])
    with col_l:
        color = BLUE if v1 >= v2 else "#555"
        st.markdown(f"<div style='color:{color};font-weight:700;font-size:1.1rem;text-align:right;'>{int(v1)}</div>", unsafe_allow_html=True)
    with col_bar:
        pct1 = int(v1)
        pct2 = int(v2)
        st.markdown(
            f"""<div style='display:flex;align-items:center;gap:4px;height:28px;'>
              <div style='flex:{pct1};background:{BLUE};border-radius:4px 0 0 4px;height:14px;min-width:4px;'></div>
              <div style='color:#8899aa;font-size:.75rem;white-space:nowrap;'>{label}</div>
              <div style='flex:{pct2};background:#e74c3c;border-radius:0 4px 4px 0;height:14px;min-width:4px;'></div>
            </div>""",
            unsafe_allow_html=True,
        )
    with col_r:
        color = "#e74c3c" if v2 >= v1 else "#555"
        st.markdown(f"<div style='color:{color};font-weight:700;font-size:1.1rem;'>{int(v2)}</div>", unsafe_allow_html=True)

name1 = p1.get("name", "P1")
name2 = p2.get("name", "P2")

hc1, hc2 = st.columns(2)
hc1.markdown(f"<h3 style='color:{BLUE};text-align:center;'>{name1}</h3>", unsafe_allow_html=True)
hc2.markdown(f"<h3 style='color:#e74c3c;text-align:center;'>{name2}</h3>", unsafe_allow_html=True)

for label, attr in zip(ATTR_LABELS, ATTRS):
    _attr_bar(label, p1.get(attr, 0) or 0, p2.get(attr, 0) or 0, name1, name2)

st.markdown("---")

# ── Key info row ─────────────────────────────────────────────────────────────
def _info_cell(label, v1, v2):
    try:
        better = float(v1) >= float(v2)
    except Exception:
        better = True
    c1, c2 = st.columns(2)
    c1.metric(label, v1, delta=None)
    c2.metric(label, v2, delta=None)

cols = st.columns(2)
for col, p, nm in [(cols[0], p1, name1), (cols[1], p2, name2)]:
    with col:
        st.markdown(f"**{nm}**")
        st.write(f"Age: {p.get('age','—')} | Position: {p.get('position_code','—')}")
        st.write(f"Overall: {p.get('overall','—')} | Value: €{p.get('market_value_m','—')}M")
        st.write(f"Nationality: {p.get('nationality','—')} | Foot: {p.get('preferred_foot','—')}")

st.markdown("---")

# ── xG Season summary comparison ─────────────────────────────────────────────
st.subheader("Season Stats (Understat)")

@st.cache_data(ttl=86400, show_spinner=False)
def _get_us_id(name, league):
    us_name = TOP_5_LEAGUES.get(league, {}).get("understat_name", "EPL")
    p = search_player_understat(name, us_name, "2025")
    return p.get("id") if p else None

@st.cache_data(ttl=86400, show_spinner=False)
def _get_summary(pid):
    return get_player_season_summary(pid) if pid else []

us1 = _get_us_id(name1, league1)
us2 = _get_us_id(name2, league2)

import pandas as pd

ss1 = _get_summary(us1)
ss2 = _get_summary(us2)

sc1, sc2 = st.columns(2)
with sc1:
    st.markdown(f"**{name1}**")
    if ss1:
        df1 = pd.DataFrame(ss1[:4])
        st.dataframe(df1[["season","team","apps","goals","assists","xG","xA","xG90"]],
                     hide_index=True, use_container_width=True,
                     column_config={"xG": st.column_config.NumberColumn(format="%.2f"),
                                    "xA": st.column_config.NumberColumn(format="%.2f"),
                                    "xG90": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.info("No Understat data")

with sc2:
    st.markdown(f"**{name2}**")
    if ss2:
        df2 = pd.DataFrame(ss2[:4])
        st.dataframe(df2[["season","team","apps","goals","assists","xG","xA","xG90"]],
                     hide_index=True, use_container_width=True,
                     column_config={"xG": st.column_config.NumberColumn(format="%.2f"),
                                    "xA": st.column_config.NumberColumn(format="%.2f"),
                                    "xG90": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.info("No Understat data")

# ── xG timeline overlay ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("xG per Match — Overlay")

@st.cache_data(ttl=86400, show_spinner=False)
def _get_timeline(pid):
    return get_player_xg_timeline(pid, "2025") if pid else []

tl1 = _get_timeline(us1)
tl2 = _get_timeline(us2)

if tl1 or tl2:
    fig_xg = go.Figure()
    if tl1:
        fig_xg.add_trace(go.Scatter(
            x=list(range(len(tl1))), y=[m["xg"] for m in tl1],
            name=name1, mode="lines+markers",
            line=dict(color=BLUE, width=2),
            marker=dict(size=6),
            hovertext=[f"{m['home_team']} vs {m['away_team']}<br>xG: {m['xg']:.2f} | G: {m['goals']}" for m in tl1],
            hovertemplate="%{hovertext}<extra></extra>",
        ))
    if tl2:
        fig_xg.add_trace(go.Scatter(
            x=list(range(len(tl2))), y=[m["xg"] for m in tl2],
            name=name2, mode="lines+markers",
            line=dict(color="#e74c3c", width=2),
            marker=dict(size=6),
            hovertext=[f"{m['home_team']} vs {m['away_team']}<br>xG: {m['xg']:.2f} | G: {m['goals']}" for m in tl2],
            hovertemplate="%{hovertext}<extra></extra>",
        ))
    fig_xg.update_layout(
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        xaxis=dict(title="Match #", color="#8899aa", gridcolor="#1a2d40"),
        yaxis=dict(title="xG", color="#8899aa", gridcolor="#1a2d40"),
        legend=dict(font=dict(color="white")),
        height=320, margin=dict(t=10, b=40),
    )
    st.plotly_chart(fig_xg, use_container_width=True)
else:
    st.info("xG timeline data not available for either player.")
