"""
Stat chart builders — radar charts, shot maps, xG timelines, market value trends.
All return matplotlib Figure or Plotly Figure objects.
"""

from typing import Optional
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

try:
    from mplsoccer import Pitch, VerticalPitch, PyPizza, FontManager
    HAS_MPLSOCCER = True
except ImportError:
    HAS_MPLSOCCER = False

DARK_BG = "#0d1b2a"
GOLD = "#c9a84c"
WHITE = "#ffffff"
GRID_COLOR = "#1e3a5f"


# ---------------------------------------------------------------------------
# Radar / Pizza Chart
# ---------------------------------------------------------------------------

RADAR_STATS_LABELS = {
    "xg_per90": "xG/90",
    "xg_assist_per90": "xA/90",
    "progressive_carries": "Prog. Carries",
    "progressive_passes": "Prog. Passes",
    "pressures": "Pressures",
    "tackles_won": "Tackles Won",
    "interceptions": "Interceptions",
    "aerial_duels_won_pct": "Aerial %",
    "passes_completed_pct": "Pass %",
    "dribbles_completed_pct": "Dribble %",
    "shots_on_target_pct": "Shot on Tgt %",
    "npxg_per90": "npxG/90",
}


def build_radar_chart(
    player_percentiles: dict,
    player_name: str,
    position_group: str,
    compare_percentiles: Optional[dict] = None,
    compare_name: str = "",
) -> plt.Figure:
    """
    Render a pizza/radar chart of player percentile rankings.
    """
    # Pick relevant stats for position
    from models.squad_analyzer import POSITION_RADAR_STATS
    stat_keys = POSITION_RADAR_STATS.get(position_group, list(RADAR_STATS_LABELS.keys()))
    stat_keys = [s for s in stat_keys if s in player_percentiles][:10]

    if not stat_keys:
        fig, ax = plt.subplots()
        fig.patch.set_facecolor(DARK_BG)
        ax.text(0.5, 0.5, "No percentile data available", ha="center", va="center", color=WHITE)
        ax.axis("off")
        return fig

    values = [round(player_percentiles.get(k, 0), 1) for k in stat_keys]
    labels = [RADAR_STATS_LABELS.get(k, k.replace("_", " ").title()) for k in stat_keys]

    if HAS_MPLSOCCER:
        try:
            slice_colors = [GOLD if v >= 70 else ("#2980b9" if v >= 40 else "#c0392b") for v in values]
            text_colors = [WHITE] * len(values)

            baker = PyPizza(
                params=labels,
                background_color=DARK_BG,
                straight_line_color="#333",
                straight_line_lw=1,
                last_circle_lw=0,
                other_circle_lw=0,
                inner_circle_size=20,
            )

            fig, ax = baker.make_pizza(
                values,
                figsize=(7, 7),
                color_blank_space=["#1a1a2e"] * len(values),
                slice_colors=slice_colors,
                value_colors=text_colors,
                value_bboxes=dict(boxstyle="round,pad=0.2", facecolor="#111", alpha=0.7),
                blank_alpha=0.4,
                kwargs_slices=dict(edgecolor="#222", zorder=2, linewidth=1),
                kwargs_params=dict(color=WHITE, fontsize=8, fontweight="bold", va="center"),
                kwargs_values=dict(color=WHITE, fontsize=9, fontweight="bold", zorder=3),
            )

            fig.text(
                0.5, 0.97,
                player_name,
                ha="center", va="top",
                fontsize=14, fontweight="bold",
                color=GOLD, fontfamily="DejaVu Sans",
            )
            fig.text(
                0.5, 0.93,
                f"{position_group} · Percentile vs. Position Peers",
                ha="center", va="top",
                fontsize=9, color="#aaa",
            )
            return fig
        except Exception:
            pass

    # Fallback: plain radar
    return _plain_radar(labels, values, player_name, position_group)


def _plain_radar(labels: list, values: list, name: str, pos: str) -> plt.Figure:
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]
    vals = values + values[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    # Grid
    ax.set_rlabel_position(0)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], color="#666", size=7)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color=WHITE, size=8)
    ax.grid(color=GRID_COLOR, linewidth=0.5)

    # Fill
    ax.plot(angles, vals, color=GOLD, linewidth=2)
    ax.fill(angles, vals, alpha=0.25, color=GOLD)

    ax.set_ylim(0, 100)
    ax.set_title(f"{name}\n{pos} · Percentile Radar", color=GOLD, fontsize=12, pad=15)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Shot Map
# ---------------------------------------------------------------------------

