"""
FIFA-style player card rendered as HTML via Streamlit components.
Uses real EA FC 26 attributes and official EA portrait URLs.

Images are fetched server-side and embedded as base64 data URIs to bypass
Streamlit's Content Security Policy which blocks external img src in st.markdown.
"""

import base64
import hashlib
import requests
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from config.settings import CACHE_DIR

# ── Image cache (disk) ────────────────────────────────────────────────────────
_IMG_CACHE_DIR = Path(CACHE_DIR) / "img"
_IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_IMG_SESSION = requests.Session()
_IMG_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

# Name particles that belong with the surname on cards
_PARTICLES = {"de", "van", "der", "den", "von", "la", "le", "del", "di", "da", "dos", "bin", "al", "el", "lo"}


def _surname(name: str) -> str:
    """Return display surname, preserving particles: 'Frenkie de Jong' → 'DE JONG'."""
    parts = name.split() if name else []
    if len(parts) >= 3 and parts[-2].lower() in _PARTICLES:
        return (parts[-2] + " " + parts[-1]).upper()
    return parts[-1].upper() if parts else name.upper()


def _img_to_data_uri(url: str) -> str:
    """
    Fetch image URL and return as base64 data URI.
    Caches to disk so each portrait is only downloaded once.
    Returns empty string on failure.
    """
    if not url:
        return ""
    key = hashlib.md5(url.encode()).hexdigest()
    cache_file = _IMG_CACHE_DIR / f"{key}.b64"
    if cache_file.exists():
        return cache_file.read_text()
    try:
        resp = _IMG_SESSION.get(url, timeout=8)
        if resp.status_code != 200 or not resp.content:
            return ""
        ext = "png" if "png" in url.lower() else "jpeg"
        b64 = base64.b64encode(resp.content).decode()
        data_uri = f"data:image/{ext};base64,{b64}"
        cache_file.write_text(data_uri)
        return data_uri
    except Exception:
        return ""


def prefetch_images(players: list) -> None:
    """
    Pre-warm the image cache for a list of players using parallel downloads.
    Call this before rendering a card grid so images are ready instantly.
    """
    urls = [p.get("ea_avatar_url") or p.get("photo_url", "") for p in players]
    urls = [u for u in urls if u]
    uncached = [u for u in urls if not (_IMG_CACHE_DIR / f"{hashlib.md5(u.encode()).hexdigest()}.b64").exists()]
    if not uncached:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_img_to_data_uri, uncached))


# ---------------------------------------------------------------------------
# Card tier definitions
# ---------------------------------------------------------------------------
CARD_TIERS = [
    (91, "TOTY",   "#ffd700", "#1a0800"),
    (88, "IF",     "#d4af37", "#1a0800"),
    (83, "GOLD",   "#c9a84c", "#0d0d00"),
    (75, "SILVER", "#aaaaaa", "#111111"),
    (0,  "BRONZE", "#cd7f32", "#110800"),
]

