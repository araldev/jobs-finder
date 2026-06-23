"""Supabase HS256 JWT verification.

Shared infrastructure — consumed by JWTUserMiddleware (presentation) and
by SupabaseEngagementRepository for service-level auth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserState:
    """Represents an authenticated user extracted from a verified JWT.

    Attributes:
        user_id: The Supabase user's UUID (the ``sub`` claim).
        email: The user's email (the ``email`` claim), or None if absent.
    """

    user_id: str
    email: str | None = None


def verify_supabase_jwt(
    token: str | None,
    secret: str,
    *,
    audience: str = "authenticated",
) -> UserState | None:
    """Verify a Supabase-issued HS256 JWT and return the embedded user info.

    Best-effort contract: returns ``None`` on ANY failure (expired token,
    wrong secret, malformed payload, unexpected exception). Never raises.

    Args:
        token: The raw JWT string (from ``Authorization: Bearer <token>``).
        secret: The HS256 secret (``SUPABASE_JWT_SECRET``).
        audience: Expected ``aud`` claim (default ``"authenticated"``).

    Returns:
        :class:`UserState` on success, ``None`` on any verification failure.
    """
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=audience,
            options={"require": ["sub", "exp", "iat", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        _logger.debug("JWT verification failed: token expired")
        return None
    except jwt.InvalidTokenError:
        _logger.debug("JWT verification failed: invalid token")
        return None
    except Exception:
        _logger.warning("JWT verification failed with unexpected error", exc_info=True)
        return None

    return UserState(
        user_id=str(payload["sub"]),
        email=str(payload["email"]) if payload.get("email") else None,
    )
