"""
Formation visualizer using mplsoccer pitch.
"""

import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

try:
    from mplsoccer import Pitch, VerticalPitch
    HAS_MPLSOCCER = True
except ImportError:
    HAS_MPLSOCCER = False


FORMATION_POSITIONS = {
    "4-3-3": [
        ("GK", 10, 50),
        ("RB", 22, 85), ("CB", 22, 62), ("CB", 22, 38), ("LB", 22, 15),
        ("CM", 50, 75), ("CM", 50, 50), ("CM", 50, 25),
        ("RW", 78, 80), ("ST", 82, 50), ("LW", 78, 20),
    ],
    "4-2-3-1": [
        ("GK", 10, 50),
        ("RB", 22, 85), ("CB", 22, 62), ("CB", 22, 38), ("LB", 22, 15),
        ("DM", 38, 65), ("DM", 38, 35),
        ("RM", 58, 80), ("AM", 60, 50), ("LM", 58, 20),
        ("ST", 82, 50),
    ],
    "4-4-2": [
        ("GK", 10, 50),
        ("RB", 22, 85), ("CB", 22, 62), ("CB", 22, 38), ("LB", 22, 15),
        ("RM", 52, 85), ("CM", 52, 62), ("CM", 52, 38), ("LM", 52, 15),
        ("ST", 80, 62), ("ST", 80, 38),
    ],
    "3-5-2": [
        ("GK", 10, 50),
        ("CB", 25, 72), ("CB", 25, 50), ("CB", 25, 28),
        ("RWB", 48, 90), ("CM", 48, 68), ("DM", 48, 50), ("CM", 48, 32), ("LWB", 48, 10),
        ("ST", 80, 62), ("ST", 80, 38),
    ],
    "3-4-3": [
        ("GK", 10, 50),
        ("CB", 25, 72), ("CB", 25, 50), ("CB", 25, 28),
        ("RWB", 50, 85), ("CM", 52, 62), ("CM", 52, 38), ("LWB", 50, 15),
        ("RW", 78, 80), ("ST", 82, 50), ("LW", 78, 20),
    ],
    "4-1-4-1": [
        ("GK", 10, 50),
        ("RB", 22, 85), ("CB", 22, 62), ("CB", 22, 38), ("LB", 22, 15),
        ("DM", 38, 50),
        ("RM", 58, 85), ("CM", 60, 65), ("CM", 60, 35), ("LM", 58, 15),
        ("ST", 82, 50),
    ],
    "5-3-2": [
        ("GK", 10, 50),
        ("RWB", 28, 90), ("CB", 25, 72), ("CB", 25, 50), ("CB", 25, 28), ("LWB", 28, 10),
        ("CM", 52, 72), ("CM", 52, 50), ("CM", 52, 28),
        ("ST", 80, 62), ("ST", 80, 38),
    ],
}

POSITION_COLORS_PITCH = {
    "GK": "#f5c518",
    "CB": "#27ae60", "RB": "#2ecc71", "LB": "#2ecc71",
    "RWB": "#16a085", "LWB": "#16a085",
    "DM": "#2980b9", "CM": "#3498db", "AM": "#8e44ad",
    "RM": "#1abc9c", "LM": "#1abc9c",
    "RW": "#e67e22", "LW": "#e67e22",
    "ST": "#c0392b", "CF": "#e74c3c",
}


# Fallback groups when primary position group is exhausted
_POSITION_FALLBACK = {
    "CM": ["DM", "AM", "Winger"],
    "DM": ["CM", "AM"],
    "AM": ["CM", "Winger"],
    "Winger": ["AM", "CM", "ST"],
    "ST": ["Winger", "AM"],
    "CB": ["FB", "DM"],
    "FB": ["CB"],
    "GK": [],
}

# Name particles that should be included with the surname
_PARTICLES = {"de", "van", "der", "den", "von", "la", "le", "del", "di", "da", "dos", "bin", "al", "el", "lo"}


def _display_name(name: str, fallback: str = "") -> str:
    """Return surname for pitch display, preserving particles (e.g. 'De Jong')."""
    parts = name.split() if name else []
    if not parts:
        return fallback
    if len(parts) >= 3 and parts[-2].lower() in _PARTICLES:
        return parts[-2].capitalize() + " " + parts[-1].capitalize()
    return parts[-1].capitalize()


def _assign_players_to_positions(formation_slots: list, squad: list) -> list:
    """
    Greedy assignment of squad players to formation slots by position group.
    Uses fallback groups when primary group is exhausted.
    Returns list of (pos_label, x, y, player_dict or None).
    """
    from config.settings import POSITION_GROUPS

    assigned = []
    used_ids = set()

    # Group players by position group
    group_players = {}
    for p in squad:
        pg = p.get("position_group", "Other")
        group_players.setdefault(pg, []).append(p)

    # Sort each group by market value desc
    for pg in group_players:
        group_players[pg].sort(key=lambda x: x.get("market_value_m", 0), reverse=True)

    for pos_label, x, y in formation_slots:
        # Find matching position group
        target_group = None
        for group, codes in POSITION_GROUPS.items():
            if pos_label in codes or group == pos_label:
                target_group = group
                break
        if target_group is None:
            target_group = pos_label

        # Build search order: primary group then fallbacks
        search_order = [target_group] + _POSITION_FALLBACK.get(target_group, [])

        chosen = None
        for group_key in search_order:
            candidates = group_players.get(group_key, [])
            for p in candidates:
                if p.get("id", p.get("name")) not in used_ids:
                    chosen = p
                    used_ids.add(p.get("id", p.get("name")))
                    break
            if chosen:
                break

        assigned.append((pos_label, x, y, chosen))

    return assigned


