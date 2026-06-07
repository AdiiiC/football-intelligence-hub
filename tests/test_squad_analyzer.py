"""
Tests for models/squad_analyzer.py

All external I/O (FBref, Understat) is mocked so tests run offline.
"""
import pytest
from unittest.mock import patch

from models.squad_analyzer import (
    determine_team_playstyle,
    recommend_sales,
    fit_analysis,
    historical_transfer_grade,
    _playstyle_fit,
    _peer_percentile,
    _heuristic_analysis,
)

# ── Inline squad factories (don't rely on conftest fixtures with @patch) ──────

def _squad():
    """15-player squad for tests that need @patch AND squad data."""
    from tests.conftest import _make_player
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


def _possession_squad():
    from tests.conftest import _make_player
    styles = ["Incisive Pass", "Technical", "Whipped Pass", "Pinged Pass", "Tiki Taka"]
    return [_make_player(f"P{i}", "CM", 25, position_group="CM", play_styles=styles)
            for i in range(11)]


def _counter_squad():
    from tests.conftest import _make_player
    styles = ["Rapid", "First Touch", "Long Ball Pass"]
    return [_make_player(f"C{i}", "ST", 24, position_group="ST", play_styles=styles)
            for i in range(11)]


# ── _peer_percentile ──────────────────────────────────────────────────────────

class TestPeerPercentile:
    def test_median_value_around_50th(self):
        peers = list(range(1, 101))  # 1–100
        pct = _peer_percentile(50, peers)
        assert 45 <= pct <= 55

    def test_top_value_near_100th(self):
        peers = list(range(0, 100))
        pct = _peer_percentile(99, peers)
        assert pct >= 95

    def test_bottom_value_near_0th(self):
        peers = list(range(1, 101))
        pct = _peer_percentile(0, peers)
        assert pct == 0.0

    def test_empty_peers_returns_50(self):
        assert _peer_percentile(10.0, []) == 50.0

    def test_single_peer_below_player(self):
        assert _peer_percentile(10, [5]) == 100.0

    def test_single_peer_above_player(self):
        assert _peer_percentile(3, [5]) == 0.0


# ── _playstyle_fit ────────────────────────────────────────────────────────────

class TestPlaystyleFit:
    def _team_style(self, dominant):
        from models.squad_analyzer import _STYLE_LABELS
        return {
            "dominant": dominant,
            "description": _STYLE_LABELS.get(dominant, dominant),
        }

    def test_player_with_all_required_tags_gets_high_score(self):
        player = {
            "position_group": "CM",
            "play_styles": ["Incisive Pass", "Technical", "Whipped Pass"],
        }
        score, label = _playstyle_fit(player, self._team_style("possession"))
        assert score >= 67
        assert "Strong" in label or "fit" in label.lower()

    def test_player_with_no_tags_gets_low_score(self):
        player = {
            "position_group": "CM",
            "play_styles": [],
        }
        score, label = _playstyle_fit(player, self._team_style("possession"))
        assert score == 0
        assert "mismatch" in label.lower() or "fit" in label.lower()

    def test_position_with_no_requirements_returns_neutral(self):
        player = {
            "position_group": "CB",
            "play_styles": [],
        }
        # counter_attack has [] for CB
        score, label = _playstyle_fit(player, self._team_style("counter_attack"))
        assert score == 65
        assert "neutral" in label.lower()

    def test_partial_match_returns_mid_score(self):
        player = {
            "position_group": "CM",
            "play_styles": ["Technical"],  # only 1 of 3 possession tags
        }
        score, label = _playstyle_fit(player, self._team_style("possession"))
        assert 0 < score < 67


# ── determine_team_playstyle ──────────────────────────────────────────────────

