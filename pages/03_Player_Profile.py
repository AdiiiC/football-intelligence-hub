"""
Player Profile — hero FIFA card, radar chart, shot map, xG timeline, price prediction, fit analysis.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Player Profile", page_icon="📊", layout="wide")

_CSS = ROOT / "ui" / "styles" / "theme.css"
if _CSS.exists():
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

from config.settings import TOP_5_LEAGUES
from data.fetchers.squad import get_clubs_for_league, get_enriched_squad
from data.scrapers.ea_ratings import search_player_ea
from data.scrapers.understat import search_player_understat, get_player_xg_timeline, get_player_shots, get_player_understat_url
from data.scrapers.fbref import get_player_stats, get_player_percentiles, get_league_stats
from models.price_predictor import predict_transfer_fee
from models.squad_analyzer import fit_analysis
from ui.components.fifa_card import render_player_hero_card, render_single_card

# ── Helper (must be defined before first use) ─────────────────────────────────
def _pos_to_group(pos_code):
    mapping = {
        "GK": "GK",
        "CB": "CB", "LCB": "CB", "RCB": "CB",
        "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
        "DM": "DM", "CDM": "DM",
        "CM": "CM", "LCM": "CM", "RCM": "CM",
        "CAM": "AM", "AM": "AM",
        "LW": "Winger", "RW": "Winger", "LM": "Winger", "RM": "Winger",
        "ST": "ST", "CF": "ST", "FW": "ST",
    }
    return mapping.get(pos_code, "CM")


from ui.components.stat_charts import (
    build_radar_chart,
    build_shot_map,
    build_xg_timeline,
    build_market_value_chart,
    build_price_gauge,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📊 Player Profile")
    search_mode = st.radio("Find player by", ["Browse squad", "Search by name"])

    if search_mode == "Browse squad":
        league = st.selectbox("League", list(TOP_5_LEAGUES.keys()))
        clubs = get_clubs_for_league(league)
        club_name = st.selectbox("Club", [c["name"] for c in clubs])
        club = next(c for c in clubs if c["name"] == club_name)

        @st.cache_data(ttl=86400, show_spinner=False)
        def load_squad(slug, tid, ln):
            return get_enriched_squad(slug, tid, ln)

        with st.spinner(f"Loading {club_name}…"):
            squad = load_squad(club["tm_slug"], club["tm_id"], league)

        player_names = [p.get("name", "") for p in squad]
        selected_name = st.selectbox("Player", player_names)
        player = next((p for p in squad if p.get("name") == selected_name), None)
    else:
        league = st.selectbox("League", list(TOP_5_LEAGUES.keys()))
        query = st.text_input("Player name", placeholder="e.g. Bukayo Saka")
        player = None
        squad = []
        club_name = ""
        if query:
            ea_player = search_player_ea(query)
            if ea_player:
                player = ea_player
                club_name = ea_player.get("club_name", "")
            else:
                st.warning("Player not found in EA database.")

if not player:
    st.info("Select a player from the sidebar to view their profile.")
    st.stop()

# ── Enrich with fresh EA attributes ─────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def enrich_player(name, club):
    ea = search_player_ea(name, club)
    return ea

ea_data = enrich_player(player.get("name", ""), player.get("club_name", "") or club_name)
if ea_data:
    player = {**ea_data, **{k: v for k, v in player.items() if v is not None}}

# ── Hero section ─────────────────────────────────────────────────────────────
import streamlit.components.v1 as _comp
_hero_html = render_player_hero_card(player)
_comp.html(f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
  body{{margin:0;padding:0;background:transparent;font-family:'Inter',system-ui,sans-serif;}}
</style>
</head><body>{_hero_html}</body></html>""", height=420, scrolling=False)

# ── Player meta row ───────────────────────────────────────────────────────────
name = player.get("name", "Player")
pos = player.get("position_label") or player.get("position_code", "")
nat = player.get("nationality", "")
club_label = player.get("club_name", "") or club_name
lg = player.get("league_name", "") or league
ovr = player.get("overall", "—")
age = player.get("age", "—")
ht = player.get("height_cm", "—")
wt = player.get("weight_kg", "—")
sm = player.get("skill_moves", "—")
wf = player.get("weak_foot", "—")
foot = player.get("preferred_foot", "—")

