"""
Scout Report PDF export using reportlab.
Falls back gracefully if reportlab is not installed.
"""

from io import BytesIO
from datetime import datetime


def generate_scout_report_pdf(player: dict, fit_result: dict = None, fbref_stats: dict = None) -> bytes:
    """
    Generate a PDF scout report for a player.
    Returns raw PDF bytes or None if reportlab is unavailable.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        return None

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    # Colour palette
    NAVY  = colors.HexColor("#0d1b2a")
    GOLD  = colors.HexColor("#c9a84c")
    LIGHT = colors.HexColor("#e8f0f8")
    GREY  = colors.HexColor("#8899aa")
    WHITE = colors.white

    styles = getSampleStyleSheet()

    def _style(name, **kw):
        return ParagraphStyle(name, **kw)

    title_style = _style("Title", fontSize=22, textColor=GOLD, alignment=TA_CENTER,
                         fontName="Helvetica-Bold", spaceAfter=4)
    sub_style   = _style("Sub",   fontSize=11, textColor=LIGHT, alignment=TA_CENTER,
                         fontName="Helvetica", spaceAfter=2)
    label_style = _style("Label", fontSize=9,  textColor=GREY,  fontName="Helvetica")
    value_style = _style("Value", fontSize=11, textColor=LIGHT, fontName="Helvetica-Bold")
    section_style = _style("Section", fontSize=12, textColor=GOLD, fontName="Helvetica-Bold",
                           spaceBefore=12, spaceAfter=4)
    body_style  = _style("Body",  fontSize=9,  textColor=LIGHT, fontName="Helvetica",
                         leading=14)

    name = player.get("name", "Unknown")
    pos  = player.get("position_code", "—")
    age  = player.get("age", "—")
    club = player.get("club_name", player.get("club", "—"))
    nat  = player.get("nationality", "—")
    ovr  = player.get("overall", "—")
    val  = player.get("market_value_m", "—")
    foot = player.get("preferred_foot", "—")

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    story.append(Paragraph("⚽ FOOTBALL INTELLIGENCE HUB", title_style))
    story.append(Paragraph("SCOUT REPORT", sub_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y')}", label_style))
    story.append(HRFlowable(color=GOLD, thickness=1.5, spaceAfter=8))
    story.append(Spacer(1, 4))

    # ── Player header block ───────────────────────────────────────────────────
    story.append(Paragraph(name.upper(), _style("PName", fontSize=20, textColor=LIGHT,
                                                 fontName="Helvetica-Bold", alignment=TA_CENTER,
                                                 spaceAfter=2)))
    story.append(Paragraph(f"{pos} | {club} | {nat}", sub_style))
    story.append(Spacer(1, 6))

    # Basic info table
    info_data = [
        ["Age", str(age), "Overall", str(ovr)],
        ["Market Value", f"€{val}M", "Preferred Foot", str(foot)],
    ]
    info_table = Table(info_data, colWidths=[35*mm, 55*mm, 40*mm, 50*mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), NAVY),
        ("TEXTCOLOR",   (0, 0), (0, -1), GREY),
        ("TEXTCOLOR",   (2, 0), (2, -1), GREY),
        ("TEXTCOLOR",   (1, 0), (1, -1), LIGHT),
        ("TEXTCOLOR",   (3, 0), (3, -1), LIGHT),
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME",    (3, 0), (3, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [NAVY, colors.HexColor("#111e2e")]),
        ("INNERGRID",   (0, 0), (-1, -1), 0.5, colors.HexColor("#1e3045")),
        ("BOX",         (0, 0), (-1, -1), 0.5, colors.HexColor("#1e3045")),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))

    # ── EA Attributes ─────────────────────────────────────────────────────────
    ea_attrs = {
        "Pace": player.get("pac"), "Shooting": player.get("sho"),
        "Passing": player.get("pas"), "Dribbling": player.get("dri"),
        "Defending": player.get("def_"), "Physicality": player.get("phy"),
    }
    if any(v for v in ea_attrs.values()):
        story.append(Paragraph("EA FC ATTRIBUTES", section_style))
        attr_data = [["Attribute", "Rating", "Attribute", "Rating"]]
        items = list(ea_attrs.items())
        for i in range(0, len(items), 2):
            row = list(items[i]) + (list(items[i+1]) if i+1 < len(items) else ["", ""])
            attr_data.append([str(x) if x is not None else "—" for x in row])

        attr_table = Table(attr_data, colWidths=[50*mm, 30*mm, 50*mm, 30*mm])
        attr_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), GOLD),
            ("TEXTCOLOR",    (0, 0), (-1, 0), NAVY),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("TEXTCOLOR",    (0, 1), (-1, -1), LIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [NAVY, colors.HexColor("#111e2e")]),
            ("INNERGRID",    (0, 0), (-1, -1), 0.5, colors.HexColor("#1e3045")),
            ("BOX",          (0, 0), (-1, -1), 0.5, colors.HexColor("#1e3045")),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("FONTNAME",     (1, 1), (1, -1), "Helvetica-Bold"),
            ("FONTNAME",     (3, 1), (3, -1), "Helvetica-Bold"),
            ("TEXTCOLOR",    (1, 1), (1, -1), GOLD),
            ("TEXTCOLOR",    (3, 1), (3, -1), GOLD),
        ]))
        story.append(attr_table)
        story.append(Spacer(1, 8))

    # ── FBref stats ───────────────────────────────────────────────────────────
    if fbref_stats:
        story.append(Paragraph("STATISTICAL PROFILE (FBref)", section_style))
        stat_keys = [
            ("Goals/90", "goals_per90"), ("Assists/90", "assists_per90"),
            ("xG/90", "xg_per90"), ("xA/90", "xg_assist_per90"),
            ("Prog Carries", "progressive_carries"), ("Prog Passes", "progressive_passes"),
            ("Tackles Won", "tackles_won"), ("Interceptions", "interceptions"),
            ("Pass Cmp%", "passes_completed_pct"), ("Dribbles Cmp%", "dribbles_completed_pct"),
        ]
        stat_data = [["Stat", "Value", "Stat", "Value"]]
        for i in range(0, len(stat_keys), 2):
            lbl1, key1 = stat_keys[i]
            val1 = fbref_stats.get(key1, "—")
            if isinstance(val1, float):
                val1 = f"{val1:.2f}"
            row = [lbl1, str(val1)]
            if i+1 < len(stat_keys):
                lbl2, key2 = stat_keys[i+1]
                val2 = fbref_stats.get(key2, "—")
                if isinstance(val2, float):
                    val2 = f"{val2:.2f}"
                row += [lbl2, str(val2)]
            else:
                row += ["", ""]
            stat_data.append(row)

        stat_table = Table(stat_data, colWidths=[55*mm, 30*mm, 55*mm, 30*mm])
        stat_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), GOLD),
            ("TEXTCOLOR",    (0, 0), (-1, 0), NAVY),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("TEXTCOLOR",    (0, 1), (-1, -1), LIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [NAVY, colors.HexColor("#111e2e")]),
            ("INNERGRID",    (0, 0), (-1, -1), 0.5, colors.HexColor("#1e3045")),
            ("BOX",          (0, 0), (-1, -1), 0.5, colors.HexColor("#1e3045")),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("FONTNAME",     (1, 1), (1, -1), "Helvetica-Bold"),
            ("FONTNAME",     (3, 1), (3, -1), "Helvetica-Bold"),
            ("TEXTCOLOR",    (1, 1), (1, -1), GOLD),
            ("TEXTCOLOR",    (3, 1), (3, -1), GOLD),
        ]))
        story.append(stat_table)
        story.append(Spacer(1, 8))

    # ── Club Fit ─────────────────────────────────────────────────────────────
    if fit_result:
        story.append(Paragraph("CLUB FIT ANALYSIS", section_style))
        fit_score = fit_result.get("overall_fit_score", "—")
        story.append(Paragraph(f"Overall Fit Score: {fit_score}/100", value_style))
        story.append(Spacer(1, 4))

        thrives = fit_result.get("thrives", [])
        if thrives:
            story.append(Paragraph("✅ Player will THRIVE in:", label_style))
            for item in thrives:
                story.append(Paragraph(f"  • {item}", body_style))

        must_adapt = fit_result.get("must_adapt", [])
        if must_adapt:
            story.append(Spacer(1, 4))
            story.append(Paragraph("⚠️ Player MUST ADAPT in:", label_style))
            for item in must_adapt:
                story.append(Paragraph(f"  • {item}", body_style))

        story.append(Spacer(1, 8))

    # ── Play styles ───────────────────────────────────────────────────────────
    play_styles = player.get("play_styles", []) or []
    play_styles_plus = player.get("play_styles_plus", []) or []
    if play_styles or play_styles_plus:
        story.append(Paragraph("EA FC PLAY STYLES", section_style))
        ps_text = ", ".join(play_styles_plus) + ("  |  " if play_styles_plus and play_styles else "") + ", ".join(play_styles)
        story.append(Paragraph(ps_text, body_style))
        story.append(Spacer(1, 8))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(color=GOLD, thickness=0.5))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Football Intelligence Hub — Confidential Scout Report — For internal use only",
        _style("Footer", fontSize=7, textColor=GREY, alignment=TA_CENTER, fontName="Helvetica")
    ))

    doc.build(story)
    return buf.getvalue()
