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

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import SecretStr

_logger = logging.getLogger(__name__)


def _atomic_write_json(path: str, data: Any) -> None:
    """Write `data` (JSON-serializable) to `path` atomically via `os.replace`.

    REQ-AC-101 + C-6 — atomic file write protects against
    partial content if the process is killed mid-write. The
    helper writes to `<path>.tmp`, `fsync`s the file, then
    `os.replace`s the temp onto the destination (POSIX
    guarantees `os.replace` is atomic on the same filesystem).
    `fsync` ensures the bytes hit disk BEFORE the rename so a
    crash after `os.replace` does NOT leave a 0-byte file
    masquerading as valid JSON.

    Caller is responsible for the directory existing (the
    3 adapters use absolute paths the composition root
    already created, OR relative paths the test fixtures
    own).
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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

    __slots__ = ("_cookie", "_cookie_path")

    def __init__(
        self,
        cookie: SecretStr | None,
        *,
        cookie_path: str | None = None,
    ) -> None:
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
        # REQ-AC-101 — optional side-channel file path. When set,
        # `set_cookies()` writes the new cookie dicts to this file
        # (atomic `os.replace`). When `None` (the v1 default; tests
        # that don't exercise refresh), `set_cookies()` raises
        # `RuntimeError` because the v1 singular adapter has no
        # implicit location to write to.
        self._cookie_path = cookie_path

    def cookie(self) -> SecretStr | None:
        return self._cookie

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """REQ-AC-101 — write `cookies` to the side-channel file.

        The v1 singular adapter holds a single `li_at` cookie in
        the ctor's `SecretStr`. `set_cookies()` writes the
        cookie dicts (Playwright `context.cookies()` shape) to
        the `cookie_path` side-channel file atomically
        (`os.replace` via `_atomic_write_json`). The ctor's
        `SecretStr` is intentionally NOT mutated — the
        side-channel file is secondary persistence (the v1
        adapter is a value-holder, not a stateful cache).

        REQ-AC-102 — read-after-write invariant. The
        side-channel file is written; the v1 `cookie()` method
        continues to return the original `SecretStr` (the
        process is meant to be RESTARTED after a refresh, at
        which point the operator updates the `.env` / shell
        export and the ctor re-reads the new value).

        Raises:
            RuntimeError: when `cookie_path is None` (no
                implicit location for the v1 singular adapter).
        """
        if self._cookie_path is None:
            raise RuntimeError(
                "EnvLinkedInAuthCookieAdapter.set_cookies() requires "
                "`cookie_path` to be set; the v1 singular adapter has "
                "no implicit side-channel location. Pass `cookie_path` "
                "to the ctor or use `MultiEnvLinkedInAuthCookiesAdapter` "
                "instead."
            )
        _atomic_write_json(self._cookie_path, list(cookies))
        _logger.warning(
            "env-var-sourced cookie written to side-channel file; "
            "update .env manually to survive process restart"
        )

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

    __slots__ = (
        "_bcookie",
        "_bscookie",
        "_cookie_path",
        "_li_at",
        "_li_gc",
        "_jsessionid",
    )

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
        *,
        cookie_path: str | None = None,
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
        # REQ-AC-101 — optional side-channel file path. When set,
        # `set_cookies()` writes the new cookie dicts to this file
        # (atomic `os.replace`). When `None`, `set_cookies()` still
        # updates the 5 internal slots in-place (the canonical
        # use-case for the multi-env adapter — the runtime can
        # mutate the in-process state even without a side-channel
        # file because the scraper re-reads via `cookies()` on
        # every `search()` call).
        self._cookie_path = cookie_path

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

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """REQ-AC-101 + REQ-AC-102 — write `cookies` to internal state +
        optional side-channel file.

        Updates the 5 internal `__slots__` (`li_at`,
        `JSESSIONID`, `bcookie`, `bscookie`, `li_gc`) from
        the input dicts. Entries whose `name` is NOT in the
        canonical 5-name set are IGNORED (defense in depth —
        the slots only cover those 5; unknown names are
        filtered out per REQ-AC-101).

        When `cookie_path` was set on the ctor, ALSO writes
        the cookie dicts to the side-channel file atomically
        (`os.replace`). Emits the same WARNING log as the
        singular env adapter.

        REQ-AC-102 — after this call, `cookies()` returns
        the freshly-set pairs (read-after-write invariant).
        """
        # The 5 canonical slots. Note: `JSESSIONID` is the
        # canonical name in Playwright's `context.cookies()`
        # output (uppercase); the slot is `_jsessionid`
        # (lowercase, matching the env-var name). The map
        # below translates cookie dict `name` → slot.
        slot_map = {
            "li_at": "_li_at",
            "JSESSIONID": "_jsessionid",
            "jsessionid": "_jsessionid",  # accept lowercase too
            "bcookie": "_bcookie",
            "bscookie": "_bscookie",
            "li_gc": "_li_gc",
        }
        new_values: dict[str, SecretStr] = {}
        for c in cookies:
            name = str(c.get("name", ""))
            value = str(c.get("value", ""))
            slot = slot_map.get(name)
            if slot is None or not value:
                continue  # unknown name OR empty value → drop
            new_values[slot] = SecretStr(value)
        # Update the 5 slots in-place. None means "not set".
        self._li_at = new_values.get("_li_at")
        self._jsessionid = new_values.get("_jsessionid")
        self._bcookie = new_values.get("_bcookie")
        self._bscookie = new_values.get("_bscookie")
        self._li_gc = new_values.get("_li_gc")
        if self._cookie_path is not None:
            _atomic_write_json(self._cookie_path, list(cookies))
            _logger.warning(
                "env-var-sourced cookie written to side-channel file; "
                "update .env manually to survive process restart"
            )

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


class JsonLinkedInAuthCookiesAdapter:
    """Reads cookies from a JSON file (exported from Playwright).

    The JSON file is the canonical output of
    ``context.cookies()`` containing the full LinkedIn cookie
    jar. The adapter loads the file ONCE at ctor time and
    returns the session cookies (li_at, JSESSIONID, bcookie,
    bscookie, li_gc, li_rm, li_mc, lidc — the full set).
    Falls back to ``None`` (no cookies) when the file does not
    exist or is empty.

    REQ-AC-101 — `set_cookies()` writes new cookie dicts back
    to the JSON file atomically (`os.replace`) and updates
    both `self._pairs` and `self._raw_dicts` from the new
    input. A rolling `<path>.bak` backup is created BEFORE
    the atomic rename (REQ-AC-101 + C-7) so the operator can
    recover the previous set if the new set is corrupt.

    Conforms to ``LinkedInAuthCookiesPort`` structurally.
    """

    _COOKIE_NAMES = (
        "li_at",
        "JSESSIONID",
        "bcookie",
        "bscookie",
        "li_gc",
        "li_rm",
        "li_mc",
        "lidc",
        "lang",
        "timezone",
        "sdui_ver",
    )

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._path = (
            str(path)
            if path is not None
            else str(
                Path(__file__).resolve().parent.parent.parent.parent.parent.parent
                / "linkedin_cookies.json"
            )
        )
        self._pairs: list[tuple[str, SecretStr]] | None = None
        self._raw_dicts: list[dict[str, Any]] | None = None
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Read the JSON file from `self._path` into internal state.

        On `FileNotFoundError` or `JSONDecodeError`, internal
        state stays `None` (the soft-mode sentinel — the
        scraper skips `add_cookies`).
        """
        try:
            with open(self._path) as f:
                cookies = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        pairs: list[tuple[str, SecretStr]] = []
        raw_dicts: list[dict[str, Any]] = []
        for c in cookies:
            if c["name"] in self._COOKIE_NAMES and c.get("value"):
                pairs.append((c["name"], SecretStr(c["value"].strip('"'))))
                raw_dicts.append(
                    {
                        "name": c["name"],
                        "value": c["value"].strip('"'),
                        "domain": c.get("domain", ".linkedin.com"),
                        "path": c.get("path", "/"),
                        "httpOnly": c.get("httpOnly", True),
                        "secure": c.get("secure", True),
                    }
                )
        self._pairs = pairs if pairs else None
        self._raw_dicts = raw_dicts if raw_dicts else None

    def cookies(self) -> list[tuple[str, SecretStr]] | None:
        return self._pairs

    def cookie_dicts(self) -> list[dict[str, Any]] | None:
        """Return full cookie dicts with original attributes (domain, path, httpOnly, secure).

        Used by the scraper to inject cookies via ``ctx.add_cookies()``
        with the EXACT attributes the browser exported — avoiding the
        ``ERR_TOO_MANY_REDIRECTS`` that happens when hardcoding
        ``domain=".linkedin.com"`` for cookies that originally had
        ``domain=".www.linkedin.com"``.
        """
        return self._raw_dicts

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """REQ-AC-101 + REQ-AC-102 — atomically rewrite the JSON file.

        Steps:
        1. Best-effort copy the current file (if it exists) to
           `<path>.bak`. Best-effort because a missing pre-existing
           file is the no-op soft-mode case.
        2. Validate each cookie dict has the required keys
           (`name`, `value`, `domain`). Unknown / malformed
           entries are dropped (defense in depth).
        3. Write the validated list to `<path>.tmp` and atomically
           `os.replace` it onto `<path>` (REQ-AC-101 + C-6).
        4. Update `self._pairs` and `self._raw_dicts` from the new
           input (REQ-AC-102 read-after-write invariant).
        """
        # Step 1: rolling .bak (best-effort).
        bak_path = self._path + ".bak"
        if os.path.exists(self._path):
            with contextlib.suppress(OSError):
                # `os.replace` is atomic; if it fails (e.g.
                # permission error), we still proceed to write
                # the new file — the operator can recover the
                # previous set from the `linkedin_cookies.json`
                # git history if needed.
                os.replace(self._path, bak_path)
        # Step 2: validate + fill defaults. Reject cookies
        # missing `name` or `value` (Playwright's
        # `context.cookies()` always emits these — defense in
        # depth against a malformed refresher payload). Other
        # fields default to the LinkedIn-canonical values:
        # `domain=".linkedin.com"`, `path="/"`, `expires=-1`,
        # `httpOnly=True`, `secure=True`, `sameSite="Lax"`.
        validated: list[dict[str, Any]] = []
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            validated.append(
                {
                    "name": name,
                    "value": value,
                    "domain": str(c.get("domain", ".linkedin.com")),
                    "path": str(c.get("path", "/")),
                    "expires": c.get("expires", -1),
                    "httpOnly": bool(c.get("httpOnly", True)),
                    "secure": bool(c.get("secure", True)),
                    "sameSite": c.get("sameSite", "Lax"),
                }
            )
        # Step 3: atomic write.
        _atomic_write_json(self._path, validated)
        # Step 4: update internal state from the validated list.
        pairs: list[tuple[str, SecretStr]] = []
        raw_dicts: list[dict[str, Any]] = []
        for c in validated:
            if c["name"] in self._COOKIE_NAMES:
                pairs.append((c["name"], SecretStr(c["value"])))
                raw_dicts.append(
                    {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ".linkedin.com"),
                        "path": c.get("path", "/"),
                        "httpOnly": c.get("httpOnly", True),
                        "secure": c.get("secure", True),
                    }
                )
        self._pairs = pairs if pairs else None
        self._raw_dicts = raw_dicts if raw_dicts else None
