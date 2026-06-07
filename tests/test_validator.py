"""
Tests for models/validator.py
"""
import pytest
from models.validator import validate_player, validate_squad


class TestValidatePlayerRequiredFields:
    def test_valid_complete_player_passes(self):
        p = {"name": "Bukayo Saka", "age": 22, "position_code": "LW"}
        result = validate_player(p)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_name_fails(self):
        result = validate_player({"age": 22, "position_code": "ST"})
        assert result["valid"] is False
        assert any("name" in e for e in result["errors"])

    def test_missing_age_fails(self):
        result = validate_player({"name": "Test", "position_code": "CM"})
        assert result["valid"] is False
        assert any("age" in e for e in result["errors"])

    def test_missing_position_code_fails(self):
        result = validate_player({"name": "Test", "age": 25})
        assert result["valid"] is False
        assert any("position_code" in e for e in result["errors"])

    def test_all_three_missing_gives_three_errors(self):
        result = validate_player({})
        assert result["valid"] is False
        assert len(result["errors"]) == 3

    def test_empty_name_fails(self):
        result = validate_player({"name": "", "age": 25, "position_code": "ST"})
        assert result["valid"] is False


class TestValidatePlayerNumericCoercion:
    def test_string_age_coerced_to_float(self):
        result = validate_player({"name": "X", "age": "25", "position_code": "CM"})
        assert result["valid"] is True
        assert result["player"]["age"] == 25.0

    def test_none_market_value_defaults_to_zero(self):
        result = validate_player({"name": "X", "age": 25, "position_code": "CM",
                                   "market_value_m": None})
        assert result["player"]["market_value_m"] == 0
        assert any("market_value_m" in w for w in result["warnings"])

    def test_non_numeric_overall_defaults_to_zero_with_warning(self):
        result = validate_player({"name": "X", "age": 25, "position_code": "CM",
                                   "overall": "n/a"})
        assert result["player"]["overall"] == 0
        assert any("overall" in w for w in result["warnings"])

    def test_all_ea_attributes_coerced(self):
        p = {"name": "X", "age": 25, "position_code": "CM",
             "pac": "80", "sho": "75", "pas": "82", "dri": "78", "def_": "60", "phy": "72"}
        result = validate_player(p)
        assert result["player"]["pac"] == 80.0
        assert result["player"]["phy"] == 72.0

    def test_float_string_market_value_coerced(self):
        result = validate_player({"name": "X", "age": 25, "position_code": "ST",
                                   "market_value_m": "45.5"})
        assert result["player"]["market_value_m"] == 45.5


class TestValidatePlayerPositionWarnings:
    def test_valid_position_codes_no_warning(self):
        for pos in ["GK", "CB", "LB", "RB", "CM", "DM", "AM", "LW", "RW", "ST", "CF"]:
            result = validate_player({"name": "X", "age": 25, "position_code": pos})
            pos_warnings = [w for w in result["warnings"] if "position" in w.lower()]
            assert pos_warnings == [], f"Unexpected warning for valid position {pos}"

    def test_invalid_position_code_generates_warning(self):
        result = validate_player({"name": "X", "age": 25, "position_code": "XX"})
        assert any("position_code" in w for w in result["warnings"])

    def test_lowercase_position_still_warns(self):
        # The validator uppercases before checking, so "cm" should warn (not in set)
        result = validate_player({"name": "X", "age": 25, "position_code": "cm"})
        # "cm".upper() == "CM" which IS in the set — should NOT warn
        pos_warnings = [w for w in result["warnings"] if "Unknown position_code" in w]
        assert pos_warnings == []


class TestValidatePlayerAgeSanity:
    def test_normal_age_no_warning(self):
        result = validate_player({"name": "X", "age": 25, "position_code": "CM"})
        age_warnings = [w for w in result["warnings"] if "age" in w.lower()]
        assert age_warnings == []

    def test_too_young_generates_warning(self):
        result = validate_player({"name": "X", "age": 10, "position_code": "CM"})
        assert any("age" in w.lower() for w in result["warnings"])

    def test_too_old_generates_warning(self):
        result = validate_player({"name": "X", "age": 50, "position_code": "GK"})
        assert any("age" in w.lower() for w in result["warnings"])

    def test_boundary_ages_pass(self):
        for age in [15, 45]:
            result = validate_player({"name": "X", "age": age, "position_code": "CM"})
            age_warnings = [w for w in result["warnings"] if "Suspicious age" in w]
            assert age_warnings == [], f"Age {age} should not trigger warning"


class TestValidatePlayerReturnStructure:
    def test_result_has_required_keys(self):
        result = validate_player({"name": "X", "age": 25, "position_code": "CM"})
        assert "valid" in result
        assert "errors" in result
        assert "warnings" in result
        assert "player" in result

    def test_original_dict_not_mutated(self):
        original = {"name": "X", "age": 25, "position_code": "CM", "market_value_m": None}
        validate_player(original)
        assert original["market_value_m"] is None  # untouched

    def test_player_in_result_is_copy(self):
        p = {"name": "X", "age": 25, "position_code": "CM"}
        result = validate_player(p)
        result["player"]["name"] = "Modified"
        assert p["name"] == "X"


class TestValidateSquad:
    def test_valid_squad_returned_intact(self, sample_squad):
        cleaned = validate_squad(sample_squad)
        assert len(cleaned) == len(sample_squad)

    def test_invalid_players_dropped(self):
        squad = [
            {"name": "Good", "age": 25, "position_code": "CM"},
            {"age": 25, "position_code": "CM"},  # missing name — invalid
            {"name": "Also Good", "age": 30, "position_code": "ST"},
        ]
        cleaned = validate_squad(squad)
        assert len(cleaned) == 2
        assert all(p["name"] != "" for p in cleaned)

    def test_empty_squad_returns_empty(self):
        assert validate_squad([]) == []

    def test_all_invalid_returns_empty(self):
        squad = [{"pac": 80}, {"sho": 70}]
        cleaned = validate_squad(squad)
        assert cleaned == []
