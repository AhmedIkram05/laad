"""Tests for RAG Redis caching module."""

from unittest.mock import MagicMock, patch
import json


class TestRedisCache:
    """Test cases for Redis caching functions."""

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_get_redis_client_connects(self, mock_redis_class, mock_pool_class):
        """Test that Redis client connects successfully via shared module."""
        from backend.src.cache import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        from backend.src.cache import redis_client

        redis_client._redis_client = None
        redis_client._redis_connection_pool = None

        client = get_redis_client()

        assert client is not None
        mock_instance.ping.assert_called_once()

    def test_get_query_hash_consistent(self):
        """Test that query hash is consistent for same query."""
        from backend.src.rag.cache import get_query_hash

        hash1 = get_query_hash("What is error A1?")
        hash2 = get_query_hash("what is error a1?")
        assert hash1 == hash2

    def test_get_query_hash_different_queries(self):
        """Test that different queries produce different hashes."""
        from backend.src.rag.cache import get_query_hash

        hash1 = get_query_hash("What is error A1?")
        hash2 = get_query_hash("What is error A2?")
        assert hash1 != hash2

    @patch("backend.src.rag.cache.get_redis_client")
    def test_get_cached_response_returns_cached(self, mock_get_client):
        """Test cache hit returns stored response."""
        from backend.src.rag.cache import get_cached_response

        mock_client = MagicMock()
        cached_data = json.dumps(
            {
                "answer": "Test answer",
                "uncertainty_score": 0.85,
                "confidence_level": "high",
            }
        )
        mock_client.get.return_value = cached_data
        mock_get_client.return_value = mock_client

        result = get_cached_response("What is error A1?")

        assert result is not None
        assert result["answer"] == "Test answer"
        assert result["uncertainty_score"] == 0.85

    @patch("backend.src.rag.cache.get_redis_client")
    def test_get_cached_response_returns_none_on_miss(self, mock_get_client):
        """Test cache miss returns None."""
        from backend.src.rag.cache import get_cached_response

        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_get_client.return_value = mock_client

        result = get_cached_response("Unknown query")

        assert result is None

    @patch("backend.src.rag.cache.get_redis_client")
    def test_get_cached_response_returns_none_on_error(self, mock_get_client):
        """Test Redis error returns None gracefully."""
        from backend.src.rag.cache import get_cached_response

        mock_get_client.side_effect = Exception("Redis connection failed")

        result = get_cached_response("test query")

        assert result is None

    @patch("backend.src.rag.cache.get_redis_client")
    def test_set_cached_response_stores_with_ttl(self, mock_get_client):
        """Test that response is cached with TTL."""
        from backend.src.rag.cache import set_cached_response

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = {
            "answer": "Test answer",
            "uncertainty_score": 0.85,
        }

        set_cached_response("What is error A1?", response)

        mock_client.setex.assert_called_once()
        call_args = mock_client.setex.call_args
        assert call_args[0][0].startswith("rag:response:")
        assert call_args[0][1] == 300
        assert json.loads(call_args[0][2]) == response

    @patch("backend.src.rag.cache.get_redis_client")
    def test_set_cached_response_handles_error(self, mock_get_client):
        """Test Redis error during set is handled gracefully."""
        from backend.src.rag.cache import set_cached_response

        mock_get_client.side_effect = Exception("Redis connection failed")

        set_cached_response("test query", {"answer": "test"})

        mock_get_client.assert_called_once()

    @patch("backend.src.rag.cache.get_redis_client")
    def test_set_cached_response_skips_when_no_client(self, mock_get_client):
        """Test that set skips when Redis client is None."""
        from backend.src.rag.cache import set_cached_response

        mock_get_client.return_value = None

        set_cached_response("test query", {"answer": "test"})

        mock_get_client.assert_called_once()