def build_shot_map(shots: list[dict], player_name: str) -> plt.Figure:
    """Render a shot map on a half-pitch."""
    if not shots:
        fig, ax = plt.subplots()
        fig.patch.set_facecolor(DARK_BG)
        ax.text(0.5, 0.5, "No shot data available", ha="center", va="center", color=WHITE)
        ax.axis("off")
        return fig

    if HAS_MPLSOCCER:
        pitch = VerticalPitch(
            pitch_type="statsbomb",
            half=True,
            pitch_color=DARK_BG,
            line_color="#2a4060",
            linewidth=1.5,
        )
        fig, ax = pitch.draw(figsize=(7, 5))
        fig.patch.set_facecolor(DARK_BG)

        for shot in shots:
            x = shot.get("x", 50)
            y = shot.get("y", 50)
            xg = shot.get("xg", 0.05)
            result = shot.get("result", "")

            color = "#f5c518" if result in ("Goal", "goal") else "#c0392b"
            marker = "*" if result in ("Goal", "goal") else "o"
            size = 80 + xg * 500

            pitch.scatter(
                y, x,  # mplsoccer vertical pitch: (y, x) swapped
                ax=ax,
                s=size,
                c=color,
                edgecolors=WHITE,
                linewidths=0.8,
                alpha=0.75,
                marker=marker,
                zorder=4,
            )
    else:
        fig, ax = plt.subplots(figsize=(7, 5))
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARK_BG)
        ax.set_xlim(0, 100)
        ax.set_ylim(50, 100)
        ax.axis("off")
        # Simple penalty box
        ax.add_patch(mpatches.Rectangle((21, 78), 58, 22, fill=False, edgecolor="#2a4060", lw=1.5))
        ax.add_patch(mpatches.Rectangle((37, 89), 26, 11, fill=False, edgecolor="#2a4060", lw=1.5))

        for shot in shots:
            x = shot.get("y", 50)
            y = shot.get("x", 50)
            xg = shot.get("xg", 0.05)
            result = shot.get("result", "")
            color = "#f5c518" if result in ("Goal", "goal") else "#c0392b"
            marker = "*" if result in ("Goal", "goal") else "o"
            ax.scatter(x, y, s=80 + xg * 500, c=color, marker=marker, edgecolors=WHITE, linewidths=0.8, alpha=0.75, zorder=4)

    goals = sum(1 for s in shots if s.get("result", "").lower() == "goal")
    total_xg = sum(s.get("xg", 0) for s in shots)

    ax.set_title(
        f"{player_name} — Shot Map\n{len(shots)} shots · {goals} goals · {total_xg:.1f} xG",
        color=GOLD, fontsize=10, fontweight="bold",
    )

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor="#f5c518", label="Goal"),
        mpatches.Patch(facecolor="#c0392b", label="No Goal"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", facecolor=DARK_BG, labelcolor=WHITE, fontsize=8)

    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# xG / xA Timeline
# ---------------------------------------------------------------------------

def build_xg_timeline(timeline: list[dict], player_name: str) -> go.Figure:
    """Rolling xG/xA per match as Plotly bar + cumulative line."""
    if not timeline:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
            title=dict(text="No xG timeline data", font=dict(color=WHITE)),
        )
        return fig

    df = pd.DataFrame(timeline)
    df = df.sort_values("date").reset_index(drop=True)

    # Cumulative
    df["cum_xg"] = df["xg"].cumsum()
    df["cum_goals"] = df["goals"].cumsum()
    df["match_label"] = df.apply(
        lambda r: f"{r['home_team']} vs {r['away_team']}<br>{r['date'][:10]}", axis=1
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # xG bars
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["xg"],
            name="xG",
            marker_color=GOLD,
            opacity=0.8,
            hovertext=df["match_label"],
            hovertemplate="%{hovertext}<br>xG: %{y:.2f}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Goals scatter
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["goals"],
            name="Goals",
            mode="markers",
            marker=dict(size=10, color="#e74c3c", symbol="star"),
            hovertemplate="Goals: %{y}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Cumulative xG line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["cum_xg"],
            name="Cumulative xG",
            line=dict(color="#3498db", width=2, dash="dot"),
            hovertemplate="Cum xG: %{y:.1f}<extra></extra>",
        ),
        secondary_y=True,
    )

    # Cumulative goals line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["cum_goals"],
            name="Cumulative Goals",
            line=dict(color="#27ae60", width=2),
            hovertemplate="Cum Goals: %{y}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(text=f"{player_name} — xG Timeline", font=dict(color=GOLD, size=14)),
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=WHITE),
        legend=dict(bgcolor="#1a1a2e", font=dict(color=WHITE)),
        xaxis=dict(title="Match #", gridcolor=GRID_COLOR, showgrid=True),
        yaxis=dict(title="xG / Goals", gridcolor=GRID_COLOR),
        yaxis2=dict(title="Cumulative", gridcolor=GRID_COLOR, showgrid=False),
        height=380,
        bargap=0.3,
    )
    return fig


# ---------------------------------------------------------------------------
# Market Value History
# ---------------------------------------------------------------------------