def render_formation(
    squad: list[dict],
    formation: str = "4-3-3",
    club_name: str = "",
    highlight_players: list[str] = None,
) -> plt.Figure:
    """
    Render a football pitch with the squad in the chosen formation.
    Returns matplotlib Figure.
    """
    slots = FORMATION_POSITIONS.get(formation, FORMATION_POSITIONS["4-3-3"])
    assignments = _assign_players_to_positions(slots, squad)
    highlight_players = highlight_players or []

    if HAS_MPLSOCCER:
        pitch = VerticalPitch(
            pitch_type="statsbomb",
            pitch_color="#0d1b2a",
            line_color="#2a4060",
            linewidth=1.5,
            goal_type="box",
        )
        fig, ax = pitch.draw(figsize=(8, 11))
        fig.patch.set_facecolor("#0d1b2a")

        for pos_label, x_pct, y_pct in slots:
            # Convert percentage (0-100) to statsbomb coordinates
            # Vertical pitch: x=0-80 (length), y=0-120 (width)
            px = y_pct / 100 * 80    # across pitch
            py = x_pct / 100 * 120   # up pitch

            assigned_player = None
            for _pos, _x, _y, player in assignments:
                if _x == x_pct and _y == y_pct:
                    assigned_player = player
                    break

            circle_color = POSITION_COLORS_PITCH.get(pos_label, "#3498db")
            name_str = ""
            if assigned_player:
                name = assigned_player.get("name", "")
                name_str = _display_name(name, fallback=pos_label)
                mv = assigned_player.get("market_value_m", 0)
                is_highlight = name in highlight_players

                # Draw circle
                ax.scatter(
                    px, py,
                    s=700,
                    c=circle_color,
                    edgecolors="#fff" if not is_highlight else "#f5c518",
                    linewidths=2.5 if not is_highlight else 4,
                    zorder=5,
                )
                # Player name
                ax.text(
                    px, py - 6.5,
                    name_str,
                    ha="center", va="top",
                    fontsize=7,
                    color="#ffffff",
                    fontweight="bold",
                    zorder=6,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#0d1b2a", alpha=0.7, edgecolor="none"),
                )
                # Market value
                ax.text(
                    px, py,
                    f"€{mv}m" if mv >= 1 else "",
                    ha="center", va="center",
                    fontsize=5.5,
                    color="#fff",
                    zorder=7,
                    fontweight="bold",
                )
            else:
                ax.scatter(px, py, s=700, c="#333", edgecolors="#555", linewidths=1.5, zorder=5)
                ax.text(px, py, pos_label, ha="center", va="center", fontsize=6, color="#aaa", zorder=6)

        # Formation label
        ax.text(
            40, 125, f"{club_name}  ·  {formation}",
            ha="center", va="center",
            fontsize=12, fontweight="bold",
            color="#c9a84c",
        )

    else:
        # Fallback: simple scatter on a rectangle
        fig, ax = plt.subplots(figsize=(8, 11))
        fig.patch.set_facecolor("#0d1b2a")
        ax.set_facecolor("#0d1b2a")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 110)
        ax.axis("off")

        # Draw basic pitch lines
        for rect_args in [
            dict(xy=(5, 5), width=90, height=100, fill=False, edgecolor="#2a4060", lw=2),
            dict(xy=(30, 5), width=40, height=15, fill=False, edgecolor="#2a4060", lw=1.5),
            dict(xy=(30, 90), width=40, height=15, fill=False, edgecolor="#2a4060", lw=1.5),
        ]:
            ax.add_patch(mpatches.Rectangle(**rect_args))
        ax.add_patch(mpatches.Circle((50, 55), 12, fill=False, edgecolor="#2a4060", lw=1.5))
        ax.plot([5, 95], [55, 55], color="#2a4060", lw=1)

        for pos_label, x_pct, y_pct in slots:
            circle_color = POSITION_COLORS_PITCH.get(pos_label, "#3498db")
            assigned_player = None
            for _pos, _x, _y, player in assignments:
                if _x == x_pct and _y == y_pct:
                    assigned_player = player
                    break

            ax.scatter(y_pct, x_pct, s=600, c=circle_color, edgecolors="#fff", linewidths=2, zorder=5)
            name_str = pos_label
            if assigned_player:
                name = assigned_player.get("name", "")
                name_str = _display_name(name, fallback=pos_label)
            ax.text(y_pct, x_pct - 5, name_str, ha="center", fontsize=6.5, color="#fff", fontweight="bold", zorder=6)

        ax.set_title(f"{club_name}  ·  {formation}", color="#c9a84c", fontsize=13, fontweight="bold", pad=10)

    plt.tight_layout()
    return fig


def get_available_formations() -> list[str]:
    return list(FORMATION_POSITIONS.keys())
