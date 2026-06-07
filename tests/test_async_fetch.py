"""
Tests for data/async_fetch.py
"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from data.async_fetch import fetch_url_async, fetch_all_async, run_async


class TestFetchUrlAsync:
    def test_returns_text_on_200(self):
        """Should return response text for a successful GET."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "hello world"

        with patch("requests.get", return_value=mock_response):
            with patch("data.async_fetch.HAS_HTTPX", False):
                result = asyncio.get_event_loop().run_until_complete(
                    fetch_url_async("https://example.com")
                )
        assert result == "hello world"

    def test_returns_none_on_non_200(self):
        """Should return None when status code is not 200."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "not found"

        with patch("requests.get", return_value=mock_response):
            with patch("data.async_fetch.HAS_HTTPX", False):
                result = asyncio.get_event_loop().run_until_complete(
                    fetch_url_async("https://example.com/missing")
                )
        assert result is None

    def test_returns_none_on_network_error(self):
        """Should return None on connection error."""
        with patch("requests.get", side_effect=ConnectionError("timeout")):
            with patch("data.async_fetch.HAS_HTTPX", False):
                result = asyncio.get_event_loop().run_until_complete(
                    fetch_url_async("https://bad-host.invalid")
                )
        assert result is None

    def test_post_method_calls_requests_post(self):
        """POST method should call requests.post not requests.get."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "post ok"

        with patch("requests.post", return_value=mock_response) as mock_post:
            with patch("data.async_fetch.HAS_HTTPX", False):
                result = asyncio.get_event_loop().run_until_complete(
                    fetch_url_async("https://example.com", method="POST", data={"key": "value"})
                )
        mock_post.assert_called_once()
        assert result == "post ok"


class TestFetchAllAsync:
    def test_returns_list_of_same_length(self):
        """fetch_all_async should return results in same order as input."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("requests.get", return_value=mock_response):
            with patch("data.async_fetch.HAS_HTTPX", False):
                requests_list = [
                    {"url": "https://a.com"},
                    {"url": "https://b.com"},
                    {"url": "https://c.com"},
                ]
                results = asyncio.get_event_loop().run_until_complete(
                    fetch_all_async(requests_list)
                )
        assert len(results) == 3

    def test_empty_request_list_returns_empty(self):
        results = asyncio.get_event_loop().run_until_complete(fetch_all_async([]))
        assert results == []

    def test_mixed_success_failure(self):
        """Should return None for failed requests, text for successful ones."""
        def side_effect(url, **kwargs):
            resp = MagicMock()
            if "good" in url:
                resp.status_code = 200
                resp.text = "good"
            else:
                resp.status_code = 500
                resp.text = "error"
            return resp

        with patch("requests.get", side_effect=side_effect):
            with patch("data.async_fetch.HAS_HTTPX", False):
                requests_list = [
                    {"url": "https://good.com"},
                    {"url": "https://bad.com"},
                ]
                results = asyncio.get_event_loop().run_until_complete(
                    fetch_all_async(requests_list)
                )
        assert results[0] == "good"
        assert results[1] is None


class TestRunAsync:
    def test_run_async_executes_coroutine(self):
        """run_async should synchronously execute an async function."""
        from data.async_fetch import run_async

        async def _coro():
            return 42

        result = run_async(_coro())
        assert result == 42

    def test_run_async_with_exception(self):
        """run_async should propagate exceptions from the coroutine."""
        from data.async_fetch import run_async

        async def _bad():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(_bad())
