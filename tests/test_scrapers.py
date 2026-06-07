"""
Snapshot-based scraper tests.
Run: python3 -m pytest tests/ -v
"""

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestTransfermarktScraper:
    def test_get_clubs_returns_list(self):
        from data.fetchers.squad import get_clubs_for_league
        clubs = get_clubs_for_league("Premier League")
        assert isinstance(clubs, list)
        assert len(clubs) > 10
        assert "name" in clubs[0]
        assert "tm_slug" in clubs[0]

    def test_squad_has_required_fields(self):
        from data.fetchers.squad import get_enriched_squad
        squad = get_enriched_squad("arsenal-fc", "11", "Premier League")
        assert len(squad) > 10
        for player in squad[:5]:
            assert "name" in player
            assert "age" in player
            assert "position_code" in player

    def test_squad_no_none_names(self):
        from data.fetchers.squad import get_enriched_squad
        squad = get_enriched_squad("arsenal-fc", "11", "Premier League")
        names = [p.get("name") for p in squad]
        assert all(n is not None and n != "" for n in names)


class TestUnderstatScraper:
    def test_search_returns_player(self):
        from data.scrapers.understat import search_player_understat
        p = search_player_understat("Bukayo Saka", "EPL", "2025")
        assert p is not None
        assert "id" in p
        assert "player_name" in p

    def test_shots_returns_list(self):
        from data.scrapers.understat import search_player_understat, get_player_shots
        p = search_player_understat("Bukayo Saka", "EPL", "2025")
        shots = get_player_shots(p["id"], "2025")
        assert isinstance(shots, list)
        if shots:
            assert "x" in shots[0]
            assert "xg" in shots[0]
            assert "result" in shots[0]

    def test_timeline_returns_list(self):
        from data.scrapers.understat import search_player_understat, get_player_xg_timeline
        p = search_player_understat("Bukayo Saka", "EPL", "2025")
        tl = get_player_xg_timeline(p["id"], "2025")
        assert isinstance(tl, list)
        if tl:
            assert "xg" in tl[0]
            assert "goals" in tl[0]
            assert "date" in tl[0]

    def test_league_stats_returns_players(self):
        from data.scrapers.understat import get_league_player_stats
        players = get_league_player_stats("EPL", "2025")
        assert len(players) > 100


class TestSquadAnalyzer:
    def _mock_player(self, name="Test Player", pos="CM", age=25, pac=75, sho=70, pas=80, dri=78, def_=60, phy=72):
        return {
            "name": name, "position_code": pos, "position_group": pos,
            "age": age, "pac": pac, "sho": sho, "pas": pas,
            "dri": dri, "def_": def_, "phy": phy,
            "market_value_m": 30.0, "overall": 80,
            "play_styles": [], "contract_expiry": 2026,
        }

    def test_determine_playstyle_returns_dict(self):
        from models.squad_analyzer import determine_team_playstyle
        squad = [self._mock_player() for _ in range(10)]
        result = determine_team_playstyle(squad)
        assert "dominant" in result
        assert "scores" in result
        assert "description" in result

    def test_fit_analysis_has_required_keys(self):
        from models.squad_analyzer import fit_analysis
        player = self._mock_player()
        squad = [self._mock_player(f"Player {i}") for i in range(15)]
        result = fit_analysis(player, squad, "Test FC")
        assert "thrives" in result
        assert "must_adapt" in result
        assert "overall_fit_score" in result
        assert 0 <= result["overall_fit_score"] <= 100


class TestCacheDb:
    def test_set_get_roundtrip(self):
        from data.cache_db import cache_set, cache_get, cache_delete
        cache_set("_test_key", {"hello": "world"}, ttl=60)
        val = cache_get("_test_key")
        assert val == {"hello": "world"}
        cache_delete("_test_key")
        assert cache_get("_test_key") is None

    def test_expired_returns_none(self):
        import time
        from data.cache_db import cache_set, cache_get
        cache_set("_test_expire", "value", ttl=1)
        time.sleep(2)
        assert cache_get("_test_expire") is None


class TestDataValidation:
    def test_validate_player_catches_missing_name(self):
        from models.validator import validate_player
        result = validate_player({"age": 25})
        assert not result["valid"]
        assert any("name" in e for e in result["errors"])

    def test_validate_player_passes_complete(self):
        from models.validator import validate_player
        player = {"name": "Test", "age": 25, "position_code": "CM", "market_value_m": 10.0}
        result = validate_player(player)
        assert result["valid"]
