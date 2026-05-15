"""Unified LLM client with fallback routing for multiple providers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

from backend.src.rag.config import config

logger = logging.getLogger(__name__)


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
    """Unified LLM client with fallback routing."""

    def __init__(self):
        if not config.is_configured:
            logger.warning("LLM client initialized but no API keys configured")
            self.providers = []
        else:
            self.providers = self._initialize_providers()

    def _initialize_providers(self) -> list[dict]:
        """Initialize available providers in priority order."""
        providers = []

        if config.gemini_api_key:
            providers.append({
                "name": "gemini",
                "model": config.primary_model,
                "api_key": config.gemini_api_key,
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
            })

        if config.groq_api_key:
            fallback = config.fallback_model
            if fallback.startswith("groq/"):
                fallback = fallback.replace("groq/", "")
            providers.append({
                "name": "groq",
                "model": fallback,
                "api_key": config.groq_api_key,
                "base_url": "https://api.groq.com/openai/v1",
            })

        if config.openrouter_api_key:
            fallback = config.fallback_model
            if fallback.startswith("openrouter/"):
                fallback = fallback.replace("openrouter/", "")
            elif fallback.startswith("groq/"):
                fallback = fallback.replace("groq/", "")
            providers.append({
                "name": "openrouter",
                "model": fallback,
                "api_key": config.openrouter_api_key,
                "base_url": "https://openrouter.ai/api/v1",
            })

        if not providers:
            logger.warning("No LLM providers available - RAG will return error messages")

        logger.info(f"Initialized {len(providers) if providers else 0} LLM providers: {[p['name'] for p in providers] if providers else []}")
        return providers

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = config.temperature,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate response with automatic fallback to next provider on failure."""
        if not self.providers:
            raise RuntimeError("No LLM providers configured. Set GEMINI_API_KEY environment variable.")

        last_error = None

        for provider in self.providers:
            try:
                response = self._call_provider(
                    provider=provider,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                logger.info(f"Successfully generated response using {provider['name']}")
                return response
            except Exception as e:
                logger.warning(f"Provider {provider['name']} failed: {e}")
                last_error = e
                time.sleep(0.5)
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    def _call_provider(
        self,
        provider: dict,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call a specific LLM provider."""
        provider_name = provider["name"]

        if provider_name == "gemini":
            return self._call_gemini(provider, prompt, system_prompt, temperature, max_tokens)
        elif provider_name == "groq":
            return self._call_groq(provider, prompt, system_prompt, temperature, max_tokens)
        elif provider_name == "openrouter":
            return self._call_openrouter(provider, prompt, system_prompt, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def _call_gemini(
        self,
        provider: dict,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call Google Gemini API."""
        url = f"{provider['base_url']}/models/{provider['model']}:generateContent"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": provider["api_key"],
        }

        contents = []
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                "topK": 40,
            },
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        data = response.json()

        text = ""
        finish_reason = "STOP"
        if "candidates" in data and data["candidates"]:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                text = candidate["content"]["parts"][0].get("text", "")
            finish_reason = candidate.get("finishReason", "STOP")

        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            raw_response=data,
            model=provider["model"],
            finish_reason=finish_reason,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
        )

    def _call_groq(
        self,
        provider: dict,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call Groq API (OpenAI-compatible)."""
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

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"],
            raw_response=data,
            model=provider["model"],
            finish_reason=choice.get("finish_reason", "STOP"),
            prompt_tokens=data.get("usage", {}).get("prompt_tokens"),
            completion_tokens=data.get("usage", {}).get("completion_tokens"),
        )

    def _call_openrouter(
        self,
        provider: dict,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call OpenRouter API (OpenAI-compatible)."""
        url = f"{provider['base_url']}/chat/completions"

        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://laad.local",
            "X-Title": "LAAD ATM Diagnostic Assistant",
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

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"],
            raw_response=data,
            model=provider["model"],
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