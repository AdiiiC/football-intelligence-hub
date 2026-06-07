"""
Tests for pages/06_Formation.py formation logic (extracted for testability).
"""
"""
Tests for formation assignment logic.
The pure logic is re-implemented here so we don't import streamlit in tests.
The algorithms are identical to pages/06_Formation.py.
"""
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_POSITION_TO_GROUP = {
    "GK": "GK", "CB": "CB", "LCB": "CB", "RCB": "CB",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "DM": "DM", "CDM": "DM",
    "CM": "CM", "MF": "CM", "LCM": "CM", "RCM": "CM",
    "CAM": "AM", "AM": "AM",
    "LW": "Winger", "RW": "Winger", "LM": "Winger", "RM": "Winger",
    "ST": "ST", "CF": "ST", "FW": "ST",
}

_SLOT_AFFINITY = {
    "GK":     {"GK": 10},
    "CB":     {"CB": 10, "DM": 2},
    "FB":     {"RB": 8, "LB": 8, "RWB": 7, "LWB": 7, "RM": 3, "LM": 3},
    "DM":     {"DM": 10, "CM": 6, "CB": 2},
    "CM":     {"CM": 10, "DM": 7, "AM": 5},
    "AM":     {"AM": 10, "CM": 6, "RW": 4, "LW": 4},
    "Winger": {"RW": 9, "LW": 9, "RM": 7, "LM": 7, "AM": 3},
    "ST":     {"ST": 10, "CF": 10, "RW": 3, "LW": 3},
}

FORMATIONS = {
    "4-3-3": [
        ("GK", 5, 50),
        ("RB", 25, 80), ("CB", 25, 60), ("CB", 25, 40), ("LB", 25, 20),
        ("CM", 50, 70), ("CM", 50, 50), ("CM", 50, 30),
        ("RW", 78, 80), ("ST", 82, 50), ("LW", 78, 20),
    ],
    "4-2-3-1": [
        ("GK", 5, 50),
        ("RB", 25, 80), ("CB", 25, 60), ("CB", 25, 40), ("LB", 25, 20),
        ("DM", 42, 65), ("DM", 42, 35),
        ("RW", 62, 80), ("AM", 65, 50), ("LW", 62, 20),
        ("ST", 82, 50),
    ],
}


def _assign_players_to_formation(squad, slots):
    available = [p for p in squad if p.get("name")]
    assigned = {}
    slot_order = list(range(len(slots)))
    slot_order.sort(key=lambda i: (0 if slots[i][0] == "GK" else 1))
    used = set()
    for i in slot_order:
        slot_pos = slots[i][0]
        best_score = -1
        best_player = None
        for p in available:
            if id(p) in used:
                continue
            pg = _POSITION_TO_GROUP.get(p.get("position_code", ""), "CM")
            affinity = _SLOT_AFFINITY.get(pg, {})
            score = affinity.get(slot_pos, 0)
            ovr = (p.get("overall") or 0) / 200
            total = score + ovr
            if total > best_score:
                best_score = total
                best_player = p
        if best_player:
            assigned[i] = best_player
            used.add(id(best_player))
    return assigned


def _make_player(name, pos, overall=80):
    return {"name": name, "position_code": pos, "overall": overall}


class TestPositionToGroupMapping:
    def test_gk_maps_to_gk(self):
        assert _POSITION_TO_GROUP["GK"] == "GK"

    def test_lb_maps_to_fb(self):
        assert _POSITION_TO_GROUP["LB"] == "FB"

    def test_rb_maps_to_fb(self):
        assert _POSITION_TO_GROUP["RB"] == "FB"

    def test_cam_maps_to_am(self):
        assert _POSITION_TO_GROUP["CAM"] == "AM"

    def test_cf_maps_to_st(self):
        assert _POSITION_TO_GROUP["CF"] == "ST"

    def test_lw_maps_to_winger(self):
        assert _POSITION_TO_GROUP["LW"] == "Winger"

    def test_cdm_maps_to_dm(self):
        assert _POSITION_TO_GROUP["CDM"] == "DM"


class TestSlotAffinity:
    def test_gk_has_highest_affinity_for_gk_slot(self):
        assert _SLOT_AFFINITY["GK"]["GK"] == 10

    def test_st_has_highest_affinity_for_st_slot(self):
        assert _SLOT_AFFINITY["ST"]["ST"] == 10

    def test_winger_has_high_affinity_for_rw_lw(self):
        assert _SLOT_AFFINITY["Winger"]["RW"] >= 8
        assert _SLOT_AFFINITY["Winger"]["LW"] >= 8

    def test_cm_has_decent_affinity_for_dm(self):
        assert _SLOT_AFFINITY["CM"].get("DM", 0) > 0


