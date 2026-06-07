"""
Shared pytest fixtures for Football Intelligence Hub tests.
"""
import sys
from pathlib import Path

import pytest

# Ensure project root is on path before any imports
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Player factories ──────────────────────────────────────────────────────────

def _make_player(
    name="Test Player", pos="CM", age=25,
    pac=75, sho=70, pas=78, dri=76, def_=55, phy=72,
    overall=82, mv=30.0, contract="Jun 30, 2027",
    play_styles=None, position_group=None,
    fee_paid_m=None,
):
    pg = position_group or pos
    return {
        "name": name,
        "position_code": pos,
        "position_group": pg,
        "age": age,
        "pac": pac, "sho": sho, "pas": pas,
        "dri": dri, "def_": def_, "phy": phy,
        "overall": overall,
        "market_value_m": mv,
        "contract_expiry": contract,
        "play_styles": play_styles or [],
        "club_name": "Test FC",
        "nationality": "Test",
        "fee_paid_m": fee_paid_m,
    }


@pytest.fixture
def sample_player():
    return _make_player()


@pytest.fixture
def sample_squad():
    """15-player mock squad covering all position groups."""
    return [
        _make_player("GK1",  "GK",  28, overall=84, mv=15.0, position_group="GK"),
        _make_player("GK2",  "GK",  22, overall=72, mv=5.0,  position_group="GK"),
        _make_player("CB1",  "CB",  27, overall=85, mv=45.0, position_group="CB",
                     play_styles=["Aerial+", "Power Header"]),
        _make_player("CB2",  "CB",  25, overall=83, mv=35.0, position_group="CB",
                     play_styles=["Aerial+", "Bruiser"]),
        _make_player("CB3",  "CB",  30, overall=79, mv=12.0, position_group="CB",
                     fee_paid_m=30.0),
        _make_player("LB1",  "LB",  24, overall=81, mv=28.0, position_group="FB",
                     play_styles=["Rapid", "Whipped Pass"]),
        _make_player("RB1",  "RB",  26, overall=80, mv=25.0, position_group="FB"),
        _make_player("DM1",  "DM",  26, overall=86, mv=50.0, position_group="DM",
                     play_styles=["Intercept", "Slide Tackle"]),
        _make_player("CM1",  "CM",  24, overall=84, mv=60.0, position_group="CM",
                     play_styles=["Incisive Pass", "Technical"]),
        _make_player("CM2",  "CM",  22, overall=78, mv=20.0, position_group="CM",
                     play_styles=["Technical"]),
        _make_player("AM1",  "CAM", 23, overall=87, mv=80.0, position_group="AM",
                     play_styles=["Flair", "Trickster"]),
        _make_player("LW1",  "LW",  21, overall=85, mv=70.0, position_group="Winger",
                     play_styles=["Rapid", "Flair"]),
        _make_player("RW1",  "RW",  25, overall=82, mv=40.0, position_group="Winger",
                     play_styles=["Rapid"]),
        _make_player("ST1",  "ST",  26, overall=88, mv=90.0, position_group="ST",
                     play_styles=["First Touch", "Rapid"]),
        _make_player("ST2",  "ST",  29, overall=80, mv=20.0, position_group="ST",
                     fee_paid_m=50.0),
    ]


@pytest.fixture
def possession_squad():
    """Squad strongly weighted toward possession play styles."""
    styles = ["Incisive Pass", "Technical", "Whipped Pass", "Pinged Pass", "Tiki Taka"]
    return [
        _make_player(f"P{i}", "CM", 25, position_group="CM", play_styles=styles)
        for i in range(11)
    ]


@pytest.fixture
def counter_attack_squad():
    """Squad strongly weighted toward counter-attack play styles."""
    styles = ["Rapid", "First Touch", "Long Ball Pass"]
    return [
        _make_player(f"C{i}", "ST", 24, position_group="ST", play_styles=styles)
        for i in range(11)
    ]
