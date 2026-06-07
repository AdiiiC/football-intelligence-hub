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
from data.scrapers.understat import (
    search_player_understat, get_player_xg_timeline,
    get_player_shots, get_player_understat_url, get_player_season_summary,
)
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
us_season = "2025"  # Understat season key: "2025" = 2025/26, "2024" = 2024/25

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
    def load_understat_id(pname, lg_name, szn):
        try:
            result = search_player_understat(pname, lg_name, szn)
            return result.get("id") if result else None
        except Exception:
            return None

    @st.cache_data(ttl=86400, show_spinner=False)
    def load_shots(pid, szn):
        try:
            return get_player_shots(pid, season=szn)
        except Exception:
            return None

    @st.cache_data(ttl=86400, show_spinner=False)
    def load_season_summary(pid):
        try:
            return get_player_season_summary(pid)
        except Exception:
            return []

    understat_league = TOP_5_LEAGUES.get(league, {}).get("understat_name", "EPL")
    with st.spinner("Loading shot data…"):
        us_id = load_understat_id(name, understat_league, us_season)
        shots = load_shots(us_id, us_season) if us_id else None
        season_summary = load_season_summary(us_id) if us_id else []

    # ── Season stats table ───────────────────────────────────────────────────
    if season_summary:
        import pandas as _pd_shots
        df_ss = _pd_shots.DataFrame(season_summary)
        df_ss = df_ss.rename(columns={
            "season": "Season", "team": "Club", "apps": "Apps",
            "minutes": "Mins", "goals": "G", "assists": "A",
            "shots": "Sh", "xG": "xG", "xA": "xA",
            "xG90": "xG/90", "xA90": "xA/90",
        })
        st.markdown("**Season Summary**")
        st.dataframe(
            df_ss, hide_index=True, use_container_width=True,
            column_config={
                "xG":    st.column_config.NumberColumn(format="%.2f"),
                "xA":    st.column_config.NumberColumn(format="%.2f"),
                "xG/90": st.column_config.NumberColumn(format="%.2f"),
                "xA/90": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.markdown("---")

    # ── Shot map ─────────────────────────────────────────────────────────────
    if shots:
        try:
            fig = build_shot_map(shots, name)
            if fig:
                st.pyplot(fig)
            goals_cnt = sum(1 for s in shots if s.get("result", "").lower() == "goal")
            total_xg  = sum(s.get("xg", 0) for s in shots)
            c1, c2, c3 = st.columns(3)
            c1.metric("Shots", len(shots))
            c2.metric("Goals", goals_cnt)
            c3.metric("xG", f"{total_xg:.2f}")
        except Exception as e:
            st.warning(f"Shot map error: {e}")
    elif us_id:
        st.info("No shots recorded for this player in the current season.")
    else:
        st.info("Player not found on Understat for this league/season.")

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
        xg_data = load_xg(us_id, us_season)

    if xg_data:
        try:
            fig = build_xg_timeline(xg_data, name)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

            # Key metrics row
            import pandas as _pd_xg
            df_xg = _pd_xg.DataFrame(xg_data)
            total_goals = int(df_xg["goals"].sum())
            total_xg_v  = float(df_xg["xg"].sum())
            total_ast   = int(df_xg["assists"].sum())
            xg_diff     = total_goals - total_xg_v
            diff_label  = f"+{xg_diff:.2f}" if xg_diff >= 0 else f"{xg_diff:.2f}"
            diff_color  = "#3ddc84" if xg_diff >= 0 else "#ff5555"

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Games", len(xg_data))
            c2.metric("Goals", total_goals)
            c3.metric("xG", f"{total_xg_v:.2f}")
            c4.metric("G − xG", diff_label, delta_color="normal")

            # Per-match detail table
            with st.expander("Per-match breakdown"):
                df_display = df_xg[["date", "home_team", "away_team", "xg", "goals", "assists", "time_played"]].copy()
                df_display.columns = ["Date", "Home", "Away", "xG", "G", "A", "Mins"]
                df_display["Date"] = df_display["Date"].str[:10]
                st.dataframe(df_display, hide_index=True, use_container_width=True,
                             column_config={"xG": st.column_config.NumberColumn(format="%.2f")})

            # ── Rolling 5-game form tracker ───────────────────────────────────
            st.markdown("---")
            st.subheader("🔥 Last 5 Games — Form Tracker")
            last5 = xg_data[-5:]
            if len(last5) >= 1:
                l5_goals = sum(m["goals"] for m in last5)
                l5_xg    = sum(m["xg"] for m in last5)
                l5_ast   = sum(m.get("assists", 0) for m in last5)
                avg_xg5  = l5_xg / len(last5)
                season_avg_xg = total_xg_v / len(xg_data) if xg_data else 0

                # Form indicator
                if avg_xg5 >= season_avg_xg * 1.25:
                    form_icon, form_label, form_color = "🔥", "Hot Form", "#3ddc84"
                elif avg_xg5 >= season_avg_xg * 0.75:
                    form_icon, form_label, form_color = "📈", "Steady",   "#c9a84c"
                else:
                    form_icon, form_label, form_color = "❄️", "Cold Spell","#5dade2"

                st.markdown(
                    f"<div style='background:#111e2e;border:1px solid #2a4560;border-radius:10px;"
                    f"padding:14px 20px;display:flex;align-items:center;gap:16px;'>"
                    f"<span style='font-size:2.4rem;'>{form_icon}</span>"
                    f"<div><div style='font-size:1.2rem;font-weight:700;color:{form_color};'>{form_label}</div>"
                    f"<div style='color:#8899aa;font-size:.85rem;'>Last {len(last5)} games: "
                    f"{l5_goals}G / {l5_ast}A / {l5_xg:.2f} xG (avg {avg_xg5:.2f}/game)</div></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Mini table
                l5_rows = []
                for m in reversed(last5):
                    opp = m.get("away_team") if m.get("home_team") else m.get("home_team")
                    l5_rows.append({
                        "Date": m["date"][:10],
                        "Opponent": opp or "—",
                        "G": m["goals"],
                        "A": m.get("assists", 0),
                        "xG": round(m["xg"], 2),
                        "Mins": m.get("time_played", "—"),
                    })
                import pandas as _pd_form
                st.dataframe(_pd_form.DataFrame(l5_rows), hide_index=True, use_container_width=True,
                             column_config={"xG": st.column_config.NumberColumn(format="%.2f")})

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

# ── PDF Export ───────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📄 Download Scout Report")

if st.button("Generate PDF Scout Report"):
    from ui.export.pdf_report import generate_scout_report_pdf
    with st.spinner("Building PDF…"):
        _fbref = st.session_state.get("_fbref_stats_cache")
        _fit   = st.session_state.get("_fit_result_cache")
        pdf_bytes = generate_scout_report_pdf(player, fit_result=_fit, fbref_stats=_fbref)
    if pdf_bytes:
        pname = player.get("name", "player").replace(" ", "_")
        st.download_button(
            label="⬇️ Download Scout Report PDF",
            data=pdf_bytes,
            file_name=f"scout_report_{pname}.pdf",
            mime="application/pdf",
        )
    else:
        st.warning("PDF generation requires `reportlab`. Install with: `pip install reportlab`")