class TestAssignPlayersToFormation:
    def test_gk_assigned_to_gk_slot(self):
        squad = [
            _make_player("GK1", "GK", 84),
            _make_player("CM1", "CM", 82),
            _make_player("ST1", "ST", 85),
        ] + [_make_player(f"X{i}", "CM", 75) for i in range(8)]

        slots = FORMATIONS["4-3-3"]
        assigned = _assign_players_to_formation(squad, slots)
        # Slot 0 is GK
        assert assigned.get(0, {}).get("position_code") == "GK"

    def test_all_11_slots_filled_with_11_players(self):
        squad = (
            [_make_player("GK1", "GK")]
            + [_make_player(f"CB{i}", "CB") for i in range(2)]
            + [_make_player("LB1", "LB"), _make_player("RB1", "RB")]
            + [_make_player(f"CM{i}", "CM") for i in range(3)]
            + [_make_player("LW1", "LW"), _make_player("RW1", "RW")]
            + [_make_player("ST1", "ST")]
        )
        slots = FORMATIONS["4-3-3"]
        assigned = _assign_players_to_formation(squad, slots)
        assert len(assigned) == 11

    def test_no_player_assigned_twice(self):
        squad = [_make_player(f"P{i}", "CM", 80) for i in range(11)]
        slots = FORMATIONS["4-3-3"]
        assigned = _assign_players_to_formation(squad, slots)
        assigned_ids = [id(p) for p in assigned.values()]
        assert len(assigned_ids) == len(set(assigned_ids))

    def test_empty_squad_returns_empty_dict(self):
        slots = FORMATIONS["4-3-3"]
        assigned = _assign_players_to_formation([], slots)
        assert assigned == {}

    def test_squad_smaller_than_slots_only_fills_available(self):
        squad = [_make_player(f"P{i}", "CM", 80) for i in range(5)]
        slots = FORMATIONS["4-3-3"]
        assigned = _assign_players_to_formation(squad, slots)
        assert len(assigned) <= 5

    def test_striker_preferred_for_st_slot(self):
        """When a natural ST and CMs compete for the ST slot, ST wins via affinity."""
        # Make all CMs have lower overall than ST so ST also wins overall ties
        squad = (
            [_make_player("GK1", "GK", 90)]
            + [_make_player(f"CB{i}", "CB", 80) for i in range(4)]
            + [_make_player(f"FB{i}", "LB", 80) for i in range(2)]
            + [_make_player(f"CM{i}", "CM", 80) for i in range(3)]
            + [_make_player("RW1", "RW", 80)]
            + [_make_player("ST1", "ST", 80)]
        )
        slots = FORMATIONS["4-3-3"]
        assigned = _assign_players_to_formation(squad, slots)
        # With natural position players for every slot, ST1 should get the ST slot
        st_slot_player = assigned.get(9)  # index 9 = ST slot
        assert st_slot_player is not None
        assert st_slot_player["position_code"] == "ST"

    def test_higher_overall_breaks_affinity_ties(self):
        """When two players have same position, higher overall should win."""
        squad = [
            _make_player(f"CM{i}", "CM", 70 + i) for i in range(11)
        ]
        slots = [("CM", 50, 50)]
        assigned = _assign_players_to_formation(squad, slots)
        # The highest overall CM should be assigned
        assert assigned[0]["overall"] == 80  # 70+10 (index 10)


class TestFormationDefinitions:
    def test_4_3_3_has_11_slots(self):
        assert len(FORMATIONS["4-3-3"]) == 11

    def test_4_2_3_1_has_11_slots(self):
        assert len(FORMATIONS["4-2-3-1"]) == 11

    def test_each_slot_has_position_and_coords(self):
        for formation, slots in FORMATIONS.items():
            for slot in slots:
                assert len(slot) == 3, f"{formation}: slot {slot} missing coords"
                pos, x, y = slot
                assert isinstance(pos, str)
                assert 0 <= x <= 100
                assert 0 <= y <= 100

    def test_each_formation_has_exactly_one_gk(self):
        for formation, slots in FORMATIONS.items():
            gk_count = sum(1 for s in slots if s[0] == "GK")
            assert gk_count == 1, f"{formation} should have exactly 1 GK"
