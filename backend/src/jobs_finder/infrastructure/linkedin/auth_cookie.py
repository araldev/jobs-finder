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


class MultiEnvLinkedInAuthCookiesAdapter:
    """Reads 4-5 LinkedIn cookies from `Settings.linkedin_*` (no I/O at runtime).

    `cookies()` returns `None` when ALL cookies are `None` (the
    v1 anonymous sentinel); otherwise returns the filtered list
    in the canonical order
    `li_at → JSESSIONID → bcookie → bscookie → li_gc`
    (REQ-LST-COOKIE-004 + REQ-LBSc-002). The 5 cookies are
    independent `SecretStr | None` slots; each is checked at
    the `Settings` boundary by the shared `mode="before"`
    validator that normalizes empty values to `None`.

    Spec: REQ-LST-COOKIE-001..005 + REQ-LBSc-002 (F-4 fold-in).
    The ctor takes the 5 values DIRECTLY (not the `Settings`
    instance). The composition root is the only site that reads
    `Settings.linkedin_*`; the adapter stays a pure value-holder.
    The class uses `__slots__` for memory efficiency and to
    document the no-state invariant at the type level (matches
    the `EnvLinkedInAuthCookieAdapter` style above and the
    `NoOpRateLimiter` style at `application/ports.py`).

    T-005 of `backend-linkedin-xvfb` adds the 5th slot
    `bscookie` (F-4 fold-in per obs #375 §9). The slot lands
    alphabetically between `bcookie` and `li_gc` in the
    canonical order. The 4-cookie path is byte-identical when
    `bscookie=None` (the F-4 additivity pin).
    """

    __slots__ = ("_li_at", "_jsessionid", "_bcookie", "_bscookie", "_li_gc")

    # Canonical LinkedIn-session cookie order. The order is
    # load-bearing: a future refactor that re-orders these 5
    # names MUST also update the order in `__init__` AND in
    # `cookies()` (they're both indexed by position in the
    # ctor's `__init__` kwargs). The tests
    # `test_cookies_returns_deterministic_order` (4 cookies)
    # and `test_bscookie_cookie_injection` (5 cookies) pin the
    # orders so a re-order breaks the tests loudly.
    # T-005 of `backend-linkedin-xvfb` inserts `bscookie` at
    # position 3 (between `bcookie` and `li_gc`).
    _COOKIE_NAMES = ("li_at", "JSESSIONID", "bcookie", "bscookie", "li_gc")

    def __init__(
        self,
        li_at: SecretStr | None,
        jsessionid: SecretStr | None,
        bcookie: SecretStr | None,
        li_gc: SecretStr | None,
        bscookie: SecretStr | None = None,
    ) -> None:
        self._li_at = li_at
        self._jsessionid = jsessionid
        self._bcookie = bcookie
        self._li_gc = li_gc
        # T-005 of `backend-linkedin-xvfb` — REQ-LBSc-002.
        # The 5th LinkedIn cookie (F-4 fold-in per obs #375 §9).
        # Default `None` preserves the v1 + v2 4-cookie path
        # when the operator does not set `LINKEDIN_BSCOOKIE`.
        self._bscookie = bscookie

    def cookies(self) -> list[tuple[str, SecretStr]] | None:
        """Return the filtered cookie list, or `None` when all 5 are `None`.

        REQ-LST-COOKIE-002: when ALL cookies are `None` (the
        v1 anonymous path), returns `None` so the caller can
        short-circuit (the scraper skips `add_cookies` entirely).

        REQ-LST-COOKIE-003: when ≥1 cookie is non-`None`, returns
        the filtered list with `None` entries removed.

        REQ-LST-COOKIE-004 + REQ-LBSc-002: the order is ALWAYS
        `li_at → JSESSIONID → bcookie → bscookie → li_gc` (the
        canonical LinkedIn-session order), NOT the order the
        constructor was called with. The 5-name order is
        stable across the 4-cookie path (when `bscookie=None`,
        the filtered list has 4 entries; when set, 5).
        """
        pairs: list[tuple[str, SecretStr]] = []
        for name, value in zip(
            self._COOKIE_NAMES,
            (self._li_at, self._jsessionid, self._bcookie, self._bscookie, self._li_gc),
            strict=True,
        ):
            if value is not None:
                pairs.append((name, value))
        return pairs if pairs else None

    def __repr__(self) -> str:
        """Mask the cookie set as `<set: N cookies>` or `<unset>` (no values).

        REQ-LST-COOKIE-005: the repr shows the COUNT (an
        acceptable 1-bit side-channel: the operator's own
        `ls -la .env` is richer) but NEVER any cookie value. The
        repr contains the synthetic test value (`"AQEAAAAQEAAA"`,
        etc.) ONLY when the caller has the repr as a string in
        test code; production code never logs the repr of a
        cookie adapter unless it intentionally wants the count
        channel.
        """
        count = sum(
            v is not None
            for v in (self._li_at, self._jsessionid, self._bcookie, self._bscookie, self._li_gc)
        )
        if count == 0:
            return "MultiEnvLinkedInAuthCookiesAdapter(<unset>)"
        return f"MultiEnvLinkedInAuthCookiesAdapter(<set: {count} cookies>)"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MultiEnvLinkedInAuthCookiesAdapter):
            return NotImplemented
        # `SecretStr.__eq__` does NOT unwrap the secret — two
        # `SecretStr("AQEAAAAQEAAA")` instances ARE equal, which
        # is exactly what we want for settings comparison.
        return (
            self._li_at == other._li_at
            and self._jsessionid == other._jsessionid
            and self._bcookie == other._bcookie
            and self._bscookie == other._bscookie
            and self._li_gc == other._li_gc
        )

    def __hash__(self) -> int:
        return hash((self._li_at, self._jsessionid, self._bcookie, self._bscookie, self._li_gc))
