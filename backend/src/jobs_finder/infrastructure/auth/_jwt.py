"""Supabase ES256 JWT verification via JWKS.

Shared infrastructure — consumed by `JWTUserMiddleware` (presentation layer)
to attach the authenticated user to `request.state.current_user`.

## Why ES256 (asymmetric) and not HS256 (symmetric)?

Supabase's recommended path in 2024+ is "JWT Signing Keys" with asymmetric
algorithms (ES256 by default). The legacy HS256 shared secret path is
deprecated for new projects. This module verifies JWTs against the
**public key** fetched from Supabase's JWKS endpoint — the **private
key** never leaves Supabase, and key rotation is automatic (the JWKS
client fetches the latest `kid` on every verification).

This is the secure choice when:
- The HS256 shared secret might leak (e.g. via `.env` backups, logs, etc.)
  — with ES256, leaking the public key is harmless; the private key
  stays server-side at Supabase.
- Supabase rotates the signing key periodically — `PyJWKClient` handles
  this transparently via the `kid` (Key ID) header on each JWT.

## Caching

`PyJWKClient` is created per `jwks_url` and cached for the process
lifetime. The client itself caches signing keys in-memory for the
configured `lifespan` (1 hour by default), so repeated verifications
don't hit the JWKS endpoint on every request.

## Failure mode

Best-effort contract — returns `None` on ANY failure (expired token,
wrong signature, malformed payload, JWKS unreachable). NEVER raises.
The caller (`JWTUserMiddleware`) treats `None` as "anonymous request"
and continues without blocking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

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


# Cache `PyJWKClient` instances per JWKS URL so we don't re-create the
# HTTP client on every request. `PyJWKClient` already caches signing
# keys internally (`cache_keys=True`, default 1-hour TTL).
_jwks_client_cache: dict[str, PyJWKClient] = {}


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Get or create a cached `PyJWKClient` for the given JWKS URL.

    The client is cached for the process lifetime. The internal signing
    key cache (1-hour default) is managed by `PyJWKClient` itself.
    """
    cached = _jwks_client_cache.get(jwks_url)
    if cached is not None:
        return cached
    client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    _jwks_client_cache[jwks_url] = client
    return client


def _reset_jwks_client_cache_for_tests() -> None:
    """Clear the JWKS client cache. Test-only hook."""
    _jwks_client_cache.clear()


def verify_supabase_jwt(
    token: str | None,
    jwks_url: str | None,
    *,
    audience: str = "authenticated",
) -> UserState | None:
    """Verify a Supabase-issued ES256 JWT via JWKS and return the embedded user info.

    Best-effort contract: returns ``None`` on ANY failure (expired token,
    wrong signature, malformed payload, JWKS unreachable, no `kid`).
    Never raises.

    Args:
        token: The raw JWT string (from ``Authorization: Bearer <token>``).
            ``None``/empty short-circuits to ``None``.
        jwks_url: The Supabase JWKS URL
            (e.g. ``https://<project>.supabase.co/auth/v1/.well-known/jwks.json``).
            ``None``/empty short-circuits to ``None`` (auth disabled).
        audience: Expected ``aud`` claim (default ``"authenticated"``,
            matching Supabase's default for user JWTs).

    Returns:
        :class:`UserState` on success, ``None`` on any verification failure.
    """
    if not token or not jwks_url:
        return None

    try:
        client = _get_jwks_client(jwks_url)
        # `get_signing_key_from_jwt` reads the `kid` header from the JWT,
        # fetches the matching key from the JWKS (cached for 1 hour),
        # and returns a `PyJWK` whose `.key` attribute is the public key.
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            # ES256 is Supabase's default for new signing keys.
            # RS256 is supported as a fallback (also asymmetric, Supabase
            # supports both). HS256 is intentionally NOT listed — see
            # the module docstring for why we moved to asymmetric.
            algorithms=["ES256", "RS256"],
            audience=audience,
            options={"require": ["sub", "exp", "iat", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        _logger.debug("JWT verification failed: token expired")
        return None
    except jwt.InvalidTokenError as exc:
        _logger.debug("JWT verification failed: %s", exc)
        return None
    except PyJWKClientError as exc:
        # JWKS endpoint unreachable / 404 / 500 / etc. Logged at WARNING
        # (not DEBUG) because it indicates a real outage.
        _logger.warning("JWT verification failed: JWKS unreachable: %s", exc)
        return None
    except Exception:
        _logger.warning(
            "JWT verification failed with unexpected error", exc_info=True
        )
        return None

    email = payload.get("email")
    return UserState(
        user_id=str(payload["sub"]),
        email=str(email) if email else None,
    )
