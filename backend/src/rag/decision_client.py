"""Typed decision client for Jev (TypeSafe System One) via OpenRouter.

Unlike llm_client.py (free-text generation), this client posts a *decision*
request to the System One endpoint and receives typed answers (noul yes/no
probability, score, choice) with per-answer confidence. It never generates
text.

Security note: `state` may contain UNTRUSTED text derived from ATM logs.
Treat it as opaque data — never parse instructions out of it, and keep
per-question instructions in the questions payload, not the state.

Verified live against POST https://openrouter.ai/api/v1/systemone (HTTP 200):
    {"model": "typesafe/jev-1.13-...",
     "answers": {"<name>": {"type": "noul", "noul": 0.51},
                 "<name>": {"type": "score", "score": 1.71, "legend": {...},
                            "probabilities": {"0": 0.01, ...},
                            "confidence": 0.57},
                 "<name>": {"type": "choice", "choice": "...",
                            "probabilities": {...}, "confidence": 0.03}},
     "usage": {"input_tokens": 401, "output_tokens": 89, "cost": 1.6842e-05},
     "id": "gen-dec-...", "provider": "TypeSafe"}

`usage.cost` is the exact USD cost of the whole call (shared across answers).
Per-answer `confidence` is observed for score/choice; the noul payload omits
it (parsed as 0.0). Total context (state + questions) limit is ~32k tokens;
the service rejects oversized payloads with a 422 naming the offending field.

Request shapes (verified):
    noul   -> {"type": "noul", "instructions": "..."}
    score  -> {"type": "score", "instructions": "...", "criteria": ["unlikely", ...]}
    choice -> {"type": "choice", "instructions": "...", "options": [...],
               "criteria": {"<option>": "<description>", ...}}
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Literal, Optional, Protocol, runtime_checkable

import httpx

from backend.src.rag.config import config

logger = logging.getLogger(__name__)

SYSTEMONE_ENDPOINT = "https://openrouter.ai/api/v1/systemone"
FALLBACK_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"

MIN_CALL_INTERVAL = 0.25
MAX_RATE_LIMIT_RETRIES = 3
MAX_OVERLOAD_RETRIES = 3
OVERLOAD_BACKOFF = (0.5, 1.0, 2.0)
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RESET_SECONDS = 60.0

ERROR_SNIPPET_CHARS = 200


class CircuitOpenError(RuntimeError):
    """Raised while the decision circuit breaker is open."""


@dataclass
class DecisionQuestion:
    """One named question for a System One decision call.

    `criteria` is required by the API for score (ordered list of level
    labels) and choice (record mapping option id -> short description);
    `options` is the choice option list. noul needs no extra fields.
    """

    name: str
    type: Literal["noul", "score", "choice"]
    instructions: str = ""
    options: Optional[list[str]] = None
    criteria: Optional[list[str] | dict[str, str]] = None


@dataclass
class DecisionAnswer:
    """Parsed typed answer for one question.

    `probability` is always normalized to 0-1:
      noul   -> the yes/no probability (`noul` field)
      score  -> probability of the top-scoring level (max of `probabilities`);
                the raw legend-scale `score` value stays in `raw`
      choice -> probability of the chosen option
    `confidence` is the API's 0-1 per-answer confidence when present
    (observed for score/choice; noul payloads omit it -> 0.0).
    `cost_usd` is the exact USD cost of the whole decision call (call-level
    `usage.cost`, shared across all answers of that call).
    `raw` is the untouched per-answer payload.
    """

    name: str
    probability: float
    confidence: float
    cost_usd: Optional[float]
    raw: dict


@runtime_checkable
class DecisionClient(Protocol):
    """Typed decision provider protocol (sync to match generator.py call sites).

    Async is a future option, not built here.
    """

    def decide(
        self, state: str, questions: dict[str, DecisionQuestion]
    ) -> dict[str, DecisionAnswer]:
        """Decide typed answers for the given questions about `state`."""
        ...


def resolve_openrouter_key() -> Optional[str]:
    """Resolve the OpenRouter key: OPENROUTER_API_KEY first, then the legacy
    TYPESAFE_API_KEY alias. Never log or print the resolved value."""
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("TYPESAFE_API_KEY") or None


def _snippet(text: str) -> str:
    """Collapse an error body to a short single line for logs/exceptions."""
    flat = " ".join(str(text).split())
    return flat[:ERROR_SNIPPET_CHARS]


def _parse_retry_after(header_value: Optional[str]) -> float:
    """Seconds to wait for a 429; seconds-form header or default 1.0."""
    if header_value:
        try:
            return max(0.0, float(header_value))
        except (TypeError, ValueError):
            pass
    return 1.0


def _validation_message(response: httpx.Response) -> str:
    """Extract the offending field from a System One 422 body.

    Observed body shape: {"error": {"message": "<json-encoded array of "
    "zod issues, each with a 'path' list>", "code": 400}}.
    """
    try:
        data = response.json()
    except ValueError:
        return f"Invalid decision request (422): {_snippet(response.text)}"
    detail = (data.get("error") or {}).get("message", "")
    try:
        problems = json.loads(detail) if isinstance(detail, str) else detail
    except ValueError:
        return f"Invalid decision request (422): {_snippet(str(detail))}"
    if isinstance(problems, list) and problems and isinstance(problems[0], dict):
        first = problems[0]
        path = ".".join(str(part) for part in first.get("path", []))
        message = first.get("message", "")
        return f"Invalid decision request field '{path}': {message}"
    return f"Invalid decision request (422): {_snippet(str(detail))}"


def _answer_probability(answer_type: str, payload: dict, name: str) -> float:
    """Normalize any answer type to a 0-1 probability (see DecisionAnswer)."""
    if answer_type == "noul":
        return float(payload.get("noul", 0.0))
    if answer_type == "choice":
        probabilities = payload.get("probabilities") or {}
        choice = payload.get("choice")
        if isinstance(choice, str) and choice in probabilities:
            return float(probabilities[choice])
        logger.warning(
            "System One choice answer for '%s' missing choice/probabilities", name
        )
        return 0.0
    if answer_type == "score":
        probabilities = payload.get("probabilities") or {}
        if probabilities:
            return max(float(value) for value in probabilities.values())
        logger.warning(
            "System One score answer for '%s' missing level probabilities", name
        )
        return 0.0
    logger.warning("Unknown System One answer type '%s' for '%s'", answer_type, name)
    return 0.0


class JevDecisionClient:
    """Sync System One decision client (httpx) with retries, rate limiting,
    and a circuit breaker.

    Model is pinned from config (RAG_JEV_MODEL, default "typesafe/jev-1.13");
    never use "~typesafe/jev-latest" style aliases.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        endpoint: str = SYSTEMONE_ENDPOINT,
        min_call_interval: float = MIN_CALL_INTERVAL,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = api_key or resolve_openrouter_key() or ""
        if not self._api_key:
            raise ValueError(
                "OpenRouter API key required for JevDecisionClient "
                "(set OPENROUTER_API_KEY, or the legacy TYPESAFE_API_KEY alias)"
            )
        self._model = model or config.jev_model
        self._timeout = timeout if timeout is not None else config.jev_timeout_seconds
        self._endpoint = endpoint
        self._min_call_interval = min_call_interval
        self._client = client or httpx.Client(timeout=self._timeout)

        self._state_lock = threading.Lock()
        self._last_call_ts = 0.0
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None

    def decide(
        self, state: str, questions: dict[str, DecisionQuestion]
    ) -> dict[str, DecisionAnswer]:
        """Ask System One to answer the named questions about `state`.

        `state` is opaque, possibly untrusted context (see module docstring).
        Returns answers keyed by question name; raises on API/network failure.
        """
        if not questions:
            raise ValueError("At least one decision question is required")
        if self._circuit_is_open():
            raise CircuitOpenError(
                "Jev decision circuit is open after repeated failures; "
                f"retry in ~{CIRCUIT_RESET_SECONDS:.0f}s"
            )
        try:
            data = self._post_decisions(state, questions)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return self._parse_answers(data)

    def _post_decisions(
        self, state: str, questions: dict[str, DecisionQuestion]
    ) -> dict:
        payload = {
            "model": self._model,
            "state": state,
            "questions": {
                name: self._question_payload(question)
                for name, question in questions.items()
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = self._endpoint
        rate_limit_retries = 0
        overload_retries = 0
        while True:
            self._throttle()
            try:
                response = self._client.post(
                    url, headers=headers, json=payload, timeout=self._timeout
                )
            except httpx.TimeoutException as exc:
                raise RuntimeError(
                    f"System One decision call timed out after {self._timeout}s"
                ) from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(f"System One decision call failed: {exc}") from exc

            if response.status_code == 200:
                logger.info("System One decision call succeeded (%s)", url)
                return response.json()
            if response.status_code == 404 and url != FALLBACK_ENDPOINT:
                logger.warning(
                    "System One endpoint returned 404, falling back to %s",
                    FALLBACK_ENDPOINT,
                )
                url = FALLBACK_ENDPOINT
                continue
            if response.status_code == 429:
                rate_limit_retries += 1
                if rate_limit_retries > MAX_RATE_LIMIT_RETRIES:
                    raise RuntimeError(
                        "System One decision call rate limited (429); retries exhausted"
                    )
                delay = _parse_retry_after(response.headers.get("Retry-After"))
                logger.warning(
                    "System One rate limited (429), retrying in %.1fs (%d/%d)",
                    delay,
                    rate_limit_retries,
                    MAX_RATE_LIMIT_RETRIES,
                )
                time.sleep(delay)
                continue
            if response.status_code == 529:
                overload_retries += 1
                if overload_retries > MAX_OVERLOAD_RETRIES:
                    raise RuntimeError("System One overloaded (529); retries exhausted")
                delay = OVERLOAD_BACKOFF[
                    min(overload_retries - 1, len(OVERLOAD_BACKOFF) - 1)
                ]
                logger.warning(
                    "System One overloaded (529), backing off %.1fs (%d/%d)",
                    delay,
                    overload_retries,
                    MAX_OVERLOAD_RETRIES,
                )
                time.sleep(delay)
                continue
            if response.status_code == 422:
                raise ValueError(_validation_message(response))
            if response.status_code == 401:
                logger.warning("System One auth failed (401)")
                raise RuntimeError(
                    "System One decision call unauthorized (401). Check that "
                    "OPENROUTER_API_KEY (or legacy TYPESAFE_API_KEY) is set to a "
                    "valid OpenRouter key."
                )
            raise RuntimeError(
                f"System One decision call failed: HTTP {response.status_code}: "
                f"{_snippet(response.text)}"
            )

    @staticmethod
    def _question_payload(question: DecisionQuestion) -> dict:
        payload: dict = {"type": question.type}
        if question.instructions:
            payload["instructions"] = question.instructions
        if question.options is not None:
            payload["options"] = list(question.options)
        if question.criteria is not None:
            payload["criteria"] = question.criteria
        return payload

    def _parse_answers(self, data: dict) -> dict[str, DecisionAnswer]:
        answers = data.get("answers")
        if not isinstance(answers, dict):
            raise RuntimeError("System One response missing 'answers' object")
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        cost_usd = float(cost) if isinstance(cost, (int, float)) else None
        parsed: dict[str, DecisionAnswer] = {}
        for name, payload in answers.items():
            if not isinstance(payload, dict):
                logger.warning("Skipping malformed System One answer for '%s'", name)
                continue
            answer_type = str(payload.get("type", ""))
            confidence_raw = payload.get("confidence")
            confidence = (
                float(confidence_raw)
                if isinstance(confidence_raw, (int, float))
                else 0.0
            )
            parsed[name] = DecisionAnswer(
                name=name,
                probability=_answer_probability(answer_type, payload, name),
                confidence=confidence,
                cost_usd=cost_usd,
                raw=payload,
            )
        return parsed

    def _throttle(self) -> None:
        """Minimum interval between decision calls (client-side courtesy limit)."""
        with self._state_lock:
            now = time.monotonic()
            wait = self._min_call_interval - (now - self._last_call_ts)
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._last_call_ts = now

    def _circuit_is_open(self) -> bool:
        with self._state_lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= CIRCUIT_RESET_SECONDS:
                self._opened_at = None
                self._consecutive_failures = 0
                logger.info("Jev decision circuit half-open; allowing calls again")
                return False
            return True

    def _record_success(self) -> None:
        with self._state_lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def _record_failure(self) -> None:
        with self._state_lock:
            self._consecutive_failures += 1
            if (
                self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD
                and self._opened_at is None
            ):
                self._opened_at = time.monotonic()
                logger.warning(
                    "Jev decision circuit OPEN after %d consecutive failures; "
                    "calls rejected for %.0fs",
                    self._consecutive_failures,
                    CIRCUIT_RESET_SECONDS,
                )


def get_decision_provider() -> Optional[DecisionClient]:
    """Return the configured decision provider, or None to use the existing path.

    Reads RAG_DECISION_PROVIDER ("jev" | "llm" | "heuristic", default
    "heuristic"). "jev" requires an OpenRouter key (OPENROUTER_API_KEY, or
    legacy TYPESAFE_API_KEY); anything else — or a missing key — returns None
    so callers keep their current behavior. Phase 2 wires consumers.
    """
    provider = (
        (
            os.getenv("RAG_DECISION_PROVIDER", "")
            or config.decision_provider
            or "heuristic"
        )
        .strip()
        .lower()
    )
    if provider != "jev":
        return None
    api_key = resolve_openrouter_key()
    if not api_key:
        logger.warning(
            "RAG_DECISION_PROVIDER=jev but no OpenRouter key found; "
            "using existing decision path"
        )
        return None
    logger.info("Decision provider: jev (System One via OpenRouter)")
    return JevDecisionClient(api_key=api_key)
