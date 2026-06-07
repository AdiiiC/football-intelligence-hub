"""
Tests for ui/components/transfer_feed.py — confidence scoring and badge rendering.
"""
import pytest
from ui.components.transfer_feed import (
    get_rumour_confidence,
    _confidence_badge,
    _type_badge,
    _direction_badge,
    _deal_type_badge,
    render_transfer_card,
)


class TestGetRumourConfidence:
    def test_confirmed_transfer_returns_100(self):
        item = {"type": "confirmed", "source": "any source"}
        conf = get_rumour_confidence(item)
        assert conf["score"] == 100
        assert conf["label"] == "Confirmed"
        assert conf["tier"] == 0

    def test_tier1_source_gives_high_confidence(self):
        item = {"type": "rumour", "source": "fabrizio romano"}
        conf = get_rumour_confidence(item)
        assert conf["label"] == "High"
        assert conf["tier"] == 1
        assert conf["score"] >= 50

    def test_sky_sports_is_tier1(self):
        item = {"type": "rumour", "source": "sky sports"}
        conf = get_rumour_confidence(item)
        assert conf["tier"] == 1

    def test_tier2_source_gives_medium_confidence(self):
        item = {"type": "rumour", "source": "goal.com"}
        conf = get_rumour_confidence(item)
        assert conf["label"] == "Medium"
        assert conf["tier"] == 2

    def test_tier3_tabloid_gives_low_confidence(self):
        item = {"type": "rumour", "source": "the sun"}
        conf = get_rumour_confidence(item)
        assert conf["label"] == "Low"
        assert conf["tier"] == 3

    def test_unknown_source_defaults_to_tier3(self):
        item = {"type": "rumour", "source": "random blog"}
        conf = get_rumour_confidence(item)
        assert conf["tier"] == 3

    def test_empty_source_defaults_to_tier3(self):
        item = {"type": "rumour", "source": ""}
        conf = get_rumour_confidence(item)
        assert conf["tier"] == 3

    def test_none_source_defaults_to_tier3(self):
        item = {"type": "rumour", "source": None}
        conf = get_rumour_confidence(item)
        assert conf["tier"] == 3

    def test_fee_info_increases_score(self):
        base  = get_rumour_confidence({"type": "rumour", "source": "goal.com"})
        withf = get_rumour_confidence({"type": "rumour", "source": "goal.com", "fee_m": 50.0})
        assert withf["score"] >= base["score"]

    def test_date_info_increases_score(self):
        base  = get_rumour_confidence({"type": "rumour", "source": "goal.com"})
        withd = get_rumour_confidence({"type": "rumour", "source": "goal.com", "date": "2025-01-15"})
        assert withd["score"] >= base["score"]

    def test_score_capped_at_100(self):
        item = {
            "type": "rumour",
            "source": "fabrizio romano",
            "fee_m": 80.0,
            "date": "2025-01-15",
        }
        conf = get_rumour_confidence(item)
        assert conf["score"] <= 100

    def test_score_never_negative(self):
        item = {"type": "rumour", "source": "random blog"}
        conf = get_rumour_confidence(item)
        assert conf["score"] >= 0

    def test_result_has_all_required_keys(self):
        conf = get_rumour_confidence({"type": "rumour", "source": "bbc sport"})
        for key in ("score", "label", "color", "bg", "tier"):
            assert key in conf

    def test_source_matching_is_case_insensitive(self):
        """Source tier lookup is on lowercased source string."""
        item = {"type": "rumour", "source": "Fabrizio Romano"}
        conf = get_rumour_confidence(item)
        assert conf["tier"] == 1

    def test_partial_source_string_matches(self):
        """'sky sports news' should still match 'sky sports'."""
        item = {"type": "rumour", "source": "sky sports news"}
        conf = get_rumour_confidence(item)
        assert conf["tier"] == 1


class TestConfidenceBadge:
    def test_confirmed_transfer_returns_empty_string(self):
        item = {"type": "confirmed", "source": "any"}
        assert _confidence_badge(item) == ""

    def test_rumour_returns_html_span(self):
        item = {"type": "rumour", "source": "fabrizio romano"}
        badge = _confidence_badge(item)
        assert "<span" in badge
        assert "confidence" in badge.lower()

    def test_low_confidence_badge_contains_low(self):
        item = {"type": "rumour", "source": "the sun"}
        badge = _confidence_badge(item)
        assert "Low" in badge


class TestTypeBadge:
    def test_confirmed_badge_contains_confirmed(self):
        badge = _type_badge("confirmed")
        assert "CONFIRMED" in badge.upper()

    def test_rumour_badge_contains_rumour(self):
        badge = _type_badge("rumour")
        assert "RUMOUR" in badge.upper()

    def test_badges_return_html_span(self):
        assert "<span" in _type_badge("confirmed")
        assert "<span" in _type_badge("rumour")


class TestDirectionBadge:
    def test_in_badge_contains_in(self):
        badge = _direction_badge("in")
        assert "IN" in badge

    def test_out_badge_contains_out(self):
        badge = _direction_badge("out")
        assert "OUT" in badge


class TestDealTypeBadge:
    def test_loan_badge_contains_loan(self):
        badge = _deal_type_badge("loan")
        assert "LOAN" in badge.upper()

    def test_permanent_badge_contains_permanent(self):
        badge = _deal_type_badge("permanent")
        assert "PERMANENT" in badge.upper()


class TestRenderTransferCard:
    def _item(self, **kw):
        base = {
            "name": "Bukayo Saka",
            "direction": "in",
            "club": "Arsenal",
            "fee_m": 50.0,
            "deal_type": "permanent",
            "window": "Summer 2025",
            "source": "sky sports",
            "type": "rumour",
            "position": "LW",
            "market_value_m": 120.0,
        }
        base.update(kw)
        return base

    def test_returns_html_string(self):
        html = render_transfer_card(self._item())
        assert isinstance(html, str)
        assert len(html) > 100

    def test_player_name_in_output(self):
        html = render_transfer_card(self._item(name="Kylian Mbappé"))
        assert "Kylian Mbappé" in html

    def test_club_name_in_output(self):
        html = render_transfer_card(self._item(club="Real Madrid"))
        assert "Real Madrid" in html

    def test_confirmed_transfer_shows_confirmed_badge(self):
        html = render_transfer_card(self._item(type="confirmed"))
        assert "CONFIRMED" in html.upper()

    def test_rumour_shows_rumour_badge(self):
        html = render_transfer_card(self._item(type="rumour"))
        assert "RUMOUR" in html.upper()

    def test_loan_deal_shows_loan(self):
        html = render_transfer_card(self._item(deal_type="loan", type="confirmed"))
        assert "LOAN" in html.upper()

    def test_fee_displayed(self):
        html = render_transfer_card(self._item(fee_m=75.0, type="confirmed"))
        assert "75" in html

    def test_missing_photo_url_does_not_crash(self):
        item = self._item()
        item.pop("photo_url", None)
        html = render_transfer_card(item)
        assert isinstance(html, str)

    def test_empty_item_does_not_crash(self):
        html = render_transfer_card({})
        assert isinstance(html, str)
