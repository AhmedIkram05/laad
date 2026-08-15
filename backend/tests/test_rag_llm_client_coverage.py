"""Extended coverage tests for backend.src.rag.llm_client.

Covers the W&B Serverless Inference provider (_call_llm), rate-limit retry
with Retry-After header parsing, generic-exception retry with time.sleep,
LLMResponse dataclass, get_llm_client singleton, and RateLimiter config.
"""

from __future__ import annotations

import time
from dataclasses import fields as dc_fields
from unittest.mock import MagicMock, patch

import pytest
import requests

pytestmark = pytest.mark.rag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    """Return a MagicMock resembling backend.src.rag.config.config."""
    cfg = MagicMock()
    cfg.is_configured = overrides.get("is_configured", True)
    cfg.llm_api_key = overrides.get("llm_api_key", "test-key")
    cfg.llm_model = overrides.get("llm_model", "google/gemma-4-31B-it")
    cfg.llm_base_url = overrides.get(
        "llm_base_url", "https://api.inference.wandb.ai/v1"
    )
    cfg.temperature = overrides.get("temperature", 0.6)
    cfg.rate_limit_per_min = overrides.get("rate_limit_per_min", 0)
    return cfg


def _make_llm_provider(**overrides):
    return {
        "name": "llm",
        "model": overrides.get("model", "google/gemma-4-31B-it"),
        "api_key": overrides.get("api_key", "sk-test"),
        "base_url": overrides.get(
            "base_url", "https://api.inference.wandb.ai/v1"
        ),
    }


def _llm_success_response(text="Hello world", model=None):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {"content": text},
                "finish_reason": "stop",
            }
        ],
        "model": model or "google/gemma-4-31B-it",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _llm_error_response(status_code=400):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "error": {"message": "Bad request"},
    }
    mock_resp.headers = {}
    err = requests.exceptions.HTTPError(response=mock_resp)
    mock_resp.raise_for_status.side_effect = err
    return mock_resp, err


def _llm_rate_limit_response(retry_after=None):
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"error": {"message": "Rate limited"}}
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    mock_resp.headers = headers
    err = requests.exceptions.HTTPError(response=mock_resp)
    mock_resp.raise_for_status.side_effect = err
    return mock_resp, err


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_fields_exist(self):
        from backend.src.rag.llm_client import LLMResponse

        field_names = {f.name for f in dc_fields(LLMResponse)}
        assert field_names == {
            "text",
            "raw_response",
            "model",
            "finish_reason",
            "prompt_tokens",
            "completion_tokens",
        }

    def test_construction_with_all_fields(self):
        from backend.src.rag.llm_client import LLMResponse

        resp = LLMResponse(
            text="hi",
            raw_response={"ok": True},
            model="m",
            finish_reason="stop",
            prompt_tokens=5,
            completion_tokens=10,
        )
        assert resp.text == "hi"
        assert resp.raw_response == {"ok": True}
        assert resp.prompt_tokens == 5

    def test_optional_fields_default_none(self):
        from backend.src.rag.llm_client import LLMResponse

        resp = LLMResponse(text="x", raw_response={}, model="m", finish_reason="stop")
        assert resp.prompt_tokens is None
        assert resp.completion_tokens is None


# ---------------------------------------------------------------------------
# RateLimiter configuration
# ---------------------------------------------------------------------------


