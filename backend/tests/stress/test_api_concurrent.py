"""API Concurrent Stress Tests — validates behaviour under concurrent load.

Uses httpx.Client against the running server (localhost:8000) instead of
TestClient, because TestClient creates a new ASGI lifespan per instance which
conflicts with the APScheduler background jobs.

Tests cover:
  1. Health endpoints under concurrent load
  2. Authentication under concurrent login attempts
  3. Anomalies listing with concurrent authenticated requests
"""
from __future__ import annotations
import threading

import httpx

BASE_URL = "http://localhost:8000"
CONCURRENT_USERS = 10
REQUEST_TIMEOUT = 10.0


class TestConcurrentHealth:
    """3 tests: concurrent access to health, auth, and data endpoints."""

    def test_concurrent_health_checks(self):
        """10 concurrent health checks must all succeed."""
        results = [None] * CONCURRENT_USERS

        def _get_health(idx):
            with httpx.Client(base_url=BASE_URL, timeout=REQUEST_TIMEOUT) as c:
                resp = c.get("/health")
                results[idx] = resp.status_code

        threads = [
            threading.Thread(target=_get_health, args=(i,))
            for i in range(CONCURRENT_USERS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=REQUEST_TIMEOUT)

        for idx, status in enumerate(results):
            assert status == 200, f"Health check {idx} returned {status}"

    def test_concurrent_login(self):
        """10 concurrent login requests must all succeed without 5xx errors."""
        results = [None] * CONCURRENT_USERS

        def _login(idx):
            try:
                with httpx.Client(base_url=BASE_URL, timeout=REQUEST_TIMEOUT) as c:
                    resp = c.post(
                        "/auth/login",
                        data={"username": "admin", "password": "admin"},
                    )
                    results[idx] = resp.status_code
            except Exception as e:
                results[idx] = f"error: {e}"

        threads = [
            threading.Thread(target=_login, args=(i,))
            for i in range(CONCURRENT_USERS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=REQUEST_TIMEOUT)

        successes = sum(1 for s in results if s == 200)
        for idx, status in enumerate(results):
            assert isinstance(status, int) and status < 500, (
                f"Login request {idx} returned {status}"
            )
        assert successes >= CONCURRENT_USERS // 2, (
            f"Only {successes}/{CONCURRENT_USERS} concurrent logins succeeded"
        )

    def test_concurrent_anomalies_listing(self):
        """10 concurrent authenticated anomalies listing requests."""
        # Get a single token first
        with httpx.Client(base_url=BASE_URL, timeout=REQUEST_TIMEOUT) as c:
            login_resp = c.post(
                "/auth/login", data={"username": "admin", "password": "admin"}
            )
            assert login_resp.status_code == 200
            token = login_resp.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        results = [None] * CONCURRENT_USERS

        def _get_anomalies(idx):
            try:
                with httpx.Client(base_url=BASE_URL, timeout=REQUEST_TIMEOUT) as c:
                    resp = c.get("/anomalies", headers=headers)
                    results[idx] = resp.status_code
            except Exception as e:
                results[idx] = f"error: {e}"

        threads = [
            threading.Thread(target=_get_anomalies, args=(i,))
            for i in range(CONCURRENT_USERS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=REQUEST_TIMEOUT)

        for idx, status in enumerate(results):
            assert status == 200, f"Anomalies listing {idx} returned {status}"
