"""
Formation View — interactive pitch with squad auto-assigned to formation slots.
"""

import sys
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Formation View", page_icon="🏟️", layout="wide")

_CSS = ROOT / "ui" / "styles" / "theme.css"
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES
from data.fetchers.squad import get_clubs_for_league, get_enriched_squad

DARK_BG = "#0d1b2a"

# ── Formation slot definitions [y=pitch-y (0=goal, 100=opponent), x=0..100] ──
FORMATIONS = {
    "4-3-3": [
        ("GK", 5,  50),
        ("RB", 25, 80), ("CB", 25, 60), ("CB", 25, 40), ("LB", 25, 20),
        ("CM", 50, 70), ("CM", 50, 50), ("CM", 50, 30),
        ("RW", 78, 80), ("ST", 82, 50), ("LW", 78, 20),
    ],
    "4-2-3-1": [
        ("GK", 5,  50),
        ("RB", 25, 80), ("CB", 25, 60), ("CB", 25, 40), ("LB", 25, 20),
        ("DM", 42, 65), ("DM", 42, 35),
        ("RW", 62, 80), ("AM", 65, 50), ("LW", 62, 20),
        ("ST", 82, 50),
    ],
    "4-4-2": [
        ("GK", 5,  50),
        ("RB", 25, 80), ("CB", 25, 60), ("CB", 25, 40), ("LB", 25, 20),
        ("RM", 55, 80), ("CM", 55, 60), ("CM", 55, 40), ("LM", 55, 20),
        ("ST", 82, 65), ("ST", 82, 35),
    ],
    "3-5-2": [
        ("GK", 5,  50),
        ("CB", 25, 70), ("CB", 25, 50), ("CB", 25, 30),
        ("RWB", 50, 88), ("CM", 50, 67), ("DM", 50, 50), ("CM", 50, 33), ("LWB", 50, 12),
        ("ST", 82, 62), ("ST", 82, 38),
    ],
    "3-4-3": [
        ("GK", 5,  50),
        ("CB", 25, 70), ("CB", 25, 50), ("CB", 25, 30),
        ("RM", 52, 80), ("CM", 52, 60), ("CM", 52, 40), ("LM", 52, 20),
        ("RW", 78, 80), ("ST", 82, 50), ("LW", 78, 20),
    ],
    "5-3-2": [
        ("GK", 5,  50),
        ("RWB", 28, 88), ("CB", 28, 70), ("CB", 28, 50), ("CB", 28, 30), ("LWB", 28, 12),
        ("CM", 55, 68), ("CM", 55, 50), ("CM", 55, 32),
        ("ST", 82, 62), ("ST", 82, 38),
    ],
}

# Position group → formation slot preferences (higher = preferred)
_SLOT_AFFINITY = {
    "GK":  {"GK": 10},
    "CB":  {"CB": 10, "DM": 2},
    "FB":  {"RB": 8, "LB": 8, "RWB": 7, "LWB": 7, "RM": 3, "LM": 3},
    "DM":  {"DM": 10, "CM": 6, "CB": 2},
    "CM":  {"CM": 10, "DM": 7, "AM": 5},
    "AM":  {"AM": 10, "CM": 6, "RW": 4, "LW": 4},
    "Winger": {"RW": 9, "LW": 9, "RM": 7, "LM": 7, "AM": 3},
    "ST":  {"ST": 10, "CF": 10, "RW": 3, "LW": 3},
}

_POSITION_TO_GROUP = {
    "GK": "GK",
    "CB": "CB", "LCB": "CB", "RCB": "CB",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "DM": "DM", "CDM": "DM",
    "CM": "CM", "MF": "CM", "LCM": "CM", "RCM": "CM",
    "CAM": "AM", "AM": "AM",
    "LW": "Winger", "RW": "Winger", "LM": "Winger", "RM": "Winger",
    "ST": "ST", "CF": "ST", "FW": "ST",
}


def _assign_players_to_formation(squad, slots):
    """Greedily assign best-fit player to each slot."""
    available = [p for p in squad if p.get("name")]
    assigned = {}  # slot_idx → player

    slot_order = list(range(len(slots)))
    # GK first, then outfield
    slot_order.sort(key=lambda i: (0 if slots[i][0] == "GK" else 1))

    used = set()
    for i in slot_order:
        slot_pos = slots[i][0]
        best_score = -1
        best_player = None
        for p in available:
            if id(p) in used:
                continue
            pg = _POSITION_TO_GROUP.get(p.get("position_code", ""), "CM")
            affinity = _SLOT_AFFINITY.get(pg, {})
            score = affinity.get(slot_pos, 0)
            ovr = (p.get("overall") or 0) / 200  # small tiebreak
            total = score + ovr
            if total > best_score:
                best_score = total
                best_player = p
        if best_player:
            assigned[i] = best_player
            used.add(id(best_player))

    return assigned