class TestRateLimiterConfig:
    def test_custom_window_and_max_requests(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=2, window_seconds=10)
        assert rl.max_requests == 2
        assert rl.window_seconds == 10
        assert rl.is_rate_limited() is False
        assert rl.is_rate_limited() is False
        assert rl.is_rate_limited() is True

    def test_wait_time_empty_key(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert rl.wait_time("nonexistent") == 0.0

    def test_isolation_between_keys(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.is_rate_limited("a") is False
        assert rl.is_rate_limited("a") is True
        # Key "b" should be independent
        assert rl.is_rate_limited("b") is False

    def test_requests_list_cleanup_on_expiry(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=3, window_seconds=1)
        now = time.time()
        # Inject expired timestamps
        rl._requests["global"] = [now - 10, now - 5, now - 2]
        # All should be expired, so not rate-limited
        assert rl.is_rate_limited() is False


# ---------------------------------------------------------------------------
# LLMClient initialization
# ---------------------------------------------------------------------------


class TestLLMClientInit:
    def test_llm_provider_when_configured(self):
        cfg = _make_config(
            llm_api_key="key",
            llm_model="google/gemma-4-31B-it",
            llm_base_url="https://api.inference.wandb.ai/v1",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            names = [p["name"] for p in client.providers]
            assert names == ["llm"]
            assert client.providers[0]["model"] == "google/gemma-4-31B-it"

    def test_no_providers_when_unconfigured(self):
        cfg = _make_config(is_configured=False, llm_api_key="")
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            assert client.providers == []


# ---------------------------------------------------------------------------
# _call_llm (W&B Serverless Inference provider)
# ---------------------------------------------------------------------------


class TestCallLLM:
    def test_success_response(self):
        provider = _make_llm_provider()
        mock_resp = _llm_success_response(text="Hi there")

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_llm(provider, "prompt", None, 0.7, 100)

        assert result.text == "Hi there"
        assert result.model == "google/gemma-4-31B-it"
        assert result.finish_reason == "stop"

    def test_with_system_prompt(self):
        provider = _make_llm_provider()
        mock_resp = _llm_success_response()

        captured = []

        def capture_post(url, headers=None, json=None, timeout=None):
            captured.append(json)
            return mock_resp

        with patch(
            "backend.src.rag.llm_client.requests.post", side_effect=capture_post
        ):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            client._call_llm(provider, "user prompt", "system msg", 0.3, 512)

        messages = captured[0]["messages"]
        assert messages[0] == {"role": "system", "content": "system msg"}
        assert messages[1] == {"role": "user", "content": "user prompt"}

    def test_api_error_raises_runtime_error(self):
        provider = _make_llm_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": {"message": "Model not found"}}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="LLM API error"):
                client._call_llm(provider, "test", None, 0.7, 100)

    def test_empty_choices_raises_runtime_error(self):
        provider = _make_llm_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="empty response"):
                client._call_llm(provider, "test", None, 0.7, 100)

    def test_empty_message_content_raises_runtime_error(self):
        provider = _make_llm_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="empty message content"):
                client._call_llm(provider, "test", None, 0.7, 100)

    def test_actual_model_extracted_from_response(self):
        provider = _make_llm_provider(model="fallback-model")
        mock_resp = _llm_success_response(model="google/gemma-4-31B-it")

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_llm(provider, "test", None, 0.7, 100)

        assert result.model == "google/gemma-4-31B-it"

    def test_http_error_propagates(self):
        provider = _make_llm_provider()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=500)
        )
        mock_resp.json.return_value = {}

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(requests.exceptions.HTTPError):
                client._call_llm(provider, "test", None, 0.7, 100)

    def test_prompt_tokens_and_completion_tokens_extracted(self):
        provider = _make_llm_provider()
        mock_resp = _llm_success_response()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_llm(provider, "test", None, 0.7, 100)

        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20


# ---------------------------------------------------------------------------
# generate() with rate limiting
# ---------------------------------------------------------------------------


class TestGenerateRateLimited:
    def test_generate_raises_when_rate_limited(self):
        cfg = _make_config(llm_api_key="key", rate_limit_per_min=20)
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            with patch("backend.src.rag.llm_client._rate_limiter") as mock_rl:
                mock_rl.is_rate_limited.return_value = True
                mock_rl.wait_time.return_value = 30.0
                with pytest.raises(RuntimeError, match="Rate limit exceeded"):
                    client.generate("test")

    def test_generate_raises_when_no_providers(self):
        cfg = _make_config(is_configured=False)
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            with pytest.raises(RuntimeError, match="No LLM providers configured"):
                client.generate("test")


# ---------------------------------------------------------------------------
# Retry logic — rate limit with Retry-After header
# ---------------------------------------------------------------------------