def build_market_value_chart(history: list[dict], player_name: str) -> go.Figure:
    """Plotly line chart of market value history from Transfermarkt."""
    if not history:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=DARK_BG,
            title=dict(text="No market value history", font=dict(color=WHITE)),
        )
        return fig

    df = pd.DataFrame(history)
    df = df.sort_values("date").reset_index(drop=True)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["value_m"],
            mode="lines+markers",
            name="Market Value (€m)",
            line=dict(color=GOLD, width=2.5),
            marker=dict(size=6, color=GOLD),
            fill="tozeroy",
            fillcolor="rgba(201,168,76,0.12)",
            hovertemplate="Date: %{x}<br>Value: €%{y}m<extra></extra>",
        )
    )

    peak = df["value_m"].max()
    peak_date = df.loc[df["value_m"].idxmax(), "date"]
    fig.add_annotation(
        x=peak_date, y=peak,
        text=f"Peak: €{peak}m",
        showarrow=True,
        arrowhead=2,
        arrowcolor=GOLD,
        font=dict(color=GOLD, size=10),
        bgcolor=DARK_BG,
    )

    fig.update_layout(
        title=dict(text=f"{player_name} — Market Value History", font=dict(color=GOLD, size=14)),
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=WHITE),
        xaxis=dict(title="Date", gridcolor=GRID_COLOR),
        yaxis=dict(title="Market Value (€m)", gridcolor=GRID_COLOR),
        height=340,
    )
    return fig


# ---------------------------------------------------------------------------
# Price Prediction Gauge
# ---------------------------------------------------------------------------

def build_price_gauge(prediction: dict, player_name: str) -> go.Figure:
    """Show predicted fee range as a visual range bar."""
    lower = prediction.get("lower_m", 0)
    median = prediction.get("median_m", 0)
    upper = prediction.get("upper_m", 0)
    mv = prediction.get("market_value_m", median)

    fig = go.Figure()

    # Range bar
    fig.add_trace(go.Bar(
        x=["Fee Range"],
        y=[upper - lower],
        base=[lower],
        marker_color="rgba(201,168,76,0.3)",
        marker_line_color=GOLD,
        marker_line_width=2,
        name="Predicted Range",
        width=0.3,
    ))

    # Median marker
    fig.add_trace(go.Scatter(
        x=["Fee Range"],
        y=[median],
        mode="markers+text",
        marker=dict(size=16, color=GOLD, symbol="diamond"),
        text=[f"€{median}m"],
        textposition="middle right",
        name="Predicted Fee",
        textfont=dict(color=GOLD, size=12),
    ))

    # MV marker
    if mv:
        fig.add_trace(go.Scatter(
            x=["Fee Range"],
            y=[mv],
            mode="markers+text",
            marker=dict(size=12, color="#3498db", symbol="circle"),
            text=[f"MV: €{mv}m"],
            textposition="middle left",
            name="Market Value",
            textfont=dict(color="#3498db", size=10),
        ))

    fig.update_layout(
        title=dict(text=f"{player_name} — Predicted Transfer Fee", font=dict(color=GOLD, size=13)),
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=WHITE),
        yaxis=dict(title="€ Millions", gridcolor=GRID_COLOR),
        xaxis=dict(showticklabels=False),
        height=320,
        showlegend=True,
        legend=dict(bgcolor="#1a1a2e", font=dict(color=WHITE)),
    )
    return fig


# ---------------------------------------------------------------------------
# Squad Weakness Heatmap
# ---------------------------------------------------------------------------

def build_weakness_chart(weaknesses: list[dict]) -> go.Figure:
    """Bar chart showing squad weakness scores per position group."""
    if not weaknesses:
        return go.Figure()

    labels = [w["position_group"] for w in weaknesses]
    scores = [w["weakness_score"] for w in weaknesses]
    colors = [
        "#c0392b" if w["priority"] == "HIGH" else
        ("#e67e22" if w["priority"] == "MEDIUM" else "#27ae60")
        for w in weaknesses
    ]

    fig = go.Figure(go.Bar(
        x=labels,
        y=scores,
        marker_color=colors,
        text=[f"{s:.0f}%" for s in scores],
        textposition="outside",
        hovertemplate="%{x}<br>Weakness Score: %{y:.1f}<extra></extra>",
    ))

    fig.add_hline(y=50, line_dash="dot", line_color="#555", annotation_text="Threshold")

    fig.update_layout(
        title=dict(text="Squad Weakness Analysis", font=dict(color=GOLD, size=14)),
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=WHITE),
        xaxis=dict(title="Position Group", gridcolor=GRID_COLOR),
        yaxis=dict(title="Weakness Score", gridcolor=GRID_COLOR, range=[0, 110]),
        height=360,
    )
    return fig
