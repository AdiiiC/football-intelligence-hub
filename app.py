"""
Football Intelligence Hub — Main Entry Point
Run: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Football Intelligence Hub",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load dark luxury CSS ────────────────────────────────────────────────────
from pathlib import Path

_CSS_FILE = Path(__file__).parent / "ui" / "styles" / "theme.css"
if _CSS_FILE.exists():
    st.markdown(f"<style>{_CSS_FILE.read_text()}</style>", unsafe_allow_html=True)

# ── Sidebar branding ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style='text-align:center;padding:18px 0 10px;'>
          <span style='font-size:2.6rem;'>⚽</span>
          <h2 style='margin:6px 0 2px;color:#c9a84c;letter-spacing:1px;font-size:1.3rem;'>
            FOOTBALL INTELLIGENCE
          </h2>
          <p style='color:#8899aa;font-size:0.75rem;margin:0;letter-spacing:2px;'>POWERED BY EA FC 26 DATA</p>
        </div>
        <hr style='border-color:#2a3a4a;margin:8px 0 16px;'/>
        """,
        unsafe_allow_html=True,
    )

# ── Home page content ────────────────────────────────────────────────────────
st.markdown(
    """
    <div style='text-align:center;padding:60px 20px 40px;'>
      <h1 style='font-size:3rem;color:#c9a84c;letter-spacing:2px;margin-bottom:12px;'>
        ⚽ Football Intelligence Hub
      </h1>
      <p style='font-size:1.2rem;color:#a0b4c8;max-width:600px;margin:0 auto 40px;'>
        Real-time squad analysis, transfer intelligence, and player insights
        across Europe's Top 5 leagues — powered by live EA FC data.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)

_CARD_STYLE = """
<a href="{url}" target="_self" style="text-decoration:none;">
  <div style="
    background:linear-gradient(135deg,#0d1b2a,#1a2d40);
    border:1px solid #2a3a4a;
    border-radius:12px;
    padding:28px 20px;
    text-align:center;
    transition:all .2s;
    cursor:pointer;
  ">
    <div style="font-size:2.5rem;margin-bottom:10px;">{icon}</div>
    <h3 style="color:#c9a84c;margin:0 0 8px;font-size:1.1rem;">{title}</h3>
    <p style="color:#7a8fa0;font-size:0.82rem;margin:0;">{desc}</p>
  </div>
</a>
"""

with col1:
    st.markdown(
        _CARD_STYLE.format(
            url="Squad_Overview",
            icon="🏟",
            title="Squad Overview",
            desc="Formation viewer, FIFA cards, squad depth analysis",
        ),
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        _CARD_STYLE.format(
            url="Transfer_Targets",
            icon="🎯",
            title="Transfer Targets",
            desc="AI buy/sell recommendations and squad weakness analysis",
        ),
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        _CARD_STYLE.format(
            url="Player_Profile",
            icon="📊",
            title="Player Profile",
            desc="Deep stats, xG timeline, radar chart, price prediction",
        ),
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        _CARD_STYLE.format(
            url="Transfer_News",
            icon="📰",
            title="Transfer News",
            desc="Live confirmed transfers and rumour feed from Transfermarkt",
        ),
        unsafe_allow_html=True,
    )

# ── Quick league stats strip ────────────────────────────────────────────────
st.markdown("<br/>", unsafe_allow_html=True)
st.markdown(
    """
    <div style='display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin:10px 0;'>
      <span style='background:#0d1b2a;border:1px solid #2a3a4a;border-radius:8px;padding:8px 18px;color:#e0e8f0;font-size:0.88rem;'>🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League</span>
      <span style='background:#0d1b2a;border:1px solid #2a3a4a;border-radius:8px;padding:8px 18px;color:#e0e8f0;font-size:0.88rem;'>🇪🇸 La Liga</span>
      <span style='background:#0d1b2a;border:1px solid #2a3a4a;border-radius:8px;padding:8px 18px;color:#e0e8f0;font-size:0.88rem;'>🇩🇪 Bundesliga</span>
      <span style='background:#0d1b2a;border:1px solid #2a3a4a;border-radius:8px;padding:8px 18px;color:#e0e8f0;font-size:0.88rem;'>🇮🇹 Serie A</span>
      <span style='background:#0d1b2a;border:1px solid #2a3a4a;border-radius:8px;padding:8px 18px;color:#e0e8f0;font-size:0.88rem;'>🇫🇷 Ligue 1</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    "<p style='text-align:center;color:#4a6070;font-size:0.75rem;margin-top:50px;'>"
    "Data: EA FC 26 Official Ratings · Transfermarkt · FBref · Understat"
    "</p>",
    unsafe_allow_html=True,
)