st.markdown(
    f"<h1 style='color:#c9a84c;margin-bottom:4px;font-size:2.2rem;'>{name}</h1>"
    f"<p style='color:#8899aa;font-size:1rem;margin:0;'>{nat}  ·  {pos}  ·  {club_label}  ·  {lg}</p>",
    unsafe_allow_html=True,
)
st.markdown("<br/>", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Overall", ovr)
m2.metric("Age", age)
m3.metric("Height", f"{ht} cm" if ht != "—" else "—")
m4.metric("Weight", f"{wt} kg" if wt != "—" else "—")

m5, m6, m7 = st.columns(3)
m5.metric("Foot", foot)
m6.metric("Skill Moves", f"{'★' * int(sm)}" if isinstance(sm, int) else sm)
m7.metric("Weak Foot", f"{'★' * int(wf)}" if isinstance(wf, int) else wf)

st.divider()

# ── Tabs ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
    padding: 10px 24px;
    font-size: 0.88rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}
</style>
""", unsafe_allow_html=True)

tab_stats, tab_shots, tab_xg, tab_value, tab_price, tab_fit = st.tabs([
    "📈 Radar Stats",
    "🎯 Shot Map",
    "⚡ xG Timeline",
    "💰 Market Value",
    "🔮 Price Prediction",
    "🤝 Club Fit",
])

season = "2024-2025"

# ── Tab: Radar ───────────────────────────────────────────────────────────────
with tab_stats:
    st.subheader("Statistical Radar")
    pos_group = _pos_to_group(player.get("position_code", "CM"))

    @st.cache_data(ttl=172800, show_spinner=False)
    def load_player_stats(pname, lg_id, szn):
        try:
            df = get_league_stats(lg_id, szn)
            if df.empty:
                return None, None
            stats = get_player_stats(pname, lg_id, szn)
            if not stats:
                return None, None
            return stats, df.to_dict(orient="records")
        except Exception:
            return None, None

    with st.spinner("Loading stats…"):
        stats, league_records = load_player_stats(name, TOP_5_LEAGUES.get(league, {}).get("fbref_id", "9"), season)

    if stats is not None and league_records is not None:
        try:
            import pandas as _pd
            league_df = _pd.DataFrame(league_records)
            percentiles = get_player_percentiles(stats, pos_group, league_df)
            fig = build_radar_chart(percentiles, name, pos_group)
            if fig:
                st.pyplot(fig)
        except Exception as e:
            st.warning(f"Radar chart error: {e}")
    else:
        # Fallback: use EA attributes directly
        attrs = {
            "Pace": player.get("pac", 0),
            "Shooting": player.get("sho", 0),
            "Passing": player.get("pas", 0),
            "Dribbling": player.get("dri", 0),
            "Defending": player.get("def_", 0),
            "Physicality": player.get("phy", 0),
        }
        if any(attrs.values()):
            st.markdown("**EA FC Attributes**")
            cols = st.columns(6)
            for i, (label, val) in enumerate(attrs.items()):
                with cols[i]:
                    color = "#3ddc84" if val >= 80 else "#c9a84c" if val >= 65 else "#ff5555"
                    st.markdown(
                        f"<div style='text-align:center;background:#111e2e;border:1px solid #1e3045;"
                        f"border-radius:10px;padding:12px 8px;'>"
                        f"<div style='font-size:1.6rem;font-weight:700;color:{color};'>{val}</div>"
                        f"<div style='font-size:.72rem;color:#8899aa;margin-top:4px;'>{label}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No stats available for this player.")

# ── Tab: Shot Map ────────────────────────────────────────────────────────────
with tab_shots:
    st.subheader("Shot Map")

    @st.cache_data(ttl=86400, show_spinner=False)
    def load_understat_id(pname, lg_name):
        try:
            result = search_player_understat(pname, lg_name, "2024")
            return result.get("id") if result else None
        except Exception:
            return None

    @st.cache_data(ttl=86400, show_spinner=False)
    def load_shots(pid, szn):
        try:
            return get_player_shots(pid, season=szn)
        except Exception:
            return None

    understat_league = TOP_5_LEAGUES.get(league, {}).get("understat_name", "EPL")
    with st.spinner("Loading shot data…"):
        us_id = load_understat_id(name, understat_league)
        shots = load_shots(us_id, "2024") if us_id else None

    if shots:
        try:
            fig = build_shot_map(shots, name)
            if fig:
                st.pyplot(fig)
        except Exception as e:
            st.warning(f"Shot map error: {e}")
    elif us_id:
        # Fallback: embed Understat iframe
        import streamlit.components.v1 as _comp_shots
        us_url = get_player_understat_url(us_id)
        st.caption(f"Source: [understat.com]({us_url})")
        _comp_shots.iframe(us_url, height=620, scrolling=True)
    else:
        st.info("Shot data not available — player not found on Understat for this league/season.")

# ── Tab: xG Timeline ─────────────────────────────────────────────────────────
with tab_xg:
    st.subheader("xG + Goals Timeline")

    @st.cache_data(ttl=86400, show_spinner=False)
    def load_xg(pid, szn):
        try:
            return get_player_xg_timeline(pid, szn) if pid else None
        except Exception:
            return None

    with st.spinner("Loading xG timeline…"):
        xg_data = load_xg(us_id, "2024")

    if xg_data:
        try:
            fig = build_xg_timeline(xg_data, name)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"xG timeline error: {e}")
    else:
        st.info("xG data not available for this player.")

# ── Tab: Market Value ─────────────────────────────────────────────────────────
with tab_value:
    st.subheader("Market Value History")

    @st.cache_data(ttl=86400, show_spinner=False)
    def load_mv(pid):
        try:
            from data.scrapers.transfermarkt import get_player_market_value_history
            return get_player_market_value_history(pid)
        except Exception:
            return None

    tm_id = player.get("tm_id") or player.get("player_id")
    if tm_id:
        with st.spinner("Loading market value history…"):
            mv_history = load_mv(str(tm_id))
        if mv_history:
            try:
                fig = build_market_value_chart(mv_history, name)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Chart error: {e}")
        else:
            st.info("Market value history not available.")
    else:
        mv = player.get("market_value_m")
        if mv:
            st.metric("Current Market Value", f"€{mv:.1f}M")
        else:
            st.info("Market value data not available.")

# ── Tab: Price Prediction ─────────────────────────────────────────────────────
with tab_price:
    st.subheader("Transfer Fee Prediction")

    with st.spinner("Generating price prediction…"):
        try:
            pred = predict_transfer_fee(player, league)
        except Exception as e:
            pred = None
            st.error(f"Prediction error: {e}")

    if pred:
        fig = build_price_gauge(pred, name)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        col_lo, col_med, col_hi = st.columns(3)
        col_lo.metric("Low Estimate", f"€{pred['lower_m']:.0f}M")
        col_med.metric("Median Estimate", f"€{pred['median_m']:.0f}M")
        col_hi.metric("High Estimate", f"€{pred['upper_m']:.0f}M")

        st.markdown(f"**Confidence:** {pred.get('confidence','')}")
        for r in pred.get("reasoning", []):
            st.write(f"• {r}")

# ── Tab: Club Fit ─────────────────────────────────────────────────────────────
with tab_fit:
    st.subheader("Club Fit Analysis")

    st.markdown("Check how this player would fit at another club:")
    target_league = st.selectbox("Target League", list(TOP_5_LEAGUES.keys()), key="fit_league")
    target_clubs = get_clubs_for_league(target_league)
    target_club_name = st.selectbox("Target Club", [c["name"] for c in target_clubs], key="fit_club")
    target_club = next(c for c in target_clubs if c["name"] == target_club_name)

    if st.button("Analyse Fit"):
        with st.spinner(f"Loading {target_club_name} squad…"):

            @st.cache_data(ttl=86400, show_spinner=False)
            def load_target_squad(slug, tid, ln):
                return get_enriched_squad(slug, tid, ln)

            target_squad = load_target_squad(target_club["tm_slug"], target_club["tm_id"], target_league)

        if target_squad:
            try:
                result = fit_analysis(player, target_squad, target_club_name)
                score = result.get("overall_fit_score", 0)
                grade = result.get("fit_grade", "C")

                grade_color = {"A+": "#3ddc84", "A": "#3ddc84", "B+": "#c9a84c", "B": "#c9a84c",
                               "C+": "#ff8c00", "C": "#ff8c00"}.get(grade, "#ff5555")

                st.markdown(
                    f"<div style='background:#111e2e;border:1px solid #2a4560;border-radius:12px;"
                    f"padding:20px;text-align:center;'>"
                    f"<div style='font-size:3rem;font-weight:700;color:{grade_color};'>{grade}</div>"
                    f"<div style='color:#8899aa;margin-top:4px;'>Fit Score: {score:.0f}/100</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                col_pos, col_neg = st.columns(2)
                with col_pos:
                    st.markdown("**✅ Will Thrive In**")
                    for item in result.get("thrives", []):
                        st.write(f"• {item}")
                with col_neg:
                    st.markdown("**⚠️ Must Adapt To**")
                    for item in result.get("must_adapt", []):
                        st.write(f"• {item}")
            except Exception as e:
                st.error(f"Fit analysis error: {e}")
        else:
            st.warning("Could not load target squad data.")
