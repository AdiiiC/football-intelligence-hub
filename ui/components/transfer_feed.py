"""
Transfer news feed component — styled cards for confirmed deals and rumours.
"""

import streamlit as st
import streamlit.components.v1 as _stcomp
from datetime import datetime


def _render_cards_iframe(items: list, height_per_item: int = 85) -> None:
    """Render a list of transfer cards in a components.v1.html iframe (bypasses CSP)."""
    cards_html = "".join(render_transfer_card(item) for item in items)
    full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>body{{margin:0;padding:4px;background:transparent;font-family:'Inter',system-ui,sans-serif;}}</style>
    </head><body>{cards_html}</body></html>"""
    height = max(120, len(items) * height_per_item + 20)
    _stcomp.html(full_html, height=height, scrolling=False)


def _direction_badge(direction: str) -> str:
    if direction == "in":
        return '<span style="background:#1a5c2a;color:#27ae60;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">IN ↓</span>'
    return '<span style="background:#5c1a1a;color:#e74c3c;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">OUT ↑</span>'


def _type_badge(t: str) -> str:
    if t == "confirmed":
        return '<span style="background:#1a5c2a;color:#2ecc71;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700;">✓ CONFIRMED</span>'
    return '<span style="background:#5c4a00;color:#f5c518;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700;">◎ RUMOUR</span>'


def _deal_type_badge(deal_type: str) -> str:
    if deal_type == "loan":
        return '<span style="background:#0d2a4a;color:#5dade2;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700;">⟳ LOAN</span>'
    return '<span style="background:#2a1a4a;color:#a569bd;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700;">⇄ PERMANENT</span>'


def _window_badge(window: str) -> str:
    """Summer YYYY = amber, Winter YYYY = icy blue."""
    if window.lower().startswith("winter"):
        return f'<span style="background:#0a2a2a;color:#48c9b0;padding:2px 7px;border-radius:10px;font-size:9px;font-weight:600;">❄ {window}</span>'
    return f'<span style="background:#2a2000;color:#f0b429;padding:2px 7px;border-radius:10px;font-size:9px;font-weight:600;">☀ {window}</span>'


def render_transfer_card(item: dict) -> str:
    name = item.get("name", "Unknown Player")
    direction = item.get("direction", "in")
    club = item.get("club", "") or ""
    fee = item.get("fee_m", 0) or 0
    deal_type = item.get("deal_type", "permanent")
    window = item.get("window", "")
    fee_str = f"€{fee:.0f}m" if fee and fee > 0 else ("Loan fee TBC" if deal_type == "loan" else "Fee undisclosed")
    pos = item.get("position", "") or ""
    source = item.get("source", "transfermarkt.com") or "transfermarkt.com"
    mv = item.get("market_value_m", 0) or 0
    item_type = item.get("type", "rumour")
    photo_url = item.get("photo_url", "") or ""
    date = item.get("date", "") or ""

    direction_label = "FROM" if direction == "in" else "TO"
    accent = "#27ae60" if direction == "in" else "#e74c3c"

    # Player photo — always show initials, overlay real photo if available
    initials = "".join(p[0].upper() for p in name.split()[:2]) if name else "?"
    # Hash name to pick a consistent accent color for initials
    hue = sum(ord(c) for c in name) % 360
    init_bg = f"hsl({hue},40%,25%)"
    init_color = f"hsl({hue},70%,65%)"

    if photo_url and not photo_url.startswith("data:"):
        # Overlay img on top of initials; if img loads with real content it shows,
        # onerror hides it and initials remain visible
        avatar_html = f"""
        <div style="position:relative;width:52px;height:52px;flex-shrink:0;">
          <div style="position:absolute;top:0;left:0;width:52px;height:52px;border-radius:50%;
            border:2px solid {accent};background:{init_bg};
            display:flex;align-items:center;justify-content:center;
            font-size:15px;font-weight:700;color:{init_color};">{initials}</div>
          <img src="{photo_url}"
            style="position:absolute;top:0;left:0;width:52px;height:52px;object-fit:cover;
              border-radius:50%;border:2px solid {accent};"
            onerror="this.style.display='none'"
            onload="if(this.naturalWidth<10)this.style.display='none'">
        </div>"""
    else:
        avatar_html = (
            f'<div style="width:52px;height:52px;border-radius:50%;border:2px solid {accent};'
            f'background:{init_bg};display:flex;align-items:center;justify-content:center;'
            f'font-size:15px;font-weight:700;color:{init_color};flex-shrink:0;">{initials}</div>'
        )

    # Bottom meta line
    if item_type == "confirmed":
        meta = fee_str
        if pos:
            meta += f" · {pos}"
    else:
        meta = f"MV: €{mv:.0f}m" if mv else ""
        if date:
            meta += f" · {date}" if meta else date

    return f"""
    <div style="
        background: linear-gradient(135deg, #111827, #1a1a2e);
        border-left: 3px solid {accent};
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 8px;
        font-family: Inter, sans-serif;
        display: flex;
        align-items: center;
        gap: 12px;
    ">
        {avatar_html}
        <div style="flex:1;min-width:0;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">
                <span style="font-weight:700;color:#fff;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</span>
                <div style="display:flex;gap:4px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end;">
                    {_window_badge(window) if window and item_type == "confirmed" else ""}
                    {_direction_badge(direction) if item_type == "confirmed" else ""}
                    {_deal_type_badge(deal_type) if item_type == "confirmed" else ""}
                    {_type_badge(item_type)}
                </div>
            </div>
            {f'<div style="color:{accent};font-size:11px;margin-top:3px;"><b>{direction_label}:</b> {club}</div>' if club else ""}
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;">
                {f'<span style="color:#888;font-size:10px;">{meta}</span>' if meta else '<span></span>'}
                <span style="color:#555;font-size:9px;text-align:right;">Source: {source}</span>
            </div>
        </div>
    </div>
    """


def render_transfer_feed(news, club_name: str) -> None:
    """
    Render the full transfer feed with tabs for confirmed / rumours.
    Accepts either a flat list of items or a dict {"confirmed": [...], "rumours": [...]}.
    """
    if isinstance(news, dict):
        confirmed = news.get("confirmed", [])
        rumours = news.get("rumours", [])
    else:
        confirmed = [n for n in news if isinstance(n, dict) and n.get("type") == "confirmed"]
        rumours = [n for n in news if isinstance(n, dict) and n.get("type") == "rumour"]

    st.markdown(f"""
    <div style="
        background: #0d1b2a;
        border: 1px solid #c9a84c33;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 16px;
    ">
        <h3 style="color:#c9a84c;margin:0 0 4px 0;font-size:16px;">⚡ Transfer Activity — {club_name}</h3>
        <p style="color:#666;font-size:11px;margin:0;">{len(confirmed)} confirmed · {len(rumours)} rumours</p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs([f"✅ Confirmed ({len(confirmed)})", f"🔶 Rumours ({len(rumours)})"])

    with tab1:
        if not confirmed:
            st.info("No confirmed transfers found for this club.")
        else:
            # Ins then Outs
            ins = [t for t in confirmed if t.get("direction") == "in"]
            outs = [t for t in confirmed if t.get("direction") == "out"]

            if ins:
                st.markdown("##### Arrivals")
                _render_cards_iframe(ins)
            if outs:
                st.markdown("##### Departures")
                _render_cards_iframe(outs)

    with tab2:
        if not rumours:
            st.info("No transfer rumours found for this club.")
        else:
            _render_cards_iframe([{**item, "direction": "in"} for item in rumours])


def render_ticker(news) -> None:
    """A compact scrolling-style ticker of transfer headlines.
    Accepts either a list of items or a dict with 'confirmed'/'rumours' keys."""
    if isinstance(news, dict):
        all_items = news.get("confirmed", []) + news.get("rumours", [])
    else:
        all_items = list(news)
    if not all_items:
        return

    headlines = []
    for item in all_items[:12]:
        name = item.get("name", "?")
        club = item.get("club", "")
        direction = "→" if item.get("direction") == "out" else "←"
        t = "✓" if item.get("type") == "confirmed" else "◎"
        deal = " [LOAN]" if item.get("deal_type") == "loan" else ""
        win = f" [{item['window']}]" if item.get("window") else ""
        headlines.append(f"{t} {name}{deal}{win} {direction} {club}")

    ticker_text = "  &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp;  ".join(headlines)

    st.markdown(f"""
    <div style="
        background:#111827;
        border:1px solid #c9a84c44;
        border-radius:6px;
        padding:8px 16px;
        overflow:hidden;
        white-space:nowrap;
        font-size:11px;
        color:#c9a84c;
        font-family:Inter,sans-serif;
        letter-spacing:0.3px;
    ">
        {ticker_text}
    </div>
    """, unsafe_allow_html=True)
