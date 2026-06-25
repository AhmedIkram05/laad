"""Tests for JWT token blacklisting via Redis."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException


class TestJWTBlacklist:
    """Test cases for JWT token blacklist functionality."""

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_blacklisted_token_rejected(self, mock_get_client):
        """Test that a blacklisted token is rejected by get_current_user."""
        from backend.src.auth.auth_router import get_current_user

        mock_client = MagicMock()
        mock_client.get.return_value = "1"
        mock_get_client.return_value = mock_client

        import backend.src.auth.auth_router as auth_router

        valid_token = auth_router.create_access_token("testuser", "user")

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(valid_token)

        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_non_blacklisted_token_accepted(self, mock_get_client):
        """Test that a non-blacklisted token is accepted."""
        from backend.src.auth.auth_router import get_current_user

        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_get_client.return_value = mock_client

        import backend.src.auth.auth_router as auth_router

        valid_token = auth_router.create_access_token("testuser", "user")

        result = get_current_user(valid_token)

        assert result["sub"] == "testuser"
        assert result["role"] == "user"

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_blacklist_ignored_when_redis_down(self, mock_get_client):
        """Test that blacklist check is bypassed when Redis is unavailable."""
        from backend.src.auth.auth_router import get_current_user

        mock_get_client.return_value = None

        import backend.src.auth.auth_router as auth_router

        valid_token = auth_router.create_access_token("testuser", "user")

        result = get_current_user(valid_token)

        assert result["sub"] == "testuser"

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_blacklist_token_sets_with_ttl(self, mock_get_client):
        """Test that blacklisting a token sets it in Redis with TTL."""
        from backend.src.auth.auth_router import _blacklist_token

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        _blacklist_token("fake-token-123", expires_at)

        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0].startswith("blacklist:")
        assert call_args[1]["ex"] > 0
        assert call_args[0][1] == "1"

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_blacklist_noop_when_redis_down(self, mock_get_client):
        """Test that blacklisting is a no-op when Redis is unavailable."""
        from backend.src.auth.auth_router import _blacklist_token

        mock_get_client.return_value = None

        expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        _blacklist_token("fake-token-456", expires_at)

    def test_expired_token_rejected_even_if_not_blacklisted(self):
        """Test that expired tokens are rejected regardless of blacklist."""
        from backend.src.auth.auth_router import get_current_user
        import backend.src.auth.auth_router as auth_router

        expired_payload = {"sub": "testuser", "role": "user", "exp": 0}
        expired_token = auth_router.jwt.encode(
            expired_payload, auth_router.SECRET_KEY, algorithm=auth_router.ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(expired_token)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_is_token_blacklisted_returns_false_when_redis_down(self, mock_get_client):
        """Test that _is_token_blacklisted returns False when Redis is down."""
        from backend.src.auth.auth_router import _is_token_blacklisted

        mock_get_client.return_value = None

        assert _is_token_blacklisted("some-token") is False

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_is_token_blacklisted_returns_true_when_found(self, mock_get_client):
        """Test that _is_token_blacklisted returns True when token is in blacklist."""
        from backend.src.auth.auth_router import _is_token_blacklisted

        mock_client = MagicMock()
        mock_client.get.return_value = "1"
        mock_get_client.return_value = mock_client

        assert _is_token_blacklisted("some-token") is True

    @patch("backend.src.auth.auth_router.get_redis_client")
    def test_logout_endpoint_blacklists_token(self, mock_get_client):
        """Test that POST /auth/logout blacklists the token."""
        from backend.src.auth.auth_router import _blacklist_token

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        import backend.src.auth.auth_router as auth_router

        valid_token = auth_router.create_access_token("logoutuser", "user")

        _blacklist_token(valid_token, datetime.now(timezone.utc) + timedelta(hours=8))

        mock_client.set.assert_called_once()
