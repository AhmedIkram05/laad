"""Tests for RAG Redis caching module."""

from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest

pytestmark = pytest.mark.rag


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

        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0].startswith("rag:response:")
        assert call_args[1]["ex"] == 300
        assert json.loads(call_args[0][1]) == response

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


class TestDefaultCacheProfile:
    """Audit finding #4: cache reads and writes must both gate on the exact
    default request profile — a response generated under custom top_k/flags
    must never poison the key a default-profile request reads."""

    @staticmethod
    def _default_kwargs():
        from backend.src.rag.config import config

        return {
            "top_k": config.retrieval_top_k,
            "error_only": config.error_only,
            "most_recent_first": config.most_recent_first,
            "include_uncertainty": True,
            "enable_reflexion": config.reflexion_enabled,
            "enable_citation_grounding": config.citation_grounding_enabled,
            "enable_self_consistency": config.self_consistency_enabled,
            "atm_id": None,
            "anomaly_type": None,
        }

    def test_default_profile_accepts_defaults(self):
        from backend.src.rag.router import _default_cache_profile

        assert _default_cache_profile(**self._default_kwargs()) is True

    def test_custom_top_k_rejected(self):
        from backend.src.rag.config import config
        from backend.src.rag.router import _default_cache_profile

        kwargs = self._default_kwargs()
        kwargs["top_k"] = config.retrieval_top_k + 1
        assert _default_cache_profile(**kwargs) is False

    def test_custom_flags_rejected(self):
        from backend.src.rag.config import config
        from backend.src.rag.router import _default_cache_profile

        kwargs = self._default_kwargs()
        kwargs["enable_self_consistency"] = not config.self_consistency_enabled
        assert _default_cache_profile(**kwargs) is False

        kwargs = self._default_kwargs()
        kwargs["enable_reflexion"] = not config.reflexion_enabled
        assert _default_cache_profile(**kwargs) is False

        kwargs = self._default_kwargs()
        kwargs["include_uncertainty"] = False
        assert _default_cache_profile(**kwargs) is False

    def test_scoped_requests_rejected(self):
        from backend.src.rag.router import _default_cache_profile

        kwargs = self._default_kwargs()
        kwargs["atm_id"] = "ATM-GB-0001"
        assert _default_cache_profile(**kwargs) is False

        kwargs = self._default_kwargs()
        kwargs["anomaly_type"] = "A1"
        assert _default_cache_profile(**kwargs) is False

    @staticmethod
    def _run_legacy(**overrides):
        """Run _run_legacy_query with fully mocked internals.

        Returns (response, set_cached_response spy).
        """
        from contextlib import ExitStack
        from types import SimpleNamespace

        from backend.src.rag.config import config

        chunk = SimpleNamespace(
            text="log 1",
            chunk_id="doc_1",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            confidence_score=0.9,
        )
        generated = SimpleNamespace(
            text="answer",
            sources=[chunk],
            model="test-model",
            self_consistency_score=0.9,
            verbalized_confidence=0.8,
            grounding_score=0.7,
            cross_encoder_used=False,
            was_revised=False,
            critique_text="",
        )
        uncertainty = SimpleNamespace(
            final_confidence=0.8,
            confidence_level="high",
            is_uncertain=False,
            recommendation="Review recommended",
            generation_variance=0.1,
        )
        kwargs = {
            "query": "why is atm failing",
            "sanitized_query": "why is atm failing",
            "query_type": None,
            "atm_id": None,
            "anomaly_type": None,
            "error_only": config.error_only,
            "most_recent_first": config.most_recent_first,
            "top_k": config.retrieval_top_k,
            "include_uncertainty": True,
            "enable_reflexion": config.reflexion_enabled,
            "enable_citation_grounding": config.citation_grounding_enabled,
            "enable_self_consistency": config.self_consistency_enabled,
            "current_user": {"sub": "admin"},
        }
        kwargs.update(overrides)
        from backend.src.rag.router import _run_legacy_query

        with ExitStack() as stack:
            gr = stack.enter_context(patch("backend.src.rag.router.get_retriever"))
            gg = stack.enter_context(patch("backend.src.rag.router.get_generator"))
            gu = stack.enter_context(
                patch("backend.src.rag.router.get_uncertainty_estimator")
            )
            stack.enter_context(
                patch(
                    "backend.src.rag.router._get_user_id_from_username", return_value=1
                )
            )
            stack.enter_context(
                patch("backend.src.rag.router._save_query_history", return_value=42)
            )
            cache_spy = stack.enter_context(
                patch("backend.src.rag.router.set_cached_response")
            )
            gr.return_value.retrieve.return_value = [chunk]
            gg.return_value.generate.return_value = generated
            gu.return_value.estimate.return_value = uncertainty
            result = _run_legacy_query(**kwargs)
        return result, cache_spy

    def test_legacy_write_skipped_for_custom_profile(self):
        from backend.src.rag.config import config

        spies = [
            self._run_legacy(
                top_k=config.retrieval_top_k + 1,
                enable_self_consistency=not config.self_consistency_enabled,
            )[1],
            self._run_legacy(
                top_k=config.retrieval_top_k,
                enable_reflexion=not config.reflexion_enabled,
            )[1],
            self._run_legacy(top_k=config.retrieval_top_k, include_uncertainty=False)[
                1
            ],
        ]
        for spy in spies:
            spy.assert_not_called()

    def test_default_profile_response_is_cached(self):
        from backend.src.rag.config import config

        result, cache_spy = self._run_legacy(
            top_k=config.retrieval_top_k,
            error_only=config.error_only,
            most_recent_first=config.most_recent_first,
            include_uncertainty=True,
            enable_reflexion=config.reflexion_enabled,
            enable_citation_grounding=config.citation_grounding_enabled,
            enable_self_consistency=config.self_consistency_enabled,
        )
        cache_spy.assert_called_once()
        assert cache_spy.call_args[0][0] == "why is atm failing"
        assert result.answer == "answer"

    def test_champion_write_gated_by_cacheable(self):
        import asyncio

        from backend.src.rag.router import _run_champion_query

        agent_result = {
            "answer": "agent answer",
            "sources": [
                {
                    "text": "Network timeout at ATM-GB-0001",
                    "chunk_id": "doc_1",
                    "atm_id": "ATM-GB-0001",
                    "timestamp": "2026-05-15T10:00:00Z",
                    "confidence_score": 0.9,
                }
            ],
            "uncertainty_score": 0.9,
            "confidence_level": "high",
            "is_uncertain": False,
            "recommendation": "Auto-respond",
            "model_used": "agentic-model",
        }

        def _run(cacheable):
            with (
                patch(
                    "backend.src.rag.agent.run_agent_query",
                    new=AsyncMock(return_value=agent_result),
                ),
                patch(
                    "backend.src.rag.router._get_user_id_from_username",
                    return_value=1,
                ),
                patch("backend.src.rag.router._save_query_history", return_value=7),
                patch("backend.src.rag.router._save_agent_trace"),
                patch("backend.src.rag.router.set_cached_response") as cache_spy,
            ):
                asyncio.run(
                    _run_champion_query(
                        query="why is atm failing",
                        sanitized_query="why is atm failing",
                        atm_id=None,
                        top_k=None,
                        current_user={"sub": "admin"},
                        cacheable=cacheable,
                    )
                )
                return cache_spy

        _run(cacheable=False).assert_not_called()
        _run(cacheable=True).assert_called_once()
