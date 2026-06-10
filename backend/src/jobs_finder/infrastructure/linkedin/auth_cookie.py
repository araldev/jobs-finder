"""LinkedIn auth-cookie adapter (T-001 of `backend-linkedin-auth`).

The `EnvLinkedInAuthCookieAdapter` is the production implementation
of `LinkedInAuthCookiePort`: a value-holder that reads the
operator's `li_at` session cookie from `Settings.linkedin_li_at`
at process start and returns it on every `cookie()` call. The
adapter is intentionally a NO-OP value provider — no I/O, no
`await`, no logging side-effects — so it can be replaced in
tests by `FakeLinkedInAuthCookiePort` (in `tests/conftest.py`)
without touching the scraper.

Spec: REQ-LA-COOKIE-001 (Protocol conformance),
REQ-LA-COOKIE-002 (returns `None` in soft mode),
REQ-LA-COOKIE-003 (returns `SecretStr` — log-masking is
enforced by the type itself), REQ-LA-COOKIE-004 (the
`__repr__` mask is enforced at the `LinkedInScraperSettings`
level, not the adapter — the adapter's value is opaque to
the caller).

The class uses `__slots__` for memory efficiency and to
document the no-state invariant at the type level (matches
the `NoOpRateLimiter` style at `application/ports.py`).
"""

from __future__ import annotations

from pydantic import SecretStr


class EnvLinkedInAuthCookieAdapter:
    """Reads `li_at` from `Settings.linkedin_li_at` (no I/O at runtime).

    The ctor takes the `SecretStr | None` value DIRECTLY (not the
    `Settings` instance). The composition root is the only site
    that reads `Settings.linkedin_li_at`; the adapter stays a
    pure value-holder. This split keeps the adapter trivially
    testable (no `Settings` ctor side-effects) and prevents a
    future refactor from accidentally calling
    `.get_secret_value()` at search time (REQ-LA-SCR-005).
    """

    __slots__ = ("_cookie",)

    def __init__(self, cookie: SecretStr | None) -> None:
        # Normalize empty `SecretStr` to `None` at the adapter boundary
        # (REQ-LA-COOKIE-002 acceptance bullet 2). The `Settings`
        # `_normalize_empty_li_at` validator (T-002) ALSO normalizes
        # empty→None at the `Settings` ctor, so under normal
        # composition-root wiring the adapter never receives
        # `SecretStr("")`. The adapter-level normalization is
        # defense-in-depth so a test that constructs the adapter
        # directly with `SecretStr("")` (bypassing `Settings`) still
        # observes the same contract.
        if cookie is not None and cookie.get_secret_value() == "":
            self._cookie = None
        else:
            self._cookie = cookie

    def cookie(self) -> SecretStr | None:
        return self._cookie

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EnvLinkedInAuthCookieAdapter):
            return NotImplemented
        # `SecretStr.__eq__` does NOT unwrap the secret — two
        # `SecretStr("AQEAAAAQEAAA")` instances ARE equal, which
        # is exactly what we want for settings comparison
        # (REQ-LA-COOKIE-004 scenario: two settings with the
        # same cookie ARE equal).
        return self._cookie == other._cookie

    def __hash__(self) -> int:
        return hash(self._cookie)