class TestRetryRateLimit:
    def test_rate_limit_retry_with_retry_after_header(self):
        cfg = _make_config(llm_api_key="key")
        rate_limit_resp, rate_limit_err = _llm_rate_limit_response(retry_after=10)
        success_resp = _llm_success_response(text="OK")

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                rate_limit_resp.raise_for_status.side_effect = rate_limit_err
                return rate_limit_resp
            return success_resp

        with patch("backend.src.rag.llm_client.config", cfg):
            with patch("backend.src.rag.llm_client.time.sleep") as mock_sleep:
                with patch(
                    "backend.src.rag.llm_client.requests.post", side_effect=side_effect
                ):
                    from backend.src.rag.llm_client import LLMClient

                    client = LLMClient()
                    result = client.generate("test prompt")

        assert result is not None
        assert result.text == "OK"
        # sleep(retry_after + 1) → sleep(11)
        mock_sleep.assert_called_with(11)

    def test_rate_limit_retry_with_invalid_retry_after_header(self):
        cfg = _make_config(llm_api_key="key")
        rate_limit_resp, rate_limit_err = _llm_rate_limit_response(
            retry_after="invalid"
        )
        success_resp = _llm_success_response(text="OK")

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                rate_limit_resp.raise_for_status.side_effect = rate_limit_err
                return rate_limit_resp
            return success_resp

        with patch("backend.src.rag.llm_client.config", cfg):
            with patch("backend.src.rag.llm_client.time.sleep") as mock_sleep:
                with patch(
                    "backend.src.rag.llm_client.requests.post", side_effect=side_effect
                ):
                    from backend.src.rag.llm_client import LLMClient

                    client = LLMClient()
                    result = client.generate("test prompt")

        assert result is not None
        # Invalid header → defaults to 5, sleep(5+1)=sleep(6)
        mock_sleep.assert_called_with(6)


# ---------------------------------------------------------------------------
# Generic exception retry with time.sleep
# ---------------------------------------------------------------------------


class TestGenericExceptionRetry:
    def test_generic_exception_retries_with_sleep(self):
        cfg = _make_config(llm_api_key="key")

        call_count = 0
        success_resp = _llm_success_response(text="Recovered")

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Connection refused")
            return success_resp

        with patch("backend.src.rag.llm_client.config", cfg):
            with patch("backend.src.rag.llm_client.time.sleep") as mock_sleep:
                with patch(
                    "backend.src.rag.llm_client.requests.post", side_effect=side_effect
                ):
                    from backend.src.rag.llm_client import LLMClient

                    client = LLMClient()
                    result = client.generate("test")

        assert result is not None
        assert result.text == "Recovered"
        # Two retries with increasing delay: RETRY_DELAY*1, RETRY_DELAY*2
        assert mock_sleep.call_count == 2

    def test_generic_exception_exhausts_retries_raises(self):
        cfg = _make_config(llm_api_key="key")

        def always_fail(*args, **kwargs):
            raise ValueError("Always fails")

        with patch("backend.src.rag.llm_client.config", cfg):
            with patch("backend.src.rag.llm_client.time.sleep"):
                with patch(
                    "backend.src.rag.llm_client.requests.post", side_effect=always_fail
                ):
                    from backend.src.rag.llm_client import LLMClient

                    client = LLMClient()
                    with pytest.raises(RuntimeError, match="All LLM providers failed"):
                        client.generate("test")


# ---------------------------------------------------------------------------
# Timeout retry path
# ---------------------------------------------------------------------------


class TestTimeoutRetry:
    def test_timeout_retries_then_raises(self):
        cfg = _make_config(llm_api_key="key")

        with patch("backend.src.rag.llm_client.config", cfg):
            with patch("backend.src.rag.llm_client.time.sleep"):
                with patch("backend.src.rag.llm_client.requests.post") as mock_post:
                    mock_post.side_effect = requests.exceptions.Timeout("timed out")
                    from backend.src.rag.llm_client import LLMClient

                    client = LLMClient()
                    with pytest.raises(RuntimeError, match="All LLM providers failed"):
                        client.generate("test")


# ---------------------------------------------------------------------------
# get_llm_client singleton
# ---------------------------------------------------------------------------


class TestGetLLMSingleton:
    def test_singleton_returns_same_instance(self):
        import backend.src.rag.llm_client as mod

        mod._llm_client = None
        with patch("backend.src.rag.llm_client.LLMClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            c1 = mod.get_llm_client()
            c2 = mod.get_llm_client()
            assert c1 is c2
            mock_cls.assert_called_once()
        mod._llm_client = None

    def test_singleton_creates_new_when_none(self):
        import backend.src.rag.llm_client as mod

        mod._llm_client = None
        cfg = _make_config(is_configured=False)
        with patch("backend.src.rag.llm_client.config", cfg):
            c1 = mod.get_llm_client()
            assert c1 is not None
        mod._llm_client = None

    def test_singleton_reuses_existing(self):
        import backend.src.rag.llm_client as mod

        existing = MagicMock()
        mod._llm_client = existing
        result = mod.get_llm_client()
        assert result is existing
        mod._llm_client = None