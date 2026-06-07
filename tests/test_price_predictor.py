"""
Tests for models/price_predictor.py
"""
import pytest
import numpy as np
from unittest.mock import patch

from models.price_predictor import (
    build_feature_vector,
    predict_transfer_fee,
    _extract_contract_years,
    FEATURE_COLS,
    LEAGUE_DIFFICULTY,
    POSITION_SCARCITY,
)


class TestExtractContractYears:
    def test_extracts_year_correctly(self):
        years = _extract_contract_years("Jun 30, 2028", current_year=2026)
        assert years == 2.0

    def test_expired_contract_returns_zero(self):
        years = _extract_contract_years("Jun 30, 2024", current_year=2026)
        assert years == 0.0

    def test_empty_string_returns_default(self):
        years = _extract_contract_years("", current_year=2026)
        assert years == 1.0

    def test_none_returns_default(self):
        years = _extract_contract_years(None, current_year=2026)
        assert years == 1.0

    def test_far_future_contract(self):
        years = _extract_contract_years("Jun 30, 2031", current_year=2026)
        assert years == 5.0

    def test_malformed_string_returns_default(self):
        years = _extract_contract_years("No contract info", current_year=2026)
        assert years == 1.0

    def test_year_in_middle_of_string(self):
        years = _extract_contract_years("Contract until 2030 confirmed", current_year=2026)
        assert years == 4.0


class TestBuildFeatureVector:
    def _player(self, **kw):
        base = {
            "age": 25, "market_value_m": 50.0,
            "contract_expiry": "Jun 30, 2028",
            "position_group": "ST",
        }
        base.update(kw)
        return base

    def test_returns_numpy_array(self):
        vec = build_feature_vector(self._player(), "Premier League")
        assert isinstance(vec, np.ndarray)

    def test_correct_length(self):
        vec = build_feature_vector(self._player(), "Premier League")
        assert len(vec) == len(FEATURE_COLS)

    def test_market_value_in_vector(self):
        vec = build_feature_vector(self._player(market_value_m=100.0), "Premier League")
        assert vec[FEATURE_COLS.index("market_value_m")] == 100.0

    def test_age_in_vector(self):
        vec = build_feature_vector(self._player(age=22), "Premier League")
        assert vec[FEATURE_COLS.index("age")] == 22.0

    def test_league_difficulty_mapped_correctly(self):
        vec_epl = build_feature_vector(self._player(), "Premier League")
        vec_l1  = build_feature_vector(self._player(), "Ligue 1")
        epl_idx = FEATURE_COLS.index("league_difficulty")
        assert vec_epl[epl_idx] == LEAGUE_DIFFICULTY["Premier League"]
        assert vec_l1[epl_idx]  == LEAGUE_DIFFICULTY["Ligue 1"]
        assert vec_epl[epl_idx] > vec_l1[epl_idx]

    def test_unknown_league_uses_fallback(self):
        vec = build_feature_vector(self._player(), "Unknown League")
        idx = FEATURE_COLS.index("league_difficulty")
        assert 0 < vec[idx] <= 1.0

    def test_performance_percentile_passed_through(self):
        vec = build_feature_vector(self._player(), "Premier League", performance_percentile=80.0)
        idx = FEATURE_COLS.index("performance_percentile")
        assert vec[idx] == 80.0

    def test_rumour_clubs_count_in_vector(self):
        vec = build_feature_vector(self._player(), "Premier League", rumour_clubs=5)
        idx = FEATURE_COLS.index("rumour_clubs_count")
        assert vec[idx] == 5.0

    def test_all_values_finite(self):
        vec = build_feature_vector(self._player(), "Premier League")
        assert np.all(np.isfinite(vec))

    def test_no_negative_values(self):
        """All features should be non-negative."""
        vec = build_feature_vector(self._player(), "Premier League")
        assert np.all(vec >= 0)


class TestPredictTransferFee:
    def _player(self, mv=50.0, age=25, pos="ST"):
        return {
            "name": "Test Player",
            "age": age,
            "market_value_m": mv,
            "contract_expiry": "Jun 30, 2028",
            "position_group": pos,
            "overall": 82,
        }

    def test_returns_dict_with_required_keys(self):
        result = predict_transfer_fee(self._player(), "Premier League")
        assert "lower_m" in result
        assert "median_m" in result
        assert "upper_m" in result

    def test_low_le_mid_le_high(self):
        result = predict_transfer_fee(self._player(), "Premier League")
        assert result["lower_m"] <= result["median_m"] <= result["upper_m"]

    def test_high_value_player_gets_higher_fee(self):
        low_val  = predict_transfer_fee(self._player(mv=10.0), "Premier League")
        high_val = predict_transfer_fee(self._player(mv=100.0), "Premier League")
        assert high_val["median_m"] > low_val["median_m"]

    def test_young_player_gets_premium(self):
        young = predict_transfer_fee(self._player(age=20, mv=50.0), "Premier League")
        old   = predict_transfer_fee(self._player(age=32, mv=50.0), "Premier League")
        assert young["median_m"] >= old["median_m"]

    def test_premier_league_fee_above_ligue_1(self):
        epl = predict_transfer_fee(self._player(), "Premier League")
        l1  = predict_transfer_fee(self._player(), "Ligue 1")
        assert epl["median_m"] >= l1["median_m"]

    def test_all_fees_positive(self):
        result = predict_transfer_fee(self._player(), "Premier League")
        assert result["lower_m"] >= 0
        assert result["median_m"] >= 0
        assert result["upper_m"] >= 0

    def test_gk_scarcity_lower_than_st(self):
        """ST has higher position scarcity than GK → should tend toward higher fees."""
        assert POSITION_SCARCITY["ST"] > POSITION_SCARCITY["GK"]

    def test_missing_market_value_does_not_crash(self):
        player = {"name": "X", "age": 25, "position_group": "CM"}
        result = predict_transfer_fee(player, "Premier League")
        assert "median_m" in result
