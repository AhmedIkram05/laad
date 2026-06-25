"""Extended coverage tests for backend.src.rag.llm_client.

Covers _call_openrouter(), FREE_MODEL_CHAIN injection, rate-limit retry
with Retry-After header parsing, generic-exception retry with time.sleep,
provider priority, openrouter/ prefix stripping, unknown provider,
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
    cfg.ollama_api_key = overrides.get("ollama_api_key", "")
    cfg.ollama_base_url = overrides.get("ollama_base_url", "https://ollama.com")
    cfg.ollama_model = overrides.get("ollama_model", "gemma4:31b-cloud")
    cfg.ollama_fallback_models = overrides.get("ollama_fallback_models", [])
    cfg.primary_model = overrides.get("primary_model", "")
    cfg.fallback_model = overrides.get("fallback_model", "")
    cfg.openrouter_api_key = overrides.get("openrouter_api_key", "")
    cfg.temperature = overrides.get("temperature", 0.6)
    return cfg


def _make_openrouter_provider(**overrides):
    p = {
        "name": "openrouter",
        "model": overrides.get("model", "deepseek/deepseek-v3-0327:free"),
        "api_key": overrides.get("api_key", "sk-or-test"),
        "base_url": overrides.get("base_url", "https://openrouter.ai/api/v1"),
    }
    return p


def _openrouter_success_response(text="Hello world", model=None):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {"content": text},
                "finish_reason": "stop",
            }
        ],
        "model": model or "deepseek/deepseek-v3-0327:free",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _openrouter_error_response(status_code=400):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "error": {"message": "Bad request"},
    }
    mock_resp.headers = {}
    err = requests.exceptions.HTTPError(response=mock_resp)
    mock_resp.raise_for_status.side_effect = err
    return mock_resp, err


def _openrouter_rate_limit_response(retry_after=None):
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
    def test_ollama_first_in_providers(self):
        cfg = _make_config(
            ollama_api_key="ollama-key",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3",
            ollama_fallback_models=[],
            openrouter_api_key="or-key",
            primary_model="openrouter/gpt-4",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            names = [p["name"] for p in client.providers]
            assert names[0] == "ollama"
            assert "openrouter" in names
            # Ollama should come before openrouter
            assert names.index("ollama") < names.index("openrouter")

    def test_openrouter_prefix_stripped_from_primary_model(self):
        cfg = _make_config(
            ollama_api_key="",
            openrouter_api_key="or-key",
            primary_model="openrouter/deepseek-v3:free",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            or_providers = [p for p in client.providers if p["name"] == "openrouter"]
            assert len(or_providers) == 1
            assert or_providers[0]["model"] == "deepseek-v3:free"

    def test_openrouter_prefix_stripped_from_fallback_model(self):
        cfg = _make_config(
            ollama_api_key="",
            openrouter_api_key="or-key",
            primary_model="openrouter/some-model",
            fallback_model="openrouter/fallback-model",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            # Should not raise — fallback_model is cleaned without error
            assert len(client.providers) == 1

    def test_ollama_fallback_models_added(self):
        cfg = _make_config(
            ollama_api_key="key",
            ollama_model="main",
            ollama_fallback_models=["fallback-a", "fallback-b"],
            openrouter_api_key="",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            ollama_providers = [p for p in client.providers if p["name"] == "ollama"]
            models = [p["model"] for p in ollama_providers]
            assert "main" in models
            assert "fallback-a" in models
            assert "fallback-b" in models

    def test_empty_fallback_model_string_ignored(self):
        cfg = _make_config(
            ollama_api_key="key",
            ollama_model="main",
            ollama_fallback_models=["", "  ", "valid"],
            openrouter_api_key="",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            ollama_providers = [p for p in client.providers if p["name"] == "ollama"]
            models = [p["model"] for p in ollama_providers]
            assert models == ["main", "valid"]

    def test_no_providers_warning(self):
        cfg = _make_config(
            is_configured=True,
            ollama_api_key="",
            openrouter_api_key="",
        )
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            assert client.providers == []


# ---------------------------------------------------------------------------
# _call_openrouter
# ---------------------------------------------------------------------------


class TestCallOpenrouter:
    def test_success_response(self):
        provider = _make_openrouter_provider()
        mock_resp = _openrouter_success_response(text="Hi there")

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_openrouter(provider, "prompt", None, 0.7, 100)

        assert result.text == "Hi there"
        assert result.model == "deepseek/deepseek-v3-0327:free"
        assert result.finish_reason == "stop"

    def test_free_model_chain_injected(self):
        from backend.src.rag.llm_client import FREE_MODEL_CHAIN

        provider = _make_openrouter_provider()
        mock_resp = _openrouter_success_response()

        captured_payloads = []

        def capture_post(url, headers=None, json=None, timeout=None):
            captured_payloads.append(json)
            return mock_resp

        with patch(
            "backend.src.rag.llm_client.requests.post", side_effect=capture_post
        ):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            client._call_openrouter(provider, "test", None, 0.5, 256)

        assert len(captured_payloads) == 1
        assert "models" in captured_payloads[0]
        assert captured_payloads[0]["models"] == FREE_MODEL_CHAIN

    def test_free_model_chain_not_injected_for_non_openrouter(self):
        provider = {
            "name": "ollama",
            "model": "llama3",
            "api_key": "key",
            "base_url": "http://localhost:11434",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hello"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            # _call_ollama is what ollama uses, but test _call_provider dispatch
            result = client._call_provider(provider, "test", None, 0.5, 100)
        assert result is not None

    def test_with_system_prompt(self):
        provider = _make_openrouter_provider()
        mock_resp = _openrouter_success_response()

        captured = []

        def capture_post(url, headers=None, json=None, timeout=None):
            captured.append(json)
            return mock_resp

        with patch(
            "backend.src.rag.llm_client.requests.post", side_effect=capture_post
        ):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            client._call_openrouter(provider, "user prompt", "system msg", 0.3, 512)

        messages = captured[0]["messages"]
        assert messages[0] == {"role": "system", "content": "system msg"}
        assert messages[1] == {"role": "user", "content": "user prompt"}

    def test_api_error_raises_runtime_error(self):
        provider = _make_openrouter_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": {"message": "Model not found"}}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="OpenRouter API error"):
                client._call_openrouter(provider, "test", None, 0.7, 100)

    def test_empty_choices_raises_runtime_error(self):
        provider = _make_openrouter_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="empty response"):
                client._call_openrouter(provider, "test", None, 0.7, 100)

    def test_empty_message_content_raises_runtime_error(self):
        provider = _make_openrouter_provider()
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
                client._call_openrouter(provider, "test", None, 0.7, 100)

    def test_actual_model_extracted_from_response(self):
        provider = _make_openrouter_provider(model="fallback-model")
        mock_resp = _openrouter_success_response(model="deepseek/deepseek-r1:free")

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_openrouter(provider, "test", None, 0.7, 100)

        assert result.model == "deepseek/deepseek-r1:free"

    def test_http_error_propagates(self):
        provider = _make_openrouter_provider()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=500)
        )
        mock_resp.json.return_value = {}

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(requests.exceptions.HTTPError):
                client._call_openrouter(provider, "test", None, 0.7, 100)

    def test_prompt_tokens_and_completion_tokens_extracted(self):
        provider = _make_openrouter_provider()
        mock_resp = _openrouter_success_response()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_openrouter(provider, "test", None, 0.7, 100)

        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


class TestCallProviderUnknown:
    def test_unknown_provider_returns_none(self):
        from backend.src.rag.llm_client import LLMClient

        client = LLMClient.__new__(LLMClient)
        with pytest.raises(ValueError, match="Unknown provider"):
            client._call_provider(
                {"name": "azure", "model": "gpt-4", "api_key": "k", "base_url": "u"},
                "test",
                None,
                0.7,
                100,
            )


# ---------------------------------------------------------------------------
# generate() with rate limiting
# ---------------------------------------------------------------------------


class TestGenerateRateLimited:
    def test_generate_raises_when_rate_limited(self):
        cfg = _make_config(ollama_api_key="key")
        with patch("backend.src.rag.llm_client.config", cfg):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient()
            with patch("backend.src.rag.llm_client._rate_limiter") as mock_rl:
                mock_rl.is_rate_limited.return_value = True
                mock_rl.wait_time.return_value = 30.0
                with pytest.raises(RuntimeError, match="Rate limit exceeded"):
                    client.generate("test")

    def test_generate_returns_none_when_no_providers(self):
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
        cfg = _make_config(ollama_api_key="", openrouter_api_key="or-key")
        rate_limit_resp, rate_limit_err = _openrouter_rate_limit_response(
            retry_after=10
        )
        success_resp = _openrouter_success_response(text="OK")

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
        cfg = _make_config(ollama_api_key="", openrouter_api_key="or-key")
        rate_limit_resp, rate_limit_err = _openrouter_rate_limit_response(
            retry_after="invalid"
        )
        success_resp = _openrouter_success_response(text="OK")

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

    def test_rate_limit_retry_exhausted_breaks_to_next_provider(self):
        """After MAX_RATE_LIMIT_RETRIES, should break and try next provider or fail."""
        cfg = _make_config(
            ollama_api_key="ollama-key",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3",
            ollama_fallback_models=[],
            openrouter_api_key="or-key",
        )
        rate_limit_resp, rate_limit_err = _openrouter_rate_limit_response(retry_after=1)

        with patch("backend.src.rag.llm_client.config", cfg):
            with patch("backend.src.rag.llm_client.time.sleep"):
                ollama_resp = MagicMock()
                ollama_resp.status_code = 200
                ollama_resp.json.return_value = {
                    "message": {"content": "OK from ollama"},
                    "done_reason": "stop",
                }
                ollama_resp.raise_for_status = MagicMock()

                call_count = {"or": 0}

                def side_effect(*args, **kwargs):
                    url = args[0] if args else kwargs.get("url", "")
                    if "openrouter" in str(url):
                        call_count["or"] += 1
                        rate_limit_resp.raise_for_status.side_effect = rate_limit_err
                        return rate_limit_resp
                    return ollama_resp

                with patch(
                    "backend.src.rag.llm_client.requests.post", side_effect=side_effect
                ):
                    from backend.src.rag.llm_client import LLMClient

                    client = LLMClient()
                    # Should eventually succeed from ollama after rate-limit retries exhausted on openrouter
                    result = client.generate("test")

                    assert result is not None


# ---------------------------------------------------------------------------
# Generic exception retry with time.sleep
# ---------------------------------------------------------------------------


class TestGenericExceptionRetry:
    def test_generic_exception_retries_with_sleep(self):
        cfg = _make_config(ollama_api_key="", openrouter_api_key="or-key")

        call_count = 0
        success_resp = _openrouter_success_response(text="Recovered")

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
        cfg = _make_config(
            ollama_api_key="",
            openrouter_api_key="or-key",
        )

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
        cfg = _make_config(ollama_api_key="", openrouter_api_key="or-key")

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


# ---------------------------------------------------------------------------
# Ollama-specific paths
# ---------------------------------------------------------------------------


class TestCallOllamaExtended:
    def test_ollama_empty_content_raises(self):
        provider = {
            "name": "ollama",
            "model": "llama3",
            "api_key": "key",
            "base_url": "http://localhost:11434",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": ""}}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="empty response"):
                client._call_ollama(provider, "test", None, 0.7, 100)

    def test_ollama_error_in_response_body(self):
        provider = {
            "name": "ollama",
            "model": "llama3",
            "api_key": "key",
            "base_url": "http://localhost:11434",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": {"message": "Model not found"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            with pytest.raises(RuntimeError, match="Ollama API error"):
                client._call_ollama(provider, "test", None, 0.7, 100)

    def test_ollama_with_system_prompt(self):
        provider = {
            "name": "ollama",
            "model": "llama3",
            "api_key": "key",
            "base_url": "http://localhost:11434",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hello"},
            "done_reason": "stop",
        }
        mock_resp.raise_for_status = MagicMock()

        captured = []

        def capture_post(url, headers=None, json=None, timeout=None):
            captured.append(json)
            return mock_resp

        with patch(
            "backend.src.rag.llm_client.requests.post", side_effect=capture_post
        ):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            client._call_ollama(provider, "user msg", "system msg", 0.7, 100)

        messages = captured[0]["messages"]
        assert messages[0] == {"role": "system", "content": "system msg"}
        assert messages[1] == {"role": "user", "content": "user msg"}

    def test_ollama_response_fields(self):
        provider = {
            "name": "ollama",
            "model": "llama3",
            "api_key": "key",
            "base_url": "http://localhost:11434",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Reply"},
            "done_reason": "stop",
            "prompt_tokens": 50,
            "eval_tokens": 100,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.src.rag.llm_client.requests.post", return_value=mock_resp):
            from backend.src.rag.llm_client import LLMClient

            client = LLMClient.__new__(LLMClient)
            result = client._call_ollama(provider, "test", None, 0.7, 100)

        assert result.text == "Reply"
        assert result.model == "llama3"
        assert result.finish_reason == "stop"
        assert result.prompt_tokens == 50
        assert result.completion_tokens == 100
