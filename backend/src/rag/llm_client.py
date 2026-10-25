"""Unified LLM client for OpenAI-compatible chat-completions providers.

W&B Serverless Inference is primary (LLM_API_KEY / WANDB_API_KEY); OpenRouter
(OPENROUTER_API_KEY / TYPESAFE_API_KEY) is the fallback and the only provider
when no W&B key is present.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import requests

from backend.src.rag.config import config

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 20
# (connect, read) tuple: a hung connect no longer burns the full read budget
# per attempt (requests applies each element separately).
REQUEST_TIMEOUT = (10, 90)
MAX_RETRIES = 2
MAX_RATE_LIMIT_RETRIES = 5
RETRY_DELAY = 2.0
# Longest a rate-limited caller waits for bucket space before failing.
RATE_LIMIT_MAX_WAIT_S = 30.0


class RateLimiter:
    """Simple in-memory token bucket rate limiter.

    Thread-safe: FastAPI dispatches sync endpoints to a threadpool, so the
    bucket dict can be mutated concurrently.
    """

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        entries = [t for t in self._requests.get(key, ()) if t > cutoff]
        if entries:
            self._requests[key] = entries
        else:
            # Drop empty buckets so per-request keys don't accumulate forever.
            self._requests.pop(key, None)
        return self._requests.get(key, [])

    def is_rate_limited(self, key: str = "global") -> bool:
        with self._lock:
            now = time.time()
            entries = self._prune(key, now)
            if len(entries) >= self.max_requests:
                return True
            entries.append(now)
            self._requests[key] = entries
            return False

    def wait_time(self, key: str = "global") -> float:
        with self._lock:
            entries = self._requests.get(key, [])
            if not entries:
                return 0.0
            oldest = min(entries)
            return max(0.0, (oldest + self.window_seconds) - time.time())

    def acquire(self, key: str = "global", max_wait: float = 0.0) -> bool:
        """Reserve a slot, waiting up to max_wait seconds for one to free up.

        Returns True when a slot was reserved; False when the bucket is still
        full after max_wait. Callers decide whether to raise or degrade.
        """
        deadline = time.time() + max(max_wait, 0.0)
        if self.max_requests <= 0:
            return False
        while True:
            with self._lock:
                now = time.time()
                entries = self._prune(key, now)
                if len(entries) < self.max_requests:
                    entries.append(now)
                    self._requests[key] = entries
                    return True
                wait = (min(entries) + self.window_seconds) - now
            if wait <= 0:
                return False
            remaining = deadline - time.time()
            if remaining <= 0:
                return False
            time.sleep(min(wait, remaining))


_rate_limiter = RateLimiter(max_requests=config.rate_limit_per_min)


def _openrouter_api_key() -> Optional[str]:
    """OpenRouter key: OPENROUTER_API_KEY, or the legacy TYPESAFE_API_KEY name."""
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("TYPESAFE_API_KEY") or None


@dataclass
class LLMResponse:
    """Response from LLM with metadata."""

    text: str
    raw_response: dict
    model: str
    finish_reason: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    # Exact billed cost in USD, from OpenRouter's usage.cost when reported.
    cost_usd: Optional[float] = None


class LLMClient:
    """LLM client over OpenAI-compatible providers (W&B primary, OpenRouter fallback)."""

    def __init__(self):
        self.providers = self._initialize_providers()
        if not self.providers:
            logger.warning("LLM client initialized but no API keys configured")

    def _initialize_providers(self) -> list[dict]:
        """W&B Serverless first (primary); OpenRouter as fallback."""
        providers = []

        if config.is_configured and config.llm_api_key:
            providers.append(
                {
                    "name": "llm",
                    "model": config.llm_model,
                    "api_key": config.llm_api_key,
                    "base_url": config.llm_base_url,
                }
            )

        openrouter_key = _openrouter_api_key()
        if openrouter_key:
            providers.append(
                {
                    "name": "openrouter",
                    "model": config.llm_model,
                    "api_key": openrouter_key,
                    "base_url": OPENROUTER_BASE_URL,
                }
            )

        if not providers:
            logger.warning(
                "No LLM providers available - RAG will return error messages"
            )

        logger.info(
            f"Initialized {len(providers) if providers else 0} LLM providers: {[p['name'] for p in providers] if providers else []}"
        )
        return providers

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = config.temperature,
        max_tokens: int = 2048,
        rate_limit_key: Optional[str] = None,
    ) -> LLMResponse:
        """Generate response with automatic retries on failure.

        rate_limit_key scopes the rate-limit bucket: pass one key per user
        request so internal multi-call generation (self-consistency, reflexion,
        verbalized confidence) counts as a single request instead of one entry
        per LLM call.
        """
        if not self.providers:
            raise RuntimeError(
                "No LLM providers configured. Set at least one of WANDB_API_KEY, "
                "LLM_API_KEY, OPENROUTER_API_KEY, or TYPESAFE_API_KEY."
            )

        if config.rate_limit_per_min > 0 and not _rate_limiter.acquire(
            rate_limit_key or "global", max_wait=RATE_LIMIT_MAX_WAIT_S
        ):
            raise RuntimeError(
                f"Rate limit exceeded. Still saturated after waiting "
                f"{RATE_LIMIT_MAX_WAIT_S:.0f}s — please retry later."
            )

        last_error = None

        for provider in self.providers:
            # 429s wait out Retry-After without consuming the attempt budget,
            # so the MAX_RATE_LIMIT_RETRIES constant is actually reachable.
            rate_limit_retries = 0
            attempts = 0
            while attempts <= MAX_RETRIES:
                try:
                    response = self._call_llm(
                        provider=provider,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    logger.info(
                        f"Successfully generated response using {provider['name']} (attempt {attempts + 1})"
                    )
                    return response
                except requests.exceptions.Timeout:
                    attempts += 1
                    logger.warning(
                        f"Provider {provider['name']} timed out (attempt {attempts}/{MAX_RETRIES + 1})"
                    )
                    last_error = RuntimeError(
                        f"Request timed out (connect={REQUEST_TIMEOUT[0]}s, read={REQUEST_TIMEOUT[1]}s)"
                    )
                    if attempts <= MAX_RETRIES:
                        # Back off before re-hitting a timing-out provider.
                        time.sleep(RETRY_DELAY * attempts)
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code == 429:
                        retry_after = 5
                        if e.response.headers.get("Retry-After"):
                            try:
                                retry_after = int(e.response.headers["Retry-After"])
                            except (ValueError, TypeError):
                                pass
                        rate_limit_retries += 1
                        if rate_limit_retries > MAX_RATE_LIMIT_RETRIES:
                            logger.warning(
                                f"Provider {provider['name']} rate limit retries exhausted"
                            )
                            last_error = e
                            break
                        logger.warning(
                            f"Provider {provider['name']} rate limited, waiting {retry_after + 1}s (retry {rate_limit_retries}/{MAX_RATE_LIMIT_RETRIES})"
                        )
                        last_error = e
                        time.sleep(retry_after + 1)
                        continue
                    logger.warning(f"Provider {provider['name']} HTTP error: {e}")
                    last_error = e
                    break
                except Exception as e:
                    attempts += 1
                    logger.warning(f"Provider {provider['name']} failed: {e}")
                    last_error = e
                    if attempts <= MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempts)
                        continue
                    break

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    def _call_llm(
        self,
        provider: dict,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call an OpenAI-compatible chat-completions endpoint (W&B or OpenRouter).

        Minimal payload: only model/messages/temperature/max_tokens. The
        provider rejects extra headers (HTTP-Referer/X-Title) and a models
        fallback chain. OpenRouter additionally opts into usage accounting
        (usage.include) so the exact billed cost (usage.cost, USD) is
        returned in the response body.
        """
        url = f"{provider['base_url']}/chat/completions"

        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": provider["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if provider["name"] == "openrouter":
            payload["usage"] = {"include": True}

        response = requests.post(
            url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            error_detail = data["error"].get("message", "Unknown error")
            raise RuntimeError(f"LLM API error: {error_detail}")

        if not data.get("choices"):
            raise RuntimeError(f"LLM returned empty response: {data}")

        choice = data["choices"][0]
        if not choice.get("message") or not choice["message"].get("content"):
            raise RuntimeError("LLM returned empty message content")

        usage = data.get("usage", {})
        return LLMResponse(
            text=choice["message"]["content"],
            raw_response=data,
            model=data.get("model", provider["model"]),
            finish_reason=choice.get("finish_reason", "STOP"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
        )


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get singleton LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