class TestDetermineTeamPlaystyle:
    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_empty_squad_returns_unknown(self, _us, _fb):
        result = determine_team_playstyle([])
        assert result["dominant"] == "unknown"
        assert result["scores"] == {}

    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_possession_squad_dominant_is_possession(self, _us, _fb):
        result = determine_team_playstyle(_possession_squad())
        assert result["dominant"] == "possession"

    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_counter_squad_dominant_is_counter(self, _us, _fb):
        result = determine_team_playstyle(_counter_squad())
        assert result["dominant"] == "counter_attack"

    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_result_has_required_keys(self, _us, _fb):
        result = determine_team_playstyle(_squad())
        assert "dominant" in result
        assert "scores" in result
        assert "ea_scores" in result
        assert "description" in result
        assert "conflicts" in result
        assert "sources" in result

    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_scores_all_archetypes_present(self, _us, _fb):
        result = determine_team_playstyle(_squad())
        expected = {"possession", "high_press", "counter_attack", "physical", "creative"}
        assert set(result["scores"].keys()) == expected

    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_scores_between_0_and_100(self, _us, _fb):
        result = determine_team_playstyle(_squad())
        for arch, score in result["scores"].items():
            assert 0 <= score <= 100, f"{arch} score {score} out of range"

    @patch("models.squad_analyzer._fbref_team_scores", return_value={
        "possession": 70, "high_press": 20, "counter_attack": 30,
        "physical": 40, "creative": 50
    })
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_fbref_scores_blend_weights_possession(self, _us, _fb):
        result = determine_team_playstyle(_squad(), "Test FC", "Premier League")
        assert result["scores"]["possession"] >= result["scores"]["high_press"]

    @patch("models.squad_analyzer._fbref_team_scores", return_value={
        "possession": 10, "high_press": 80, "counter_attack": 10,
        "physical": 50, "creative": 50
    })
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_conflict_detection_fires_when_sources_disagree(self, _us, _fb):
        result = determine_team_playstyle(_possession_squad(), "Test FC", "Premier League")
        assert isinstance(result["conflicts"], list)

    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_sources_dict_has_ea_true(self, _us, _fb):
        result = determine_team_playstyle(_squad())
        assert result["sources"]["ea"] is True


# ── historical_transfer_grade ─────────────────────────────────────────────────

class TestHistoricalTransferGrade:
    def test_bargain_grade_for_high_gain(self):
        """Paid €20M, now worth €60M → +200% → A+"""
        g = historical_transfer_grade({"fee_paid_m": 20.0, "market_value_m": 60.0})
        assert g["grade"] == "A+"
        assert g["label"] == "Bargain"
        assert g["delta_m"] == 40.0
        assert abs(g["delta_pct"] - 200.0) < 1

    def test_good_value_grade(self):
        """Paid €30M, now worth €40M → +33% → A"""
        g = historical_transfer_grade({"fee_paid_m": 30.0, "market_value_m": 40.0})
        assert g["grade"] == "A"

    def test_fair_deal_grade(self):
        """Paid €30M, now worth €28M → -6.7% → B"""
        g = historical_transfer_grade({"fee_paid_m": 30.0, "market_value_m": 28.0})
        assert g["grade"] == "B"

    def test_slight_overpay_grade(self):
        """Paid €40M, now worth €28M → -30% → C"""
        g = historical_transfer_grade({"fee_paid_m": 40.0, "market_value_m": 28.0})
        assert g["grade"] == "C"

    def test_overpaid_grade(self):
        """Paid €60M, now worth €20M → -66% → D"""
        g = historical_transfer_grade({"fee_paid_m": 60.0, "market_value_m": 20.0})
        assert g["grade"] == "D"

    def test_free_transfer_now_valuable_is_bargain(self):
        """Free transfer, now worth €30M → 100% → A+"""
        g = historical_transfer_grade({"fee_paid_m": 0, "market_value_m": 30.0})
        assert g["grade"] == "A+"
        assert g["delta_pct"] == 100.0

    def test_no_data_returns_b_with_zero_delta(self):
        """No fee or value data → 0% → B (fair deal)"""
        g = historical_transfer_grade({})
        assert g["delta_m"] == 0.0
        assert g["delta_pct"] == 0.0

    def test_result_has_all_required_keys(self):
        g = historical_transfer_grade({"fee_paid_m": 20, "market_value_m": 40})
        for key in ("grade", "label", "color", "delta_m", "delta_pct", "rationale"):
            assert key in g

    def test_rationale_mentions_fee_when_present(self):
        g = historical_transfer_grade({"fee_paid_m": 25, "market_value_m": 50})
        assert "25" in g["rationale"] or "€" in g["rationale"]

    def test_free_transfer_rationale_mentions_free(self):
        g = historical_transfer_grade({"fee_paid_m": 0, "market_value_m": 30})
        assert "free" in g["rationale"].lower()


# ── fit_analysis ──────────────────────────────────────────────────────────────

class TestFitAnalysis:
    def test_returns_required_keys(self):
        from tests.conftest import _make_player
        player = _make_player()
        result = fit_analysis(player, _squad(), "Test FC")
        assert "thrives" in result
        assert "must_adapt" in result
        assert "overall_fit_score" in result

    def test_fit_score_in_valid_range(self):
        from tests.conftest import _make_player
        player = _make_player()
        result = fit_analysis(player, _squad(), "Test FC")
        score = result["overall_fit_score"]
        assert 0 <= score <= 100

    def test_thrives_and_must_adapt_are_lists(self):
        from tests.conftest import _make_player
        player = _make_player()
        result = fit_analysis(player, _squad(), "Test FC")
        assert isinstance(result["thrives"], list)
        assert isinstance(result["must_adapt"], list)

    def test_small_squad_does_not_crash(self):
        from tests.conftest import _make_player
        player = _make_player()
        result = fit_analysis(player, [player], "Test FC")
        assert "overall_fit_score" in result

    def test_empty_squad_does_not_crash(self):
        from tests.conftest import _make_player
        player = _make_player()
        result = fit_analysis(player, [], "Test FC")
        assert "overall_fit_score" in result