POSITION_COLORS = {
    "GK":  "#f5c518",
    "CB":  "#27ae60", "LB": "#2ecc71", "RB": "#2ecc71",
    "LWB": "#16a085", "RWB": "#16a085",
    "DM":  "#2980b9", "CM": "#3498db", "AM": "#8e44ad",
    "LM":  "#1abc9c", "RM": "#1abc9c",
    "LW":  "#e67e22", "RW": "#e67e22",
    "ST":  "#c0392b", "CF": "#e74c3c",
    "Winger": "#e67e22", "FB": "#2ecc71",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_attr(player: dict, *keys, default: int = 50) -> int:
    """Pull an integer attribute from player dict, trying multiple key names."""
    for k in keys:
        v = player.get(k)
        if v is not None:
            try:
                return max(1, min(99, int(float(v))))
            except (ValueError, TypeError):
                pass
    return default


def _card_tier(overall: int) -> tuple:
    for threshold, label, gold, bg in CARD_TIERS:
        if overall >= threshold:
            return label, gold, bg
    return "BRONZE", "#cd7f32", "#110800"


def _stat_bar(label: str, value: int) -> str:
    pct = min(99, max(1, value))
    color = (
        "#00d4aa" if pct >= 85 else
        "#f5c518" if pct >= 75 else
        "#e67e22" if pct >= 65 else
        "#e74c3c"
    )
    return f"""
    <div style="display:flex;align-items:center;gap:5px;margin:3px 0;">
        <span style="width:24px;font-weight:900;font-size:12px;color:{color};text-align:right;">{pct}</span>
        <div style="flex:1;background:rgba(255,255,255,0.1);border-radius:3px;height:4px;overflow:hidden;">
            <div style="width:{pct}%;background:{color};height:100%;border-radius:3px;
                        box-shadow:0 0 4px {color}88;"></div>
        </div>
        <span style="font-size:8px;color:rgba(255,255,255,0.55);width:24px;text-transform:uppercase;">{label}</span>
    </div>
    """


def _initials_avatar(player: dict, size: str = "80px") -> str:
    """Generate a colored initials circle as image fallback."""
    name = player.get("name", "?")
    parts = name.split()
    if len(parts) >= 2:
        initials = parts[0][0].upper() + parts[-1][0].upper()
    else:
        initials = name[:2].upper()
    # Deterministic color from name hash
    h = sum(ord(c) for c in name) % 360
    bg = f"hsl({h}, 55%, 28%)"
    border = f"hsl({h}, 65%, 45%)"
    font_size = str(int(size.replace("px","")) // 3) + "px"
    return (
        f'<div style="width:{size};height:{size};border-radius:50%;background:{bg};'
        f'border:2px solid {border};display:flex;align-items:center;'
        f'justify-content:center;font-size:{font_size};font-weight:700;'
        f'color:#fff;flex-shrink:0;">{initials}</div>'
    )


def _build_image_html(player: dict, size: str = "80px") -> str:
    """
    Return player portrait with initials circle always as base layer.
    The <img> sits on top; onerror hides it, revealing the initials.
    """
    url = (
        player.get("ea_avatar_url") or
        player.get("sofifa_face_url") or
        player.get("photo_url") or
        ""
    )
    name = player.get("name", "?")
    parts = name.split()
    initials = (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else name[:2].upper()
    h = sum(ord(c) for c in name) % 360
    bg = f"hsl({h},55%,28%)"
    border_col = f"hsl({h},65%,45%)"
    sz = int(size.replace("px", ""))
    fs = sz // 3

    # Always render initials as solid background; img layered on top
    # overflow:hidden clips the absolute img to the border-radius circle
    img_tag = (
        f'<img src="{url}" '
        f'style="position:absolute;inset:0;width:100%;height:100%;'
        f'object-fit:cover;border-radius:50%;" '
        f'onerror="this.style.display=\'none\'" />'
        if url else ""
    )
    return (
        f'<div style="position:relative;width:{size};height:{size};'
        f'border-radius:50%;background:{bg};border:2px solid {border_col};'
        f'display:flex;align-items:center;justify-content:center;'
        f'font-size:{fs}px;font-weight:700;color:#fff;flex-shrink:0;'
        f'overflow:hidden;">'
        f'{initials}{img_tag}'
        f'</div>'
    )


def _estimate_overall_fallback(player: dict) -> int:
    """Market-value-based overall estimate when EA data is unavailable."""
    mv = player.get("market_value_m", 0) or 0
    fbref = player.get("fbref", {})
    if mv >= 100: base = 88
    elif mv >= 60: base = 84
    elif mv >= 30: base = 80
    elif mv >= 15: base = 76
    elif mv >= 5:  base = 72
    else:          base = 68
    xg = float(fbref.get("xg_per90", 0) or 0)
    return min(99, base + min(4, int(xg * 10)))


# ---------------------------------------------------------------------------
# Public card renderer
# ---------------------------------------------------------------------------

def render_fifa_card(player: dict, compact: bool = False, show_price: bool = False) -> str:
    """
    Returns HTML string for a FIFA Ultimate Team-style player card.
    Uses real EA FC 26 data (PAC/SHO/PAS/DRI/DEF/PHY) when available,
    falls back to FBref-derived estimates otherwise.
    Use with st.markdown(..., unsafe_allow_html=True).
    """
    # Real EA overall if available, else estimate
    overall = _get_attr(player, "overall", default=0) or _estimate_overall_fallback(player)
    tier_label, card_color, card_bg = _card_tier(overall)

    pos_code = player.get("position_code") or player.get("position_group", "MF")
    pos_accent = POSITION_COLORS.get(pos_code, "#c9a84c")

    name = player.get("short_name") or player.get("name", "Unknown")
    first = " ".join(name.split()[:-1]) if len(name.split()) > 1 else ""
    last = _surname(name)

    mv = player.get("market_value_m", 0) or 0
    mv_str = f"€{mv:.0f}m" if mv >= 1 else (f"€{int(mv*1000)}k" if mv > 0 else "—")

    nationality = player.get("nationality", "")
    age = player.get("age", "")
    contract = str(player.get("contract_expiry", ""))
    contract_warn = (
        '<span style="color:#e74c3c;font-size:8px;margin-left:2px;">⚠</span>'
        if any(yr in contract for yr in ["2025", "2026"]) else ""
    )

    # Real EA attributes — fallback to FBref proxies
    fbref = player.get("fbref", {})
    def _fb(k, default=0.0):
        try: return float(fbref.get(k, default) or default)
        except: return default

    pac = _get_attr(player, "pac", "pace",
                    default=min(99, 50 + int(_fb("progressive_carries") * 0.5)))
    sho = _get_attr(player, "sho", "shooting",
                    default=min(99, 40 + int(_fb("xg_per90") * 120)))
    pas = _get_attr(player, "pas", "passing",
                    default=min(99, int(_fb("passes_completed_pct") or 70)))
    dri = _get_attr(player, "dri", "dribbling",
                    default=min(99, 45 + int(_fb("dribbles_completed_pct") * 0.4)))
    def_ = _get_attr(player, "def_", "defending",
                     default=min(99, 40 + int((_fb("tackles_won") + _fb("interceptions")) * 2)))
    phy = _get_attr(player, "phy", "physic",
                    default=min(99, 50 + int(_fb("aerial_duels_won_pct") * 0.35)))

    img_size = "72px" if compact else "88px"
    img_html = _build_image_html(player, img_size)
    width = "165px" if compact else "210px"

    price_badge = ""
    if show_price and player.get("median_m"):
        price_badge = (
            f'<div style="background:rgba(201,168,76,0.15);border:1px solid {card_color};'
            f'border-radius:6px;padding:3px 6px;margin-top:6px;font-size:9px;'
            f'color:{card_color};font-weight:700;">💰 Est. €{player["median_m"]}m</div>'
        )

    return f"""
    <div style="
        background: linear-gradient(160deg, {card_bg} 0%, #1a1a2e 60%, #0d0d0d 100%);
        border: 2px solid {card_color};
        border-radius: 14px;
        padding: 14px 10px 10px;
        width: {width};
        font-family: 'Inter', 'Rajdhani', sans-serif;
        box-shadow: 0 6px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06);
        position: relative;
        text-align: center;
    ">
        <div style="position:absolute;top:10px;left:10px;text-align:left;line-height:1.1;">
            <div style="font-size:26px;font-weight:900;color:{card_color};letter-spacing:-1px;">{overall}</div>
            <div style="font-size:9px;color:{pos_accent};font-weight:800;letter-spacing:1px;">{pos_code}</div>
            <div style="font-size:7px;color:rgba(255,255,255,0.35);letter-spacing:1px;">{tier_label}</div>
        </div>

        <div style="display:flex;flex-direction:column;align-items:center;padding-left:18px;">
            <div style="border-radius:50%;border:2px solid {card_color};padding:2px;
                        box-shadow:0 0 12px {card_color}66;">
                {img_html}
            </div>
        </div>

        <div style="margin-top:6px;">
            <div style="font-size:14px;font-weight:900;color:#fff;letter-spacing:0.5px;">{last}</div>
            <div style="font-size:9px;color:rgba(255,255,255,0.45);margin-top:1px;">{first}</div>
        </div>

        <div style="display:flex;justify-content:center;gap:6px;margin:3px 0;flex-wrap:wrap;">
            <span style="font-size:8px;color:{card_color};font-weight:700;">{nationality}</span>
            {"<span style='font-size:8px;color:rgba(255,255,255,0.35);'>·</span>" if age else ""}
            <span style="font-size:8px;color:rgba(255,255,255,0.45);">{"Age " + str(age) if age else ""}</span>
        </div>

        <div style="font-size:11px;font-weight:800;color:{card_color};margin-bottom:2px;">
            {mv_str}{contract_warn}
        </div>

        <div style="border-top:1px solid rgba(255,255,255,0.08);margin:7px 0 5px;"></div>

        <div style="padding:0 4px;">
            {_stat_bar("PAC", pac)}
            {_stat_bar("SHO", sho)}
            {_stat_bar("PAS", pas)}
            {_stat_bar("DRI", dri)}
            {_stat_bar("DEF", def_)}
            {_stat_bar("PHY", phy)}
        </div>
        {price_badge}
    </div>
    """


def render_card_grid(players: list, cols: int = 4, show_price: bool = False) -> None:
    """
    Render a grid of FIFA cards using st.components.v1.html (iframe).
    This bypasses DOMPurify and allows external images from EA CDN.
    """
    import streamlit.components.v1 as components

    cards_html = "".join(render_fifa_card(p, show_price=show_price) for p in players)

    grid_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      body {{ margin:0; padding:0; background:transparent; }}
      .card-grid {{
        display: flex;
        flex-wrap: wrap;
        gap: 14px;
        padding: 4px 2px 12px;
        font-family: 'Inter', system-ui, sans-serif;
      }}
    </style>
    </head>
    <body>
      <div class="card-grid">
        {cards_html}
      </div>
    </body>
    </html>
    """

    # Calculate approximate height based on rows
    row_count = (len(players) + cols - 1) // cols
    height = row_count * 320 + 40
    components.html(grid_html, height=height, scrolling=False)


def render_single_card(player: dict, compact: bool = False, show_price: bool = False) -> None:
    """
    Render one FIFA card via components.v1.html (iframe).
    Use this instead of st.markdown(render_fifa_card(...)) to avoid CSP issues.
    """
    import streamlit.components.v1 as _comp
    card_html = render_fifa_card(player, compact=compact, show_price=show_price)
    full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>body{{margin:0;padding:0;background:transparent;font-family:'Inter',system-ui,sans-serif;}}</style>
    </head><body>{card_html}</body></html>"""
    height = 320 if compact else 360
    _comp.html(full_html, height=height, scrolling=False)


def render_player_hero_card(player: dict) -> str:
    """
    Large hero card for the Player Profile page.
    Shows full name, all 6 main attributes large + sub-attribute pills.
    """
    overall = _get_attr(player, "overall", default=0) or _estimate_overall_fallback(player)
    _, card_color, card_bg = _card_tier(overall)
    pos_code = player.get("position_code") or player.get("position_group", "MF")
    pos_accent = POSITION_COLORS.get(pos_code, "#c9a84c")

    name = player.get("name", "Unknown")
    nationality = player.get("nationality", "")
    age = player.get("age", "")
    club = player.get("club_name") or player.get("squad", "")
    mv = player.get("market_value_m", 0) or 0
    mv_str = f"€{mv:.0f}m" if mv >= 1 else (f"€{int(mv*1000)}k" if mv > 0 else "—")
    release = player.get("release_clause_eur", 0) or 0
    release_str = f"€{release/1e6:.0f}m" if release and release > 0 else "—"
    pot = player.get("potential", "")
    pot_str = f" / {pot} POT" if pot else ""

    pac = _get_attr(player, "pac", "pace", default=65)
    sho = _get_attr(player, "sho", "shooting", default=55)
    pas = _get_attr(player, "pas", "passing", default=60)
    dri = _get_attr(player, "dri", "dribbling", default=62)
    def_ = _get_attr(player, "def_", "defending", default=45)
    phy = _get_attr(player, "phy", "physic", default=65)

    img_html = _build_image_html(player, "120px")

    def attr_color(v):
        return "#00d4aa" if v >= 85 else ("#f5c518" if v >= 75 else ("#e67e22" if v >= 65 else "#e74c3c"))

    def attr_block(val, label):
        c = attr_color(val)
        return (f'<div style="flex:1;text-align:center;padding:10px 4px;">'
                f'<div style="font-size:26px;font-weight:900;color:{c};line-height:1;">{val}</div>'
                f'<div style="font-size:10px;color:rgba(255,255,255,0.45);font-weight:700;letter-spacing:1px;margin-top:2px;">{label}</div>'
                f'</div>')

    sub_attrs = {
        "Acceleration": _get_attr(player, "acceleration"),
        "Sprint Speed": _get_attr(player, "sprint_speed"),
        "Finishing":    _get_attr(player, "finishing"),
        "Long Shots":   _get_attr(player, "long_shots"),
        "Short Pass":   _get_attr(player, "short_passing"),
        "Long Pass":    _get_attr(player, "long_passing"),
        "Ball Control": _get_attr(player, "ball_control"),
        "Dribbling":    _get_attr(player, "dribbling_skill"),
        "Stamina":      _get_attr(player, "stamina"),
        "Strength":     _get_attr(player, "strength"),
        "Interceptions":_get_attr(player, "interceptions_attr"),
        "Marking":      _get_attr(player, "marking"),
        "Composure":    _get_attr(player, "composure"),
        "Reactions":    _get_attr(player, "reactions"),
        "Vision":       _get_attr(player, "vision"),
    }

    pills = "".join([
        f'<span style="background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);'
        f'border-radius:20px;padding:4px 10px;font-size:10px;color:rgba(255,255,255,0.7);white-space:nowrap;">'
        f'<span style="color:{attr_color(v)};font-weight:700;">{v}</span>&nbsp;{k}</span>'
        for k, v in sub_attrs.items() if v != 50
    ])

    play_styles = player.get("play_styles") or []
    style_pills = "".join(
        f'<span style="background:rgba(201,168,76,0.12);border:1px solid rgba(201,168,76,0.3);'
        f'border-radius:20px;padding:4px 10px;font-size:10px;color:{card_color};white-space:nowrap;">{ps}</span>'
        for ps in play_styles
    )

    return f"""
    <div style="
        background: linear-gradient(160deg, {card_bg} 0%, #0d1b2a 55%, #0a0a1a 100%);
        border: 2px solid {card_color};
        border-radius: 18px;
        padding: 20px 20px 16px;
        width: 100%;
        box-sizing: border-box;
        font-family: 'Inter', sans-serif;
        box-shadow: 0 8px 40px rgba(0,0,0,0.6);
    ">
        <!-- Top: portrait + overall -->
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px;">
            <div style="flex-shrink:0;">
                <div style="border-radius:50%;border:3px solid {card_color};padding:3px;
                            box-shadow:0 0 16px {card_color}55;display:inline-block;">
                    {img_html}
                </div>
            </div>
            <div>
                <div style="font-size:48px;font-weight:900;color:{card_color};line-height:1;">{overall}</div>
                <div style="font-size:14px;color:{pos_accent};font-weight:800;letter-spacing:2px;">{pos_code}</div>
                {f'<div style="font-size:10px;color:rgba(255,255,255,0.3);margin-top:2px;">{pot_str}</div>' if pot_str else ""}
            </div>
            <div style="flex:1;text-align:right;">
                <div style="font-size:20px;font-weight:900;color:#fff;">{name}</div>
                <div style="font-size:12px;color:{card_color};margin-top:2px;font-weight:600;">{club}</div>
                <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:2px;">{nationality} · Age {age}</div>
                <div style="margin-top:6px;display:flex;justify-content:flex-end;gap:16px;">
                    <div>
                        <div style="font-size:8px;color:rgba(255,255,255,0.3);letter-spacing:1px;">MARKET VALUE</div>
                        <div style="font-size:14px;font-weight:900;color:{card_color};">{mv_str}</div>
                    </div>
                    <div>
                        <div style="font-size:8px;color:rgba(255,255,255,0.3);letter-spacing:1px;">RELEASE</div>
                        <div style="font-size:14px;font-weight:700;color:#e74c3c;">{release_str}</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 6 attributes bar -->
        <div style="display:flex;border-top:1px solid rgba(255,255,255,0.08);
                    border-bottom:1px solid rgba(255,255,255,0.08);padding:4px 0;margin-bottom:12px;">
            {attr_block(pac, "PAC")}
            {attr_block(sho, "SHO")}
            {attr_block(pas, "PAS")}
            {attr_block(dri, "DRI")}
            {attr_block(def_, "DEF")}
            {attr_block(phy, "PHY")}
        </div>

        {f'''<!-- Play styles -->
        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;">
            {style_pills}
        </div>''' if style_pills else ""}

        <!-- Sub-attributes -->
        <div style="font-size:8px;color:rgba(255,255,255,0.25);font-weight:700;letter-spacing:2px;margin-bottom:6px;">SUB-ATTRIBUTES</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;">
            {pills}
        </div>
    </div>
    """

