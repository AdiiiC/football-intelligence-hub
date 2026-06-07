"""
Tests for ui/export/pdf_report.py
"""
import pytest

pytest.importorskip("reportlab", reason="reportlab not installed — skipping PDF tests")

from ui.export.pdf_report import generate_scout_report_pdf


def _player(**kw):
    base = {
        "name": "Bukayo Saka",
        "position_code": "LW",
        "age": 22,
        "club_name": "Arsenal",
        "nationality": "English",
        "overall": 88,
        "market_value_m": 130.0,
        "preferred_foot": "Left",
        "pac": 91, "sho": 82, "pas": 83, "dri": 88, "def_": 66, "phy": 70,
        "play_styles": ["Rapid", "Technical"],
        "play_styles_plus": ["Trickster"],
    }
    base.update(kw)
    return base


class TestGenerateScoutReportPdf:
    def test_returns_bytes(self):
        pdf = generate_scout_report_pdf(_player())
        assert isinstance(pdf, bytes)

    def test_pdf_starts_with_pdf_magic_bytes(self):
        pdf = generate_scout_report_pdf(_player())
        assert pdf[:4] == b"%PDF"

    def test_pdf_non_empty(self):
        pdf = generate_scout_report_pdf(_player())
        assert len(pdf) > 1000  # any valid PDF will be > 1 KB

    def test_with_fit_result(self):
        fit = {
            "overall_fit_score": 78,
            "thrives": ["Goalscoring (xG/90)", "Ball progression"],
            "must_adapt": ["Pressing intensity"],
        }
        pdf = generate_scout_report_pdf(_player(), fit_result=fit)
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"

    def test_with_fbref_stats(self):
        stats = {
            "goals_per90": 0.45,
            "assists_per90": 0.30,
            "xg_per90": 0.40,
            "xg_assist_per90": 0.28,
            "progressive_carries": 8.2,
            "progressive_passes": 5.1,
            "tackles_won": 1.2,
            "interceptions": 0.8,
            "passes_completed_pct": 84.5,
            "dribbles_completed_pct": 62.3,
        }
        pdf = generate_scout_report_pdf(_player(), fbref_stats=stats)
        assert isinstance(pdf, bytes)

    def test_with_all_data(self):
        fit = {"overall_fit_score": 85, "thrives": ["Pace"], "must_adapt": []}
        stats = {"goals_per90": 0.5, "xg_per90": 0.45}
        pdf = generate_scout_report_pdf(_player(), fit_result=fit, fbref_stats=stats)
        assert pdf[:4] == b"%PDF"

    def test_minimal_player_dict(self):
        """PDF should be generated even with minimal player data."""
        pdf = generate_scout_report_pdf({"name": "Unknown Player"})
        assert isinstance(pdf, bytes)

    def test_empty_player_dict(self):
        """Should not crash on empty dict."""
        pdf = generate_scout_report_pdf({})
        assert isinstance(pdf, bytes)

    def test_player_with_no_ea_attributes(self):
        """Player missing EA attrs should still produce a valid PDF."""
        player = {"name": "No Attrs", "age": 25, "position_code": "CM"}
        pdf = generate_scout_report_pdf(player)
        assert isinstance(pdf, bytes)

    def test_player_with_play_styles(self):
        player = _player(play_styles=["Rapid", "Press Proven"], play_styles_plus=["Intercept"])
        pdf = generate_scout_report_pdf(player)
        assert isinstance(pdf, bytes)

    def test_fit_result_with_empty_thrives(self):
        fit = {"overall_fit_score": 50, "thrives": [], "must_adapt": ["Passing accuracy"]}
        pdf = generate_scout_report_pdf(_player(), fit_result=fit)
        assert isinstance(pdf, bytes)

    def test_multiple_calls_return_consistent_type(self):
        for _ in range(3):
            pdf = generate_scout_report_pdf(_player())
            assert isinstance(pdf, bytes)
