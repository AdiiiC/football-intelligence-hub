"""
Tests for config/settings.py
"""
import pytest
from config import settings


class TestRequiredConstants:
    def test_top5_leagues_defined(self):
        assert hasattr(settings, "TOP_5_LEAGUES")
        assert isinstance(settings.TOP_5_LEAGUES, dict)

    def test_top5_leagues_has_5_entries(self):
        assert len(settings.TOP_5_LEAGUES) == 5

    def test_top5_leagues_expected_names(self):
        expected = {"Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"}
        assert set(settings.TOP_5_LEAGUES.keys()) == expected

    def test_each_league_has_required_keys(self):
        for league, data in settings.TOP_5_LEAGUES.items():
            assert "tm_id" in data or "flag" in data, f"{league} missing expected keys"

    def test_position_groups_defined(self):
        assert hasattr(settings, "POSITION_GROUPS")
        assert isinstance(settings.POSITION_GROUPS, dict)

    def test_position_groups_covers_all_roles(self):
        expected = {"GK", "CB", "FB", "DM", "CM", "AM", "Winger", "ST"}
        assert set(settings.POSITION_GROUPS.keys()) == expected

    def test_fbref_stat_cols_defined(self):
        assert hasattr(settings, "FBREF_STAT_COLS")
        assert isinstance(settings.FBREF_STAT_COLS, list)
        assert len(settings.FBREF_STAT_COLS) > 0

    def test_fbref_stat_cols_expected_fields(self):
        cols = settings.FBREF_STAT_COLS
        assert "goals_per90" in cols
        assert "assists_per90" in cols
        assert "xg_per90" in cols

    def test_strength_threshold_defined(self):
        assert hasattr(settings, "STRENGTH_THRESHOLD")
        assert 50 <= settings.STRENGTH_THRESHOLD <= 100

    def test_weakness_threshold_defined(self):
        assert hasattr(settings, "WEAKNESS_THRESHOLD")
        assert 0 <= settings.WEAKNESS_THRESHOLD <= 50

    def test_strength_above_weakness(self):
        assert settings.STRENGTH_THRESHOLD > settings.WEAKNESS_THRESHOLD

    def test_cache_dir_defined(self):
        assert hasattr(settings, "CACHE_DIR")
        assert isinstance(settings.CACHE_DIR, str)

    def test_model_dir_defined(self):
        assert hasattr(settings, "MODEL_DIR")
        assert isinstance(settings.MODEL_DIR, str)


class TestSeasonSettings:
    def test_current_season_fbref(self):
        assert hasattr(settings, "CURRENT_SEASON_FBREF")
        assert "-" in settings.CURRENT_SEASON_FBREF  # e.g. "2024-2025"

    def test_current_season_understat(self):
        assert hasattr(settings, "CURRENT_SEASON_UNDERSTAT")
        assert settings.CURRENT_SEASON_UNDERSTAT.isdigit()

    def test_current_season_tm(self):
        assert hasattr(settings, "CURRENT_SEASON_TM")
        assert settings.CURRENT_SEASON_TM.isdigit()


class TestTTLSettings:
    def test_ttl_squad_defined(self):
        assert hasattr(settings, "CACHE_TTL_SQUAD")
        assert isinstance(settings.CACHE_TTL_SQUAD, int)
        assert settings.CACHE_TTL_SQUAD > 0

    def test_ttl_player_stats_defined(self):
        assert hasattr(settings, "CACHE_TTL_STATS")
        assert isinstance(settings.CACHE_TTL_STATS, int)
        assert settings.CACHE_TTL_STATS > 0

    def test_ttl_market_value_defined(self):
        assert hasattr(settings, "CACHE_TTL_MARKET")
        assert isinstance(settings.CACHE_TTL_MARKET, int)
        assert settings.CACHE_TTL_MARKET > 0

    def test_ttl_transfer_news_defined(self):
        assert hasattr(settings, "CACHE_TTL_TRANSFERS")
        assert isinstance(settings.CACHE_TTL_TRANSFERS, int)
        assert settings.CACHE_TTL_TRANSFERS > 0


class TestScraperSettings:
    def test_scraper_headers_defined(self):
        assert hasattr(settings, "SCRAPER_HEADERS")
        assert isinstance(settings.SCRAPER_HEADERS, dict)
        assert "User-Agent" in settings.SCRAPER_HEADERS

    def test_user_agent_non_empty(self):
        assert len(settings.SCRAPER_HEADERS["User-Agent"]) > 10


class TestLeagueMappings:
    def test_understat_to_league_defined(self):
        assert hasattr(settings, "UNDERSTAT_TO_LEAGUE")
        assert isinstance(settings.UNDERSTAT_TO_LEAGUE, dict)

    def test_fbref_id_to_league_defined(self):
        assert hasattr(settings, "FBREF_ID_TO_LEAGUE")
        assert isinstance(settings.FBREF_ID_TO_LEAGUE, dict)

    def test_understat_epl_mapping(self):
        # "EPL" should map to "Premier League"
        epl = settings.UNDERSTAT_TO_LEAGUE.get("EPL", "")
        assert "Premier League" in epl or "Premier" in epl