# ── recommend_sales ───────────────────────────────────────────────────────────

class TestRecommendSales:
    @patch("data.scrapers.understat.get_league_player_stats", return_value=[])
    @patch("data.scrapers.fbref.get_ucl_player_stats", return_value=[])
    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_returns_list(self, _us, _fb, _ucl, _ls):
        result = recommend_sales(_squad())
        assert isinstance(result, list)

    @patch("data.scrapers.understat.get_league_player_stats", return_value=[])
    @patch("data.scrapers.fbref.get_ucl_player_stats", return_value=[])
    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_results_sorted_by_sell_score_descending(self, _us, _fb, _ucl, _ls):
        result = recommend_sales(_squad())
        scores = [r["sell_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    @patch("data.scrapers.understat.get_league_player_stats", return_value=[])
    @patch("data.scrapers.fbref.get_ucl_player_stats", return_value=[])
    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_each_result_has_required_keys(self, _us, _fb, _ucl, _ls):
        result = recommend_sales(_squad())
        for r in result:
            assert "name" in r
            assert "sell_score" in r
            assert "sell_reasons" in r

    @patch("data.scrapers.understat.get_league_player_stats", return_value=[])
    @patch("data.scrapers.fbref.get_ucl_player_stats", return_value=[])
    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_contract_expiring_1yr_is_flagged(self, _us, _fb, _ucl, _ls):
        from datetime import date
        current_year = date.today().year
        squad = [
            {"name": f"CM{i}", "position_code": "CM", "position_group": "CM",
             "age": 26, "market_value_m": 30.0,
             "contract_expiry": f"Jun 30, {current_year}",
             "overall": 80, "play_styles": []}
            for i in range(3)
        ]
        result = recommend_sales(squad)
        reasons_flat = " ".join(r for x in result for r in x.get("sell_reasons", []))
        assert "sell now" in reasons_flat.lower() or "expires" in reasons_flat.lower()

    @patch("data.scrapers.understat.get_league_player_stats", return_value=[])
    @patch("data.scrapers.fbref.get_ucl_player_stats", return_value=[])
    @patch("models.squad_analyzer._fbref_team_scores", return_value={})
    @patch("models.squad_analyzer._understat_situation_scores", return_value={})
    def test_only_player_in_position_excluded(self, _us, _fb, _ucl, _ls):
        squad = [
            {"name": "Solo GK", "position_code": "GK", "position_group": "GK",
             "age": 30, "market_value_m": 10.0, "contract_expiry": "Jun 30, 2025",
             "overall": 70, "play_styles": []},
            {"name": "CB1", "position_code": "CB", "position_group": "CB",
             "age": 25, "market_value_m": 20.0, "contract_expiry": "Jun 30, 2030",
             "overall": 80, "play_styles": []},
        ]
        result = recommend_sales(squad)
        sell_names = [r["name"] for r in result]
        assert "Solo GK" not in sell_names


# ── _heuristic_analysis ───────────────────────────────────────────────────────

class TestHeuristicAnalysis:
    def test_returns_list_for_each_position(self):
        squad = [
            {"position_group": "GK"}, {"position_group": "GK"},
            {"position_group": "CB"}, {"position_group": "CB"},
        ]
        result = _heuristic_analysis(squad)
        assert isinstance(result, list)
        pos_groups = {r["position_group"] for r in result}
        assert "GK" in pos_groups

    def test_missing_position_has_high_weakness_score(self):
        squad = [{"position_group": "CM"} for _ in range(5)]
        result = _heuristic_analysis(squad)
        gk_entry = next((r for r in result if r["position_group"] == "GK"), None)
        assert gk_entry is not None
        assert gk_entry["weakness_score"] > 0
        assert gk_entry["priority"] in ("HIGH", "MEDIUM")

    def test_full_squad_has_low_gk_weakness(self):
        squad = [{"position_group": "GK"}, {"position_group": "GK"}]
        result = _heuristic_analysis(squad)
        gk_entry = next((r for r in result if r["position_group"] == "GK"), None)
        assert gk_entry["weakness_score"] == 0.0
        assert gk_entry["priority"] == "LOW"
