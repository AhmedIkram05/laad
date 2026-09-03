"""Unified LLM client for the W&B Serverless Inference provider (single provider)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import requests

from backend.src.rag.config import config

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 20
REQUEST_TIMEOUT = 90
MAX_RETRIES = 2
MAX_RATE_LIMIT_RETRIES = 5
RETRY_DELAY = 2.0


class RateLimiter:
    """Simple in-memory token bucket rate limiter."""

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, key: str = "global") -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if len(self._requests[key]) >= self.max_requests:
            return True
        self._requests[key].append(now)
        return False

    def wait_time(self, key: str = "global") -> float:
        if not self._requests[key]:
            return 0.0
        oldest = min(self._requests[key])
        return max(0.0, (oldest + self.window_seconds) - time.time())


_rate_limiter = RateLimiter(max_requests=config.rate_limit_per_min)


@dataclass
class LLMResponse:
    """Response from LLM with metadata."""

    text: str
    raw_response: dict
    model: str
    finish_reason: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class LLMClient:
    """LLM client for the single W&B Serverless Inference provider."""

    def __init__(self):
        if not config.is_configured:
            logger.warning("LLM client initialized but no API keys configured")
            self.providers = []
        else:
            self.providers = self._initialize_providers()

    def _initialize_providers(self) -> list[dict]:
        """Initialize the single W&B provider (LLM_API_KEY / WANDB_API_KEY)."""
        providers = []

        if config.llm_api_key:
            providers.append(
                {
                    "name": "llm",
                    "model": config.llm_model,
                    "api_key": config.llm_api_key,
                    "base_url": config.llm_base_url,
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
    ) -> LLMResponse:
        """Generate response with automatic retries on failure."""
        if not self.providers:
            raise RuntimeError(
                "No LLM providers configured. Set at least one of LLM_API_KEY or WANDB_API_KEY environment variables."
            )

        if config.rate_limit_per_min > 0 and _rate_limiter.is_rate_limited():
            wait = _rate_limiter.wait_time()
            raise RuntimeError(
                f"Rate limit exceeded. Please wait {wait:.0f}s before retrying."
            )

        last_error = None

        for provider in self.providers:
            rate_limit_retries = 0
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = self._call_llm(
                        provider=provider,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    logger.info(
                        f"Successfully generated response using {provider['name']} (attempt {attempt + 1})"
                    )
                    return response
                except requests.exceptions.Timeout:
                    logger.warning(
                        f"Provider {provider['name']} timed out (attempt {attempt + 1}/{MAX_RETRIES + 1})"
                    )
                    last_error = RuntimeError(
                        f"Request timed out after {REQUEST_TIMEOUT}s"
                    )
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
                    logger.warning(f"Provider {provider['name']} failed: {e}")
                    last_error = e
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * (attempt + 1))
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
        """Call W&B Serverless Inference (strict OpenAI-compatible API).

        Minimal payload: only model/messages/temperature/max_tokens. The
        provider rejects extra headers (HTTP-Referer/X-Title) and a models
        fallback chain.
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

        return LLMResponse(
            text=choice["message"]["content"],
            raw_response=data,
            model=data.get("model", provider["model"]),
            finish_reason=choice.get("finish_reason", "STOP"),
            prompt_tokens=data.get("usage", {}).get("prompt_tokens"),
            completion_tokens=data.get("usage", {}).get("completion_tokens"),
        )


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get singleton LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
