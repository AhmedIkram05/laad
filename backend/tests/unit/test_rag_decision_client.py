"""Tests for backend.src.rag.decision_client."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from backend.src.rag.decision_client import (
    CIRCUIT_RESET_SECONDS,
    FALLBACK_ENDPOINT,
    SYSTEMONE_ENDPOINT,
    CircuitOpenError,
    DecisionClient,
    DecisionQuestion,
    JevDecisionClient,
    get_decision_provider,
)

pytestmark = pytest.mark.rag

FIXTURES_DIR = Path(__file__).parent / "fixtures"

TEST_KEY = "test-key-not-a-real-secret"

QUESTIONS: dict[str, DecisionQuestion] = {
    "did_error_recur": DecisionQuestion(
        name="did_error_recur",
        type="noul",
        instructions="Return probability that the error will recur tomorrow",
    ),
    "error_recur_score": DecisionQuestion(
        name="error_recur_score",
        type="score",
        instructions="Score the likelihood the error recurs tomorrow",
        criteria=["unlikely", "possible", "likely"],
    ),
    "best_action": DecisionQuestion(
        name="best_action",
        type="choice",
        instructions="Pick the most likely cause",
        options=["card_reader_fault", "network_outage", "cash_dispenser_jam"],
        criteria={
            "card_reader_fault": "reader hardware failure",
            "network_outage": "upstream connectivity loss",
            "cash_dispenser_jam": "physical cash dispenser jam",
        },
    ),
}


def _load_fixture(filename: str) -> dict:
    return json.loads((FIXTURES_DIR / filename).read_text())


def _ok_response(fixture: dict) -> httpx.Response:
    return httpx.Response(200, json=fixture)


def _make_client(responses: list, **kwargs) -> tuple[JevDecisionClient, MagicMock]:
    """JevDecisionClient backed by a fake httpx.Client with canned responses."""
    fake_client = MagicMock(spec=httpx.Client)
    fake_client.post = MagicMock(side_effect=responses)
    defaults = {
        "api_key": TEST_KEY,
        "client": fake_client,
        "min_call_interval": 0.0,
    }
    defaults.update(kwargs)
    client = JevDecisionClient(**defaults)
    return client, fake_client


def _validation_response(path: list, message: str) -> httpx.Response:
    """422 body matching the observed System One shape."""
    body = {
        "error": {
            "message": json.dumps(
                [
                    {
                        "expected": "array",
                        "code": "invalid_type",
                        "path": path,
                        "message": message,
                    }
                ]
            ),
            "code": 400,
        }
    }
    return httpx.Response(422, json=body)


class TestHappyPath:
    def test_parses_real_fixture_all_answer_types(self):
        fixture = _load_fixture("jev_systemone_response.json")
        client, fake_client = _make_client([_ok_response(fixture)])

        answers = client.decide(
            "The ATM returned error code 51 twice today.", QUESTIONS
        )

        assert set(answers) == {"did_error_recur", "error_recur_score", "best_action"}

        noul = answers["did_error_recur"]
        assert noul.probability == 0.51
        assert noul.confidence == 0.0  # observed noul payload omits confidence
        assert noul.cost_usd == pytest.approx(1.6842e-05)
        assert noul.raw == fixture["answers"]["did_error_recur"]

        score = answers["error_recur_score"]
        assert score.probability == 0.72  # max level probability
        assert score.confidence == 0.57
        assert score.raw["score"] == 1.71  # legend-scale value untouched in raw

        choice = answers["best_action"]
        assert choice.probability == 0.36  # chosen option's probability
        assert choice.confidence == 0.03
        assert choice.raw["choice"] == "cash_dispenser_jam"

    def test_request_shape_pins_model_and_builds_questions(self):
        fixture = _load_fixture("jev_systemone_response.json")
        client, fake_client = _make_client([_ok_response(fixture)])
        state = "The ATM returned error code 51 twice today."

        client.decide(state, QUESTIONS)

        request = fake_client.post.call_args
        assert request.args[0] == SYSTEMONE_ENDPOINT
        assert request.kwargs["headers"]["Authorization"] == f"Bearer {TEST_KEY}"
        body = request.kwargs["json"]
        assert body["model"] == "typesafe/jev-1.13"  # exact pinned id
        assert body["state"] == state  # opaque passthrough, never parsed
        questions = body["questions"]
        assert questions["did_error_recur"] == {
            "type": "noul",
            "instructions": "Return probability that the error will recur tomorrow",
        }
        assert questions["error_recur_score"]["criteria"] == [
            "unlikely",
            "possible",
            "likely",
        ]
        assert questions["best_action"]["options"] == [
            "card_reader_fault",
            "network_outage",
            "cash_dispenser_jam",
        ]
        assert set(questions["best_action"]["criteria"]) == {
            "card_reader_fault",
            "network_outage",
            "cash_dispenser_jam",
        }

    def test_noul_only_fixture(self):
        fixture = _load_fixture("jev_systemone_noul_response.json")
        client, _ = _make_client([_ok_response(fixture)])
        questions = {"did_error_recur": QUESTIONS["did_error_recur"]}

        answers = client.decide("state", questions)

        assert answers["did_error_recur"].probability == 0.5
        assert answers["did_error_recur"].confidence == 0.0
        assert answers["did_error_recur"].cost_usd == pytest.approx(0.00001197)

    def test_unknown_answer_type_keeps_raw_zero_probability(self):
        fixture = {
            "answers": {"odd_q": {"type": "mystery", "value": 9}},
            "usage": {"cost": 0.001},
        }
        client, _ = _make_client([_ok_response(fixture)])

        answers = client.decide("state", {"odd_q": QUESTIONS["did_error_recur"]})

        assert answers["odd_q"].probability == 0.0
        assert answers["odd_q"].raw == {"type": "mystery", "value": 9}
        assert answers["odd_q"].cost_usd == pytest.approx(0.001)

    def test_satisfies_decision_client_protocol(self):
        client, _ = _make_client(
            [_ok_response(_load_fixture("jev_systemone_response.json"))]
        )
        assert isinstance(client, DecisionClient)


class TestRetries:
    def test_429_honors_retry_after_then_succeeds(self):
        fixture = _load_fixture("jev_systemone_response.json")
        responses = [
            httpx.Response(429, headers={"Retry-After": "2"}),
            _ok_response(fixture),
        ]
        client, fake_client = _make_client(responses)
        with patch("backend.src.rag.decision_client.time.sleep") as sleep_mock:
            answers = client.decide("state", QUESTIONS)

        sleep_mock.assert_called_once_with(2.0)
        assert fake_client.post.call_count == 2
        assert set(answers) == set(QUESTIONS)

    def test_429_retries_exhausted_raises(self):
        client, fake_client = _make_client([httpx.Response(429)] * 4)
        with patch("backend.src.rag.decision_client.time.sleep"):
            with pytest.raises(RuntimeError, match="rate limited"):
                client.decide("state", QUESTIONS)
        # Initial attempt + 3 retries, then give up.
        assert fake_client.post.call_count == 4

    def test_529_backoff_sequence_then_succeeds(self):
        fixture = _load_fixture("jev_systemone_response.json")
        responses = [httpx.Response(529), httpx.Response(529), _ok_response(fixture)]
        client, fake_client = _make_client(responses)
        with patch("backend.src.rag.decision_client.time.sleep") as sleep_mock:
            answers = client.decide("state", QUESTIONS)

        assert sleep_mock.call_args_list == [call(0.5), call(1.0)]
        assert fake_client.post.call_count == 3
        assert set(answers) == set(QUESTIONS)

    def test_529_retries_exhausted_raises(self):
        client, fake_client = _make_client([httpx.Response(529)] * 4)
        with patch("backend.src.rag.decision_client.time.sleep"):
            with pytest.raises(RuntimeError, match="overloaded"):
                client.decide("state", QUESTIONS)
        assert fake_client.post.call_count == 4


class TestErrors:
    def test_422_raises_value_error_naming_field(self):
        response = _validation_response(
            ["questions", "q1", "criteria"],
            "Invalid input: expected array, received undefined",
        )
        client, fake_client = _make_client([response])

        with pytest.raises(ValueError, match="questions\\.q1\\.criteria"):
            client.decide("state", QUESTIONS)
        assert fake_client.post.call_count == 1  # 422 is not retried

    def test_422_non_json_body_still_value_error(self):
        client, _ = _make_client([httpx.Response(422, text="plain text error")])
        with pytest.raises(ValueError, match="422"):
            client.decide("state", QUESTIONS)

    def test_401_raises_runtime_error_with_hint_and_no_key(self):
        unauthorized = httpx.Response(401, json={"error": {"message": "bad"}})
        client, _ = _make_client([unauthorized, unauthorized])

        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            client.decide("state", QUESTIONS)

        with pytest.raises(RuntimeError) as excinfo:
            client._post_decisions(
                "state",
                {"q": DecisionQuestion(name="q", type="noul")},
            )
        assert TEST_KEY not in str(excinfo.value)  # never leaks key material

    def test_other_status_raises_with_snippet(self):
        client, _ = _make_client([httpx.Response(500, text="boom\n_Detail_")])
        with pytest.raises(RuntimeError, match="HTTP 500"):
            client.decide("state", QUESTIONS)


class TestEndpointFallback:
    def test_404_falls_back_to_alpha_endpoint(self):
        fixture = _load_fixture("jev_systemone_response.json")
        responses = [httpx.Response(404), _ok_response(fixture)]
        client, fake_client = _make_client(responses)

        answers = client.decide("state", QUESTIONS)

        urls = [c.args[0] for c in fake_client.post.call_args_list]
        assert urls == [SYSTEMONE_ENDPOINT, FALLBACK_ENDPOINT]
        assert set(answers) == set(QUESTIONS)


class TestCircuitBreaker:
    def test_opens_after_five_consecutive_failures(self):
        client, fake_client = _make_client([httpx.Response(500, text="boom")] * 6)

        for _ in range(5):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                client.decide("state", QUESTIONS)
        assert fake_client.post.call_count == 5

        # Circuit now open: rejected before any HTTP call.
        with pytest.raises(CircuitOpenError):
            client.decide("state", QUESTIONS)
        assert fake_client.post.call_count == 5

    def test_success_resets_failure_count(self):
        fixture = _load_fixture("jev_systemone_response.json")
        responses = (
            [httpx.Response(500)] * 4 + [_ok_response(fixture)] + [httpx.Response(500)]
        )
        client, fake_client = _make_client(responses)

        for _ in range(4):
            with pytest.raises(RuntimeError):
                client.decide("state", QUESTIONS)
        assert client.decide("state", QUESTIONS)  # success resets the counter
        with pytest.raises(RuntimeError):
            client.decide("state", QUESTIONS)  # next failure is only #1, not #5
        assert fake_client.post.call_count == 6  # circuit never opened

    def test_recovers_after_circuit_timeout(self):
        responses = [httpx.Response(500, text="boom")] * 5 + [
            _ok_response(_load_fixture("jev_systemone_response.json"))
        ] * 2
        client, fake_client = _make_client(responses)
        for _ in range(5):
            with pytest.raises(RuntimeError):
                client.decide("state", QUESTIONS)
        with pytest.raises(CircuitOpenError):
            client.decide("state", QUESTIONS)

        with patch(
            "backend.src.rag.decision_client.time.monotonic",
            return_value=time.monotonic() + CIRCUIT_RESET_SECONDS + 1,
        ):
            answers = client.decide("state", QUESTIONS)
        assert set(answers) == set(QUESTIONS)
        assert fake_client.post.call_count == 6

        # After recovery the circuit is closed for good (failure counter reset).
        assert client.decide("state", QUESTIONS)


class TestRateLimit:
    def test_min_interval_throttles_second_call(self):
        fixture = _load_fixture("jev_systemone_response.json")
        client, _ = _make_client([_ok_response(fixture)] * 2, min_call_interval=100.0)
        client.decide("state", QUESTIONS)
        client._last_call_ts = time.monotonic()

        with patch("backend.src.rag.decision_client.time.sleep") as sleep_mock:
            client.decide("state", QUESTIONS)

        assert sleep_mock.call_count == 1
        waited = sleep_mock.call_args.args[0]
        assert 0 < waited <= 100.0


class TestGetDecisionProvider:
    def test_default_heuristic_returns_none(self, monkeypatch):
        monkeypatch.delenv("RAG_DECISION_PROVIDER", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        assert get_decision_provider() is None

    def test_llm_provider_returns_none(self, monkeypatch):
        monkeypatch.setenv("RAG_DECISION_PROVIDER", "llm")
        monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
        assert get_decision_provider() is None

    def test_jev_without_key_returns_none(self, monkeypatch):
        monkeypatch.setenv("RAG_DECISION_PROVIDER", "jev")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        assert get_decision_provider() is None

    def test_jev_with_key_returns_client(self, monkeypatch):
        monkeypatch.setenv("RAG_DECISION_PROVIDER", "jev")
        monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
        provider = get_decision_provider()
        assert isinstance(provider, JevDecisionClient)
        assert isinstance(provider, DecisionClient)  # runtime_checkable protocol
        provider._client.close()

    def test_jev_with_legacy_alias_key_returns_client(self, monkeypatch):
        monkeypatch.setenv("RAG_DECISION_PROVIDER", "jev")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("TYPESAFE_API_KEY", TEST_KEY)
        provider = get_decision_provider()
        assert isinstance(provider, JevDecisionClient)
        assert provider._api_key == TEST_KEY  # legacy alias resolved
        provider._client.close()
