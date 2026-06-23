"""Tests for `verify_supabase_jwt()` — the ES256+JWKS verifier.

Uses a locally-generated EC keypair (no live Supabase, no network).
The test monkey-patches the JWKS client to return the matching
public key for our test tokens.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from jobs_finder.infrastructure.auth import _jwt as jwt_module
from jobs_finder.infrastructure.auth._jwt import (
    UserState,
    _reset_jwks_client_cache_for_tests,
    verify_supabase_jwt,
)
from jobs_finder.infrastructure.auth._jwt import (
    _get_jwks_client as _real_get_jwks_client,
)

# Captured at import time, BEFORE the autouse `_patch_jwks_client`
# fixture runs. Used by `TestJWKSClientCache` to exercise the REAL
# `_get_jwks_client` (which uses the cached PyJWKClient instances).
_REAL_GET_JWKS_CLIENT = _real_get_jwks_client

# ---------------------------------------------------------------------------
# Test fixtures: ES256 keypair + monkey-patched JWKS client
# ---------------------------------------------------------------------------

# Generated once per test session (slow keygen). Each test creates a new
# PyJWK stub pointing at the SAME public key — so any token signed with
# the private key verifies regardless of which test signed it.
@pytest.fixture(scope="session")
def _ec_keypair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def private_key(_ec_keypair: tuple[Any, Any]) -> Any:
    return _ec_keypair[0]


@pytest.fixture
def public_key(_ec_keypair: tuple[Any, Any]) -> Any:
    return _ec_keypair[1]


@pytest.fixture
def jwks_url() -> str:
    return "https://test.supabase.co/auth/v1/.well-known/jwks.json"


@pytest.fixture(autouse=True)
def _clear_jwks_cache() -> None:
    """Ensure each test starts with a fresh JWKS cache."""
    _reset_jwks_client_cache_for_tests()


class _FakeSigningKey:
    """Stand-in for `jwt.PyJWK` — just needs a `.key` attribute."""

    def __init__(self, key: Any) -> None:
        self.key = key


class _FakeJWKSClient:
    """Stand-in for `jwt.PyJWKClient` — returns the test public key."""

    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:  # noqa: ARG002
        return _FakeSigningKey(self._public_key)


@pytest.fixture(autouse=True)
def _patch_jwks_client(monkeypatch: pytest.MonkeyPatch, public_key: Any) -> None:
    """Patch `_get_jwks_client` to return a stub that yields our test public key.

    This isolates the verifier from the real Supabase JWKS endpoint —
    tests run offline and deterministic.
    """
    monkeypatch.setattr(
        jwt_module,
        "_get_jwks_client",
        lambda _url: _FakeJWKSClient(public_key),
    )


def _sign_token(
    private_key: Any,
    *,
    sub: str = "user-abc-123",
    email: str = "test@example.com",
    aud: str = "authenticated",
    exp_offset: int = 3600,
    iat_offset: int = 0,
) -> str:
    """Sign an ES256 JWT with the given private key."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "iat": now + iat_offset,
        "exp": now + exp_offset,
        "aud": aud,
    }
    # PyJWT accepts a cryptography EC private key directly for ES256 signing.
    return jwt.encode(payload, private_key, algorithm="ES256")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestVerifySupabaseJWT:
    def test_valid_jwt_returns_user_state(
        self, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN valid JWT WHEN verify_supabase_jwt THEN returns UserState."""
        token = _sign_token(private_key)
        result = verify_supabase_jwt(token, jwks_url=jwks_url)
        assert isinstance(result, UserState)
        assert result.user_id == "user-abc-123"
        assert result.email == "test@example.com"

    def test_valid_jwt_without_email(
        self, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN JWT without email claim WHEN verify THEN email is None."""
        token = _sign_token(private_key, email="")  # empty string → falsy
        result = verify_supabase_jwt(token, jwks_url=jwks_url)
        assert result is not None
        assert result.user_id == "user-abc-123"
        assert result.email is None

    def test_expired_jwt_returns_none(
        self, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN expired JWT WHEN verify THEN returns None."""
        # exp 1 hour in the past
        token = _sign_token(private_key, exp_offset=-3600)
        result = verify_supabase_jwt(token, jwks_url=jwks_url)
        assert result is None

    def test_wrong_audience_returns_none(
        self, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN JWT with wrong audience WHEN verify THEN returns None."""
        token = _sign_token(private_key, aud="anon")
        result = verify_supabase_jwt(token, jwks_url=jwks_url)
        assert result is None

    def test_empty_token_returns_none(self, jwks_url: str) -> None:
        """GIVEN empty token WHEN verify THEN returns None."""
        assert verify_supabase_jwt("", jwks_url=jwks_url) is None
        assert verify_supabase_jwt(None, jwks_url=jwks_url) is None

    def test_malformed_token_returns_none(self, jwks_url: str) -> None:
        """GIVEN malformed JWT string WHEN verify THEN returns None."""
        assert verify_supabase_jwt("not.a.token", jwks_url=jwks_url) is None
        assert verify_supabase_jwt("garbage", jwks_url=jwks_url) is None

    def test_jwt_signed_with_different_key_returns_none(
        self, jwks_url: str
    ) -> None:
        """GIVEN JWT signed with a different ES256 key WHEN verify THEN None.

        The signature won't match the public key the JWKS stub returns,
        so verification fails. Confirms the verifier actually checks
        signatures (not just claim shape).
        """
        other_private = ec.generate_private_key(ec.SECP256R1())
        token = _sign_token(other_private)
        # The patched JWKS client returns `public_key` (the fixture),
        # not the public key matching `other_private`.
        result = verify_supabase_jwt(token, jwks_url=jwks_url)
        assert result is None

    def test_missing_required_claim_returns_none(
        self, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN JWT missing required claim (e.g. `sub`) WHEN verify THEN None."""
        # Sign manually without `sub` — PyJWT doesn't enforce required claims,
        # so we need to pass options={"verify_claims": True} (default) and
        # a custom payload missing `sub`.
        token = jwt.encode(
            {
                "email": "test@example.com",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "aud": "authenticated",
                # no `sub`
            },
            private_key,
            algorithm="ES256",
        )
        assert verify_supabase_jwt(token, jwks_url=jwks_url) is None

    def test_empty_jwks_url_returns_none(self, private_key: Any) -> None:
        """GIVEN empty jwks_url WHEN verify THEN returns None (auth disabled)."""
        token = _sign_token(private_key)
        assert verify_supabase_jwt(token, jwks_url="") is None
        assert verify_supabase_jwt(token, jwks_url=None) is None


# ---------------------------------------------------------------------------
# JWKS failure handling
# ---------------------------------------------------------------------------


class TestJWKSAvailability:
    def test_jwks_unreachable_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN JWKS endpoint unreachable WHEN verify THEN None (no raise)."""

        class _BrokenJWKSClient:
            def get_signing_key_from_jwt(self, _token: str) -> Any:  # noqa: ARG002
                raise jwt.exceptions.PyJWKClientError("JWKS 500")

        monkeypatch.setattr(
            jwt_module,
            "_get_jwks_client",
            lambda _url: _BrokenJWKSClient(),
        )
        token = _sign_token(private_key)
        # Must NOT raise — best-effort contract.
        assert verify_supabase_jwt(token, jwks_url=jwks_url) is None

    def test_jwks_returns_wrong_key_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, private_key: Any, jwks_url: str
    ) -> None:
        """GIVEN JWKS returns a key that doesn't match the token's signature THEN None."""
        # Stub returns a DIFFERENT public key — signature check fails.
        other_public = ec.generate_private_key(ec.SECP256R1()).public_key()
        monkeypatch.setattr(
            jwt_module,
            "_get_jwks_client",
            lambda _url: _FakeJWKSClient(other_public),
        )
        token = _sign_token(private_key)
        assert verify_supabase_jwt(token, jwks_url=jwks_url) is None


# ---------------------------------------------------------------------------
# JWKS client cache
# ---------------------------------------------------------------------------


class TestJWKSClientCache:
    def test_client_is_cached_per_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same JWKS URL → only ONE PyJWKClient instantiation (cached).

        Repeated calls to the real `_get_jwks_client` with the same URL
        must instantiate `PyJWKClient` exactly once (the second+ calls
        consult the module-level `_jwks_client_cache` dict).

        Verifies that the module-level `_jwks_client_cache` dict is
        consulted on subsequent calls (avoids re-instantiating the
        HTTP client + cache on every request).
        """
        from unittest.mock import MagicMock

        _reset_jwks_client_cache_for_tests()
        mock_cls = MagicMock()
        # Patch the class the REAL function looks up — the real function
        # is captured at module import time before the autouse fixture
        # replaces `_get_jwks_client` itself.
        monkeypatch.setattr(jwt_module, "PyJWKClient", mock_cls)

        url = "https://example.com/jwks.json"
        client1 = _REAL_GET_JWKS_CLIENT(url)
        client2 = _REAL_GET_JWKS_CLIENT(url)
        client3 = _REAL_GET_JWKS_CLIENT(url)

        # All three calls return the SAME object (cached).
        assert client1 is client2 is client3
        # And PyJWKClient was instantiated exactly ONCE (not three times).
        assert mock_cls.call_count == 1

    def test_different_urls_get_different_clients(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Different JWKS URLs get independent cached clients."""
        from unittest.mock import MagicMock

        _reset_jwks_client_cache_for_tests()
        # `side_effect=lambda *args: MagicMock()` makes each `PyJWKClient(...)`
        # call return a NEW mock instance (the default `MagicMock()` returns
        # the SAME mock on every call — useless for this test).
        mock_cls = MagicMock(side_effect=lambda *_args, **_kwargs: MagicMock())
        monkeypatch.setattr(jwt_module, "PyJWKClient", mock_cls)

        client_a = _REAL_GET_JWKS_CLIENT("https://a.example.com/jwks.json")
        client_b = _REAL_GET_JWKS_CLIENT("https://b.example.com/jwks.json")

        assert client_a is not client_b
        assert mock_cls.call_count == 2


# ---------------------------------------------------------------------------
# Sanity: pyjwt-cryptography wiring
# ---------------------------------------------------------------------------


def test_pyjwt_supports_es256_signing_and_verification() -> None:
    """Sanity check: PyJWT can sign AND verify ES256 with our test keypair.

    Guards against accidental downgrades (e.g. someone removing the
    cryptography extra and breaking ES256 silently).
    """
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    token = jwt.encode(
        {
            "sub": "u1",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
            "aud": "authenticated",
        },
        priv,
        algorithm="ES256",
    )
    payload = jwt.decode(token, pub_pem, algorithms=["ES256"], audience="authenticated")
    assert payload["sub"] == "u1"
