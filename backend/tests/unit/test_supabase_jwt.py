"""Unit tests for the Supabase JWT verifier (tasks 5.1 / 2.4).

Strict TDD: these tests were written BEFORE the production code.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import jwt

from jobs_finder.application.ports import EngagementPort
from jobs_finder.infrastructure.auth._jwt import (
    UserState,
    verify_supabase_jwt,
)

# PyJWT >= 2.13 warns on keys shorter than 32 bytes for HS256.
# Use a 64-char hex key to keep the test suite warning-free.
_VALID_SECRET = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
_OTHER_SECRET = "f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1"
_INVALID_SECRET = "not-32-bytes"  # intentionally short for error-path test


class TestVerifySupabaseJWT:
    """Tests for `verify_supabase_jwt()` — the HS256 JWT verifier.

    Spec scenarios (JWT-001):
      - GIVEN valid JWT WHEN verify THEN extract user_id + email
      - GIVEN expired JWT WHEN verify THEN return None (best-effort)
      - GIVEN wrong secret WHEN verify THEN return None
      - GIVEN missing / malformed token WHEN verify THEN return None
    """

    def _make_token(
        self,
        *,
        secret: str = _VALID_SECRET,
        sub: str = "user-abc-123",
        email: str = "test@example.com",
        exp_offset: float = 3600.0,
        algorithm: str = "HS256",
    ) -> str:
        """Helper: encode a JWT with the given params."""
        payload: dict[str, object] = {
            "sub": sub,
            "email": email,
            "iat": int(time.time()),
            "exp": int(time.time()) + int(exp_offset),
            "aud": "authenticated",
        }
        return jwt.encode(payload, secret, algorithm=algorithm)

    def test_valid_jwt_returns_user_state(self) -> None:
        """GIVEN valid HS256 JWT WHEN verify THEN UserState with user_id + email."""
        token = self._make_token()
        result = verify_supabase_jwt(token, secret=_VALID_SECRET)
        assert isinstance(result, UserState)
        assert result.user_id == "user-abc-123"
        assert result.email == "test@example.com"

    def test_valid_jwt_without_email(self) -> None:
        """GIVEN valid JWT without email WHEN verify THEN user_id set, email=None."""
        payload: dict[str, object] = {
            "sub": "user-no-email",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
        }
        token = jwt.encode(payload, _VALID_SECRET, algorithm="HS256")
        result = verify_supabase_jwt(token, secret=_VALID_SECRET)
        assert isinstance(result, UserState)
        assert result.user_id == "user-no-email"
        assert result.email is None

    def test_expired_jwt_returns_none(self) -> None:
        """GIVEN expired JWT WHEN verify THEN return None (best-effort)."""
        token = self._make_token(exp_offset=-3600)  # expired 1h ago
        result = verify_supabase_jwt(token, secret=_VALID_SECRET)
        assert result is None

    def test_wrong_secret_returns_none(self) -> None:
        """GIVEN JWT signed with different secret WHEN verify THEN return None."""
        token = self._make_token(secret=_OTHER_SECRET)
        result = verify_supabase_jwt(token, secret=_VALID_SECRET)
        assert result is None

    def test_empty_token_returns_none(self) -> None:
        """GIVEN empty/missing token WHEN verify THEN return None."""
        result = verify_supabase_jwt("", secret=_VALID_SECRET)
        assert result is None

    def test_malformed_token_returns_none(self) -> None:
        """GIVEN malformed token string WHEN verify THEN return None."""
        result = verify_supabase_jwt("not.a.token", secret=_VALID_SECRET)
        assert result is None

    def test_wrong_algorithm_returns_none(self) -> None:
        """GIVEN token with different algorithm WHEN verify THEN return None."""
        token = self._make_token(algorithm="HS512", secret=_VALID_SECRET)
        result = verify_supabase_jwt(token, secret=_VALID_SECRET)
        assert result is None

    def test_none_token_returns_none(self) -> None:
        """GIVEN None token WHEN verify THEN return None."""
        result = verify_supabase_jwt(None, secret=_VALID_SECRET)  # type: ignore[arg-type]
        assert result is None

    def test_jwt_decode_raises_unexpected_error(self) -> None:
        """GIVEN PyJWT raises unexpected error WHEN verify THEN return None
        (never crash — best-effort contract)."""
        token = self._make_token()
        with patch("jwt.decode", side_effect=RuntimeError("unexpected")):
            result = verify_supabase_jwt(token, secret=_VALID_SECRET)
        assert result is None


class TestEngagementPortProtocol:
    """Verify EngagementPort Protocol is structurally sound (ENG-001)."""

    def test_protocol_has_required_methods(self) -> None:
        """GIVEN EngagementPort Protocol THEN it has record_event and count_events_today."""
        methods = [m for m in dir(EngagementPort) if not m.startswith("_")]
        assert "record_event" in methods
        assert "count_events_today" in methods
