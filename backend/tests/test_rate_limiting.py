"""Tests for distributed rate limiting with Redis sorted sets."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


class TestRateLimiting:
    """Test cases for Redis-based rate limiting."""

    def setup_method(self):
        from backend.src.rag import router as router_module

        router_module._query_timestamps.clear()

    def teardown_method(self):
        from backend.src.rag import router as router_module

        router_module._query_timestamps.clear()

    @patch("backend.src.rag.router.get_redis_client")
    def test_redis_rate_limit_allows_under_limit(self, mock_get_client):
        """Test that requests under the limit are allowed."""
        from backend.src.rag.router import _check_rate_limit

        mock_client = MagicMock()
        mock_client.pipeline.return_value.execute.return_value = [0, 0, 1, True]
        mock_get_client.return_value = mock_client

        _check_rate_limit("user1")

        mock_client.pipeline.assert_called_once()

    @patch("backend.src.rag.router.get_redis_client")
    def test_redis_rate_limit_blocks_over_limit(self, mock_get_client):
        """Test that requests over the limit raise 429."""
        from backend.src.rag.router import _check_rate_limit

        mock_client = MagicMock()
        mock_client.pipeline.return_value.execute.return_value = [0, 0, 11, True]
        mock_get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("user1")

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail

    @patch("backend.src.rag.router.get_redis_client")
    def test_rate_limit_falls_back_to_memory_when_redis_down(self, mock_get_client):
        """Test that rate limiting falls back to in-memory when Redis unavailable."""
        from backend.src.rag.router import _check_rate_limit

        mock_get_client.return_value = None

        for i in range(10):
            _check_rate_limit("user2")

        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("user2")

        assert exc_info.value.status_code == 429

    @patch("backend.src.rag.router.get_redis_client")
    def test_rate_limit_per_user_isolation(self, mock_get_client):
        """Test that rate limits are per-user, not global."""
        from backend.src.rag.router import _check_rate_limit

        mock_client = MagicMock()
        mock_client.pipeline.return_value.execute.return_value = [0, 0, 1, True]
        mock_get_client.return_value = mock_client

        _check_rate_limit("user_a")
        _check_rate_limit("user_b")

        assert mock_client.pipeline.call_count == 2

    @patch("backend.src.rag.router.get_redis_client")
    def test_redis_uses_sorted_set_pipeline(self, mock_get_client):
        """Test that Redis rate limiting uses sorted set operations."""
        from backend.src.rag.router import _check_rate_limit

        mock_pipeline = MagicMock()
        mock_pipeline.execute.return_value = [0, 0, 1, True]
        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipeline
        mock_get_client.return_value = mock_client

        _check_rate_limit("user3")

        mock_pipeline.zremrangebyscore.assert_called_once()
        mock_pipeline.zadd.assert_called_once()
        mock_pipeline.zcard.assert_called_once()
        mock_pipeline.expire.assert_called_once()

    def test_in_memory_rate_limit_blocks_over_limit(self):
        """Test in-memory fallback blocks over limit."""
        from backend.src.rag.router import _check_rate_limit_in_memory

        for i in range(10):
            _check_rate_limit_in_memory("test_user")

        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit_in_memory("test_user")

        assert exc_info.value.status_code == 429

    def test_in_memory_rate_limit_allows_under_limit(self):
        """Test in-memory fallback allows under limit."""
        from backend.src.rag.router import _check_rate_limit_in_memory

        for i in range(5):
            _check_rate_limit_in_memory("fresh_user")

    @patch("backend.src.rag.router.get_redis_client")
    def test_redis_rate_limit_at_exact_boundary(self, mock_get_client):
        """Test rate limit at exactly the max requests boundary."""
        from backend.src.rag.router import _check_rate_limit

        mock_client = MagicMock()
        mock_client.pipeline.return_value.execute.return_value = [0, 0, 10, True]
        mock_get_client.return_value = mock_client

        _check_rate_limit("boundary_user")
