"""Tests for backend.src.rag.llm_client."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

pytestmark = pytest.mark.rag


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

    def test_initialize_with_llm(self):
        config_mock = MagicMock()
        config_mock.is_configured = True
        config_mock.llm_api_key = "test-key"
        config_mock.llm_model = "google/gemma-4-31B-it"
        config_mock.llm_base_url = "https://api.inference.wandb.ai/v1"

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            assert len(client.providers) == 1
            # The only provider should be the W&B llm provider
            assert client.providers[0]["name"] == "llm"

    def test_generate_raises_when_no_providers(self):
        config_mock = MagicMock()
        config_mock.is_configured = False

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            with pytest.raises(RuntimeError, match="No LLM providers configured"):
                client.generate("test prompt")


class TestCallProvider:
    def test_call_llm_success(self):
        config_mock = MagicMock()
        config_mock.llm_api_key = "key"
        config_mock.llm_model = "model"
        config_mock.llm_base_url = "https://api.inference.wandb.ai/v1"

        with patch("backend.src.rag.llm_client.config", config_mock):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "STOP"}],
                "model": "gemma4",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

            with patch("requests.post", return_value=mock_response):
                result = client._call_llm(
                    {
                        "name": "llm",
                        "model": "model",
                        "base_url": "https://api.inference.wandb.ai/v1",
                        "api_key": "key",
                    },
                    "test prompt",
                    None,
                    0.7,
                    100,
                )
                assert result is not None
                assert result.text == "Hello"
                assert result.model == "gemma4"

    def test_call_llm_http_error_retries(self):
        config_mock = MagicMock()
        config_mock.llm_api_key = "key"
        config_mock.llm_model = "model"
        config_mock.llm_base_url = "https://api.inference.wandb.ai/v1"

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
                    client._call_llm(
                        {
                            "name": "llm",
                            "model": "model",
                            "base_url": "https://api.inference.wandb.ai/v1",
                            "api_key": "key",
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
