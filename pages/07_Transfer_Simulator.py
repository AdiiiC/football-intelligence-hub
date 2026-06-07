"""
What-If Transfer Simulator — hypothetical signing impact on squad playstyle and sell recommendations.
"""

import sys
from pathlib import Path
from copy import deepcopy

import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Transfer Simulator", page_icon="🔮", layout="wide")

_CSS = ROOT / "ui" / "styles" / "theme.css"
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES
from data.fetchers.squad import get_clubs_for_league, get_enriched_squad
from data.scrapers.ea_ratings import search_player_ea
from models.squad_analyzer import determine_team_playstyle, recommend_sales

st.markdown("## 🔮 What-If Transfer Simulator")
st.caption("Add a hypothetical signing to your squad and see the impact on playstyle and sell priority.")

# ── Sidebar: base squad ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏟️ Base Squad")
    league = st.selectbox("League", list(TOP_5_LEAGUES.keys()), key="sim_lg")
    clubs = get_clubs_for_league(league)
    club_name = st.selectbox("Club", [c["name"] for c in clubs], key="sim_cl")
    club = next(c for c in clubs if c["name"] == club_name)

    st.markdown("---")
    st.markdown("### ➕ Hypothetical Signing")
    signing_name = st.text_input("Player name", placeholder="e.g. Kylian Mbappé", key="sim_name")
    simulate_btn = st.button("Run Simulation", type="primary")


@st.cache_data(ttl=86400, show_spinner=False)
def _squad(slug, tid, ln, club_dn=""):
    return get_enriched_squad(slug, tid, ln, club_display_name=club_dn)


with st.spinner(f"Loading {club_name}…"):
    squad = _squad(club["tm_slug"], club["tm_id"], league, club_dn=club_name)

if not squad:
    st.warning("Could not load squad.")
    st.stop()

# ── Current state ─────────────────────────────────────────────────────────────
col_before, col_after = st.columns(2)

with col_before:
    st.markdown("### Current State")
    st.metric("Squad Size", len(squad))
    total_val = sum(p.get("market_value_m", 0) or 0 for p in squad)
    avg_age = sum(int(p.get("age") or 25) for p in squad) / len(squad)
    st.metric("Total Value", f"€{total_val:.0f}M")
    st.metric("Avg Age", f"{avg_age:.1f}")

    with st.spinner("Analysing current playstyle…"):
        ps_before = determine_team_playstyle(squad, club_name, league)

    dominant_before = ps_before.get("dominant", "Unknown")
    st.markdown(f"**Playstyle:** `{dominant_before}`")
    st.caption(ps_before.get("description", ""))

    scores_before = ps_before.get("scores", {})
    if scores_before:
        import pandas as pd
        df_scores = pd.DataFrame([{"Archetype": k, "Score": round(v, 1)} for k, v in
                                   sorted(scores_before.items(), key=lambda x: x[1], reverse=True)])
        st.dataframe(df_scores, hide_index=True, use_container_width=True)

    sells_before = recommend_sales(squad)[:5]
    if sells_before:
        st.markdown("**Top sell candidates:**")
        for s in sells_before:
            st.write(f"• {s.get('name')} ({s.get('position_code')}) — score {s.get('sell_score', 0):.0f}")


# ── Hypothetical signing ──────────────────────────────────────────────────────
if simulate_btn and signing_name.strip():
    with st.spinner(f"Searching EA database for {signing_name}…"):
        ea_player = search_player_ea(signing_name.strip())

    if not ea_player:
        st.error(f"Player '{signing_name}' not found in EA database. Check the spelling.")
        st.stop()

    # Build hypothetical signing dict
    new_player = deepcopy(ea_player)
    new_player.setdefault("market_value_m", 0)
    new_player.setdefault("age", 25)
    new_player.setdefault("contract_expiry", 2028)
    new_player.setdefault("play_styles", [])

    hypothetical_squad = squad + [new_player]
    signing_mv = new_player.get("market_value_m", 0) or 0

    with col_after:
        st.markdown(f"### After Signing {new_player.get('name', signing_name)}")

        new_total_val = total_val + signing_mv
        new_avg_age = sum(int(p.get("age") or 25) for p in hypothetical_squad) / len(hypothetical_squad)
        st.metric("Squad Size", len(hypothetical_squad), delta=1)
        st.metric("Total Value", f"€{new_total_val:.0f}M", delta=f"+€{signing_mv:.0f}M")
        st.metric("Avg Age", f"{new_avg_age:.1f}", delta=f"{new_avg_age - avg_age:+.1f}")

        with st.spinner("Analysing new playstyle…"):
            ps_after = determine_team_playstyle(hypothetical_squad, club_name, league)

        dominant_after = ps_after.get("dominant", "Unknown")
        changed = dominant_after != dominant_before
        icon = "🔄" if changed else "✅"
        st.markdown(f"**Playstyle:** `{dominant_after}` {icon}")
        st.caption(ps_after.get("description", ""))

        if changed:
            st.warning(f"Playstyle shift: {dominant_before} → {dominant_after}")

        scores_after = ps_after.get("scores", {})
        if scores_after:
            df_after = pd.DataFrame([{"Archetype": k, "Score": round(v, 1)} for k, v in
                                      sorted(scores_after.items(), key=lambda x: x[1], reverse=True)])
            st.dataframe(df_after, hide_index=True, use_container_width=True)

        sells_after = recommend_sales(hypothetical_squad)[:5]
        if sells_after:
            st.markdown("**Top sell candidates (after signing):**")
            for s in sells_after:
                before_names = [x.get("name") for x in sells_before]
                delta_tag = "" if s.get("name") in before_names else " 🆕"
                st.write(f"• {s.get('name')}{delta_tag} ({s.get('position_code')}) — score {s.get('sell_score', 0):.0f}")

    # ── Signing profile ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader(f"Signing Profile: {new_player.get('name', signing_name)}")
    ATTRS = ["pac", "sho", "pas", "dri", "def_", "phy"]
    LABELS = ["PAC", "SHO", "PAS", "DRI", "DEF", "PHY"]
    attr_cols = st.columns(6)
    for col, attr, label in zip(attr_cols, ATTRS, LABELS):
        col.metric(label, new_player.get(attr) or "—")

    squad_avgs = {}
    for a in ATTRS:
        vals = [p.get(a) or 0 for p in squad if p.get(a)]
        squad_avgs[a] = sum(vals) / len(vals) if vals else 0

    st.markdown("**Above squad average:**")
    above = [LABELS[i] for i, a in enumerate(ATTRS) if (new_player.get(a) or 0) > squad_avgs.get(a, 0)]
    below = [LABELS[i] for i, a in enumerate(ATTRS) if (new_player.get(a) or 0) < squad_avgs.get(a, 0)]
    st.write(f"✅ {', '.join(above) if above else 'None'}")
    st.write(f"❌ {', '.join(below) if below else 'None'}")

    play_styles = new_player.get("play_styles", []) or []
    if play_styles:
        st.markdown(f"**Play Styles:** {', '.join(play_styles)}")

elif not simulate_btn:
    with col_after:
        st.markdown("### After Signing ...")
        st.info("Enter a player name and click **Run Simulation** to see the impact.")
