"""Tests for backend.src.rag.llm_client."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests


class TestRateLimiter:
    def test_not_rate_limited_initially(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert rl.is_rate_limited() is False

    def test_rate_limited_after_max_requests(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            rl.is_rate_limited()
        assert rl.is_rate_limited() is True

    def test_wait_time_returns_zero_when_not_limited(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert rl.wait_time() == 0.0

    def test_wait_time_positive_when_limited(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.is_rate_limited()
        assert rl.wait_time() > 0

    def test_expired_requests_removed(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=5, window_seconds=60)
        now = time.time()
        rl._requests["global"] = [now - 120, now - 90, now - 30]
        result = rl.is_rate_limited()
        assert isinstance(result, bool)


class TestLLMClient:
    def test_initialize_providers_empty_when_not_configured(self):
        config_mock = MagicMock()
        config_mock.is_configured = False

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            assert len(client.providers) == 0

    def test_initialize_with_ollama(self):
        config_mock = MagicMock()
        config_mock.is_configured = True
        config_mock.OLLAMA_BASE_URL = "http://localhost:11434"
        config_mock.OLLAMA_API_KEY = "test-key"
        config_mock.OLLAMA_MODEL = "gemma4:31b-cloud"
        config_mock.OLLAMA_FALLBACK_MODELS = ["nemotron-3:latest"]
        config_mock.RAG_PRIMARY_MODEL = ""
        config_mock.RAG_FALLBACK_MODEL = ""

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            assert len(client.providers) > 0
            # First provider should be Ollama
            assert client.providers[0]["name"] == "ollama"

    def test_generate_raises_when_no_providers(self):
        config_mock = MagicMock()
        config_mock.is_configured = False

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            with pytest.raises(RuntimeError, match="No LLM providers configured"):
                client.generate("test prompt")


class TestCallProvider:
    def test_call_ollama_success(self):
        config_mock = MagicMock()
        config_mock.OLLAMA_BASE_URL = "http://localhost:11434"
        config_mock.OLLAMA_API_KEY = "key"
        config_mock.OLLAMA_MODEL = "model"
        config_mock.RAG_PRIMARY_MODEL = ""
        config_mock.RAG_FALLBACK_MODEL = ""

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"content": "Hello"},
                "model": "gemma4",
            }

            with patch("requests.post", return_value=mock_response):
                result = client._call_provider(
                    {
                        "name": "ollama",
                        "model": "model",
                        "base_url": "http://localhost:11434",
                        "api_key": "key",
                        "api_type": "ollama",
                    },
                    "test prompt",
                    None,
                    0.7,
                    100,
                )
                assert result is not None
                assert result.text == "Hello"

    def test_call_ollama_http_error_retries(self):
        config_mock = MagicMock()
        config_mock.OLLAMA_BASE_URL = "http://localhost:11434"
        config_mock.OLLAMA_API_KEY = "key"
        config_mock.OLLAMA_MODEL = "model"
        config_mock.RAG_PRIMARY_MODEL = ""
        config_mock.RAG_FALLBACK_MODEL = ""

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_response
            )

            with patch("requests.post", return_value=mock_response):
                with pytest.raises(requests.exceptions.HTTPError):
                    client._call_provider(
                        {
                            "name": "ollama",
                            "model": "model",
                            "base_url": "http://localhost:11434",
                            "api_key": "key",
                            "api_type": "ollama",
                        },
                        "test",
                        None,
                        0.7,
                        100,
                    )


class TestGetLLMClient:
    def test_returns_singleton(self):
        with patch("backend.src.rag.llm_client.LLMClient") as mock_cls:
            from backend.src.rag.llm_client import get_llm_client  # noqa: E402
            import backend.src.rag.llm_client as _llm_mod

            _llm_mod._llm_client = None
            client = get_llm_client()
            assert client is not None
            # Second call should return same instance
            mock_cls.reset_mock()
            client2 = get_llm_client()
            assert client2 is not None