def _draw_pitch_with_players(slots, assigned):
    fig = go.Figure()

    # Pitch outline
    def _rect(x0, y0, x1, y1, **kw):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=dict(color="#3a5a3a", width=1.5), **kw)

    _rect(0, 0, 100, 100)          # outer
    _rect(0, 30, 16, 70)           # own penalty
    _rect(84, 30, 100, 70)         # opp penalty
    _rect(0, 41, 5.5, 59)          # own 6-yard
    _rect(94.5, 41, 100, 59)       # opp 6-yard

    # Centre circle (approximate with scatter)
    import math
    cx, cy, r = 50, 50, 9.15
    theta = [i * 2 * math.pi / 60 for i in range(61)]
    cx_pts = [cx + r * math.cos(t) for t in theta]
    cy_pts = [cy + r * math.sin(t) for t in theta]
    fig.add_trace(go.Scatter(x=cx_pts, y=cy_pts, mode="lines",
                             line=dict(color="#3a5a3a", width=1.5),
                             hoverinfo="skip", showlegend=False))
    # Centre spot
    fig.add_trace(go.Scatter(x=[50], y=[50], mode="markers",
                             marker=dict(color="#3a5a3a", size=5),
                             hoverinfo="skip", showlegend=False))
    # Halfway line
    fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100,
                  line=dict(color="#3a5a3a", width=1.5))

    # Players
    for i, (slot_pos, px, py) in enumerate(slots):
        player = assigned.get(i)
        if not player:
            continue
        name = player.get("name", "?")
        ovr  = player.get("overall") or ""
        short_name = name.split()[-1] if " " in name else name

        # Circle
        fig.add_trace(go.Scatter(
            x=[px], y=[py],
            mode="markers+text",
            marker=dict(size=28, color="#1a3a5c", line=dict(color="#c9a84c", width=2)),
            text=[str(ovr)],
            textposition="middle center",
            textfont=dict(color="#c9a84c", size=11, family="Arial Black"),
            hovertext=[f"<b>{name}</b><br>Position: {slot_pos}<br>OVR: {ovr}"],
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False,
        ))
        # Name label
        fig.add_trace(go.Scatter(
            x=[px], y=[py - 6],
            mode="text",
            text=[short_name],
            textfont=dict(color="white", size=9),
            hoverinfo="skip",
            showlegend=False,
        ))

    fig.update_layout(
        paper_bgcolor="#1a3a1a",
        plot_bgcolor="#2d6a2d",
        xaxis=dict(visible=False, range=[-5, 105]),
        yaxis=dict(visible=False, range=[-10, 110], scaleanchor="x", scaleratio=0.7),
        margin=dict(t=10, b=10, l=10, r=10),
        height=520,
    )
    return fig


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    league = st.selectbox("League", list(TOP_5_LEAGUES.keys()), key="fm_lg")
    clubs = get_clubs_for_league(league)
    club_name = st.selectbox("Club", [c["name"] for c in clubs], key="fm_cl")
    club = next(c for c in clubs if c["name"] == club_name)
    formation = st.selectbox("Formation", list(FORMATIONS.keys()), index=0, key="fm_form")

@st.cache_data(ttl=86400, show_spinner=False)
def _squad(slug, tid, ln):
    return get_enriched_squad(slug, tid, ln)

with st.spinner(f"Loading {club_name}…"):
    squad = _squad(club["tm_slug"], club["tm_id"], league)

# ── Main ─────────────────────────────────────────────────────────────────────
st.markdown(f"## 🏟️ {club_name} — {formation}")

slots = FORMATIONS[formation]
assigned = _assign_players_to_formation(squad, slots)

fig = _draw_pitch_with_players(slots, assigned)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("Starting XI")

import pandas as pd

rows = []
for i, (slot_pos, px, py) in enumerate(slots):
    p = assigned.get(i)
    if p:
        rows.append({
            "Slot": slot_pos,
            "Name": p.get("name", "—"),
            "Age": p.get("age", "—"),
            "OVR": p.get("overall", "—"),
            "Value (€M)": p.get("market_value_m", "—"),
        })

if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# Manual override expander
with st.expander("🔧 Manual player assignment"):
    st.caption("Drag-and-drop not yet supported in Streamlit — use dropdowns to reassign slots.")
    player_names = ["—"] + [p.get("name", "") for p in squad]
    for i, (slot_pos, px, py) in enumerate(slots):
        current = assigned.get(i, {}).get("name", "—")
        sel = st.selectbox(f"Slot {slot_pos}", player_names,
                           index=player_names.index(current) if current in player_names else 0,
                           key=f"slot_{i}")
        if sel != "—":
            assigned[i] = next((p for p in squad if p.get("name") == sel), assigned.get(i))
