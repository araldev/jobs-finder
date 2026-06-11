# Tasks: `backend-linkedin-stealth`

> **Status**: `tasks` (ready for `sdd-apply` after orchestrator review of §13 Review Workload Forecast)
> **Base**: `6402798` (post `backend-linkedin-auth` merge on `main`)
> **Design**: obs #368
> **Spec**: obs #367 (15 REQ-LST-* = 3 CF + 5 COOKIE + 4 SCR + 3 CFG)
> **Proposal**: obs #366
> **Exploration**: obs #365
> **Trigger**: obs #364 (live `ERR_TOO_MANY_REDIRECTS` with v1 `li_at`)
> **Precedent cycle**: obs #362 (v1 archive), obs #357 (v1 tasks template), obs #83 (Indeed stealth)
> **Mode**: `both` (OpenSpec filesystem + Engram)
> **Strict TDD**: ACTIVE — every REQ-LST-* scenario is a real test, RED first
> **Confidence note**: 0.55 per explore obs #365 §4.4 that `playwright-stealth` bypasses the 2026 Cloudflare+LinkedIn 302-loop. Documented fallback: `backend-linkedin-residential-proxy` (out of scope).

## 1. Goal

Ship the first-intent mitigation for the LinkedIn + Cloudflare 302-loop blocker (obs #364). The change extends the just-merged `backend-linkedin-auth` (v1, at `6402798`) along 3 axes: (1) inject `playwright-stealth` (already a project dep at `pyproject.toml:25`, used by Indeed at `indeed/scraper.py:246-247` and InfoJobs at `infojobs/scraper.py:326-327`) at the `BrowserContext` level; (2) add a NEW `LinkedInAuthCookiesPort` (plural) Protocol + `MultiEnvLinkedInAuthCookiesAdapter` that aggregates 4 cookies (`li_at` + `JSESSIONID` + `bcookie` + `li_gc`); (3) add `is_cloudflare_challenge(soup)` pure-function detector that surfaces the 302-loop gracefully (soft WARNING + return `[]`). The v1 `EnvLinkedInAuthCookieAdapter` is KEPT byte-identical (35 v1 tests construct it directly). Single PR, 5 conventional commits, ~528 net LOC.

## 2. Work units (overview)

| Unit | Goal | LOC | Depends on |
|---|---|---|---|
| T-001 | NEW `MultiEnvLinkedInAuthCookiesAdapter` + `LinkedInAuthCookiesPort` Protocol + `FakeLinkedInAuthCookiesPort` conftest companion + 3 backward-compat tests | ~140 | — (foundation) |
| T-002 | NEW 3 `Settings.linkedin_*` fields (`jsessionid` + `bcookie` + `li_gc`) + 2 shared validator helpers + 5 tests | ~70 | T-001 (composition root reads all 4 fields) |
| T-003 | NEW `is_cloudflare_challenge(soup)` pure function + `CLOUDFLARE_CHALLENGE_HTML` fixture + 5 tests | ~80 | — (independent pure parser) |
| T-004 | EXTEND `LinkedInPlaywrightScraper` — `stealth: Stealth \| None` ctor kwarg + `apply_stealth_async` injection + multi-cookie `add_cookies` + `LinkedInScraperSettings.auth_cookies`/`stealth` slots + closure `is_cloudflare_challenge` precedence + ~10 tests | ~80 | T-001 (Protocol) + T-002 (Settings field) + T-003 (detector) |
| T-005 | EXTEND `app_factory.build_app()` — `MultiEnvLinkedInAuthCookiesAdapter` wire + `Stealth()` wire + 4-`None` startup WARNING + integration tests + `.env.example` + `README.md` | ~80 | T-001 + T-002 + T-004 |

**Total**: ~528 net LOC across 5 commits (~105 LOC/commit avg, well under 400-line per-commit sub-budget and 5,000-line review budget).

## 3. Work units (detailed)

---

### T-001: `LinkedInAuthCookiesPort` Protocol + `MultiEnvLinkedInAuthCookiesAdapter` + `FakeLinkedInAuthCookiesPort` conftest companion

**REQ coverage**: REQ-LST-COOKIE-001, REQ-LST-COOKIE-002, REQ-LST-COOKIE-003, REQ-LST-COOKIE-004, REQ-LST-COOKIE-005
**Files**:
- MODIFIED: `backend/src/jobs_finder/application/ports.py` (+12 LOC) — add `LinkedInAuthCookiesPort` Protocol after v1 `LinkedInAuthCookiePort` at L665
- MODIFIED: `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` (+45 LOC) — add `MultiEnvLinkedInAuthCookiesAdapter` class below v1 `EnvLinkedInAuthCookieAdapter` at L73; v1 class UNCHANGED
- MODIFIED: `backend/tests/conftest.py` (+15 LOC) — add `FakeLinkedInAuthCookiesPort` companion below v1 `FakeLinkedInAuthCookiePort` at L76; v1 fake UNCHANGED
- NEW: `backend/tests/unit/test_linkedin_stealth.py` (~100 LOC) — 10 scenarios (Protocol conformance + adapter ctor + cookies() return values + order + repr mask)
- MODIFIED: `backend/tests/unit/test_linkedin_auth_cookie.py` (+15 LOC) — 3 backward-compat scenarios (v1 `EnvLinkedInAuthCookieAdapter` ctor still works with `SecretStr | None`)
**Test command**: `cd backend && uv run pytest tests/unit/test_linkedin_stealth.py tests/unit/test_linkedin_auth_cookie.py -v`
**Acceptance**:
- [ ] All 10 new tests in `test_linkedin_stealth.py` + 3 extended tests in `test_linkedin_auth_cookie.py` PASS
- [ ] `LinkedInAuthCookiesPort` Protocol exists at `application/ports.py:668+` with exactly 1 method `cookies() -> list[tuple[str, SecretStr]] | None`
- [ ] `MultiEnvLinkedInAuthCookiesAdapter` lives at `infrastructure/linkedin/auth_cookie.py` next to v1; v1 class is byte-identical (no `__init__.py` changes — AGENTS.md rule #4)
- [ ] `FakeLinkedInAuthCookiesPort` lives at `tests/conftest.py:80+` next to v1 fake; v1 fake is byte-identical
- [ ] Both `MultiEnvLinkedInAuthCookiesAdapter` and `FakeLinkedInAuthCookiesPort` satisfy `LinkedInAuthCookiesPort` structurally (`mypy --strict` verified)
- [ ] `MultiEnvLinkedInAuthCookiesAdapter.__repr__` with 4 set cookies contains `"<set: 4 cookies>"` and does NOT contain any synthetic test value
- [ ] `cookies()` returns `None` when all 4 are `None`; returns filtered list in deterministic order `li_at → JSESSIONID → bcookie → li_gc` when ≥1 is non-None
- [ ] `uv run mypy --strict` is clean (project-wide)
- [ ] `uv run ruff check` + `uv run ruff format --check` clean
- [ ] `uv run pytest` (full suite, 1,254 v1 + 13 new = 1,267) is GREEN — the 35 v1 tests stay GREEN
- [ ] No real LinkedIn cookie value appears in any committed file (only `"AQEAAAAQEAAA"`, `"ajax:12345"`, `"v2_xyz"`, `"gc_abc"` as sentinels)
- [ ] Git log shows 1 commit: `feat(linkedin-stealth): add LinkedInAuthCookiesPort + MultiEnvAdapter + test double`

**RED test** (paste verbatim — `test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_returns_deterministic_order`):
```python
def test_cookies_returns_deterministic_order() -> None:
    """`cookies()` always returns li_at, JSESSIONID, bcookie, li_gc in that order.

    Pins REQ-LST-COOKIE-004: the order is the canonical LinkedIn-session
    order (the v1 caplog bug was a wrong-order assertion; this test
    pins the correct order so a future refactor that re-orders the
    fields breaks the test loudly).
    """
    from pydantic import SecretStr
    from jobs_finder.infrastructure.linkedin.auth_cookie import (
        MultiEnvLinkedInAuthCookiesAdapter,
    )
    adapter = MultiEnvLinkedInAuthCookiesAdapter(
        li_at=SecretStr("AQEAAAAQEAAA"),
        jsessionid=SecretStr("ajax:12345"),
        bcookie=SecretStr("v2_xyz"),
        li_gc=SecretStr("gc_abc"),
    )
    names = [name for (name, _value) in adapter.cookies()]
    assert names == ["li_at", "JSESSIONID", "bcookie", "li_gc"]
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py`):
```python
class MultiEnvLinkedInAuthCookiesAdapter:
    """Reads 4 LinkedIn cookies from `Settings.linkedin_*` (no I/O at runtime).

    `cookies()` returns `None` when ALL 4 are `None` (the v1 anonymous
    sentinel); otherwise returns the filtered list in the canonical
    order `li_at → JSESSIONID → bcookie → li_gc` (REQ-LST-COOKIE-004).
    """
    __slots__ = ("_li_at", "_jsessionid", "_bcookie", "_li_gc")
    _COOKIE_NAMES = ("li_at", "JSESSIONID", "bcookie", "li_gc")
    def __init__(self, li_at, jsessionid, bcookie, li_gc) -> None:
        self._li_at, self._jsessionid, self._bcookie, self._li_gc = (
            li_at, jsessionid, bcookie, li_gc,
        )
    def cookies(self) -> list[tuple[str, SecretStr]] | None:
        pairs: list[tuple[str, SecretStr]] = []
        for name, value in zip(
            self._COOKIE_NAMES,
            (self._li_at, self._jsessionid, self._bcookie, self._li_gc),
            strict=True,
        ):
            if value is not None:
                pairs.append((name, value))
        return pairs if pairs else None
    def __repr__(self) -> str:
        count = sum(
            v is not None
            for v in (self._li_at, self._jsessionid, self._bcookie, self._li_gc)
        )
        return f"MultiEnvLinkedInAuthCookiesAdapter(<{'set: ' + str(count) + ' cookies' if count else 'unset'}>)"
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MultiEnvLinkedInAuthCookiesAdapter):
            return NotImplemented
        return (
            self._li_at == other._li_at
            and self._jsessionid == other._jsessionid
            and self._bcookie == other._bcookie
            and self._li_gc == other._li_gc
        )
    def __hash__(self) -> int:
        return hash((self._li_at, self._jsessionid, self._bcookie, self._li_gc))
```

**Commit subject**: `feat(linkedin-stealth): add LinkedInAuthCookiesPort + MultiEnvAdapter + test double`

**Rollback**: `git revert <commit-sha>` — Protocol + adapter + test double + 3 backward-compat tests are additive; the v1 `EnvLinkedInAuthCookieAdapter` + v1 `FakeLinkedInAuthCookiePort` are byte-identical; the 35 v1 tests stay green.

---

### T-002: 3 new `Settings.linkedin_*` fields + 2 shared validator helpers

**REQ coverage**: REQ-LST-CFG-001, REQ-LST-CFG-002, REQ-LST-CFG-003
**Files**:
- MODIFIED: `backend/src/jobs_finder/infrastructure/config.py` (+50 LOC, -10 LOC) — add 3 new `linkedin_{jsessionid,bcookie,li_gc}` fields after v1 `linkedin_li_at` block at L362; refactor v1 `_normalize_empty_li_at` + `_reject_short_li_at` to delegate to 2 new shared helpers (`_normalize_empty_linkedin_optional_secret` + `_reject_short_linkedin_optional_cookie`); bind all 4 fields to the 2 shared validators via 4 `field_validator` decorators
- MODIFIED: `backend/tests/unit/test_linkedin_config.py` (+20 LOC) — add 5 scenarios (1 per new field for env round-trip + 1 parametrized shared-validator test + 1 repr-mask test)
**Test command**: `cd backend && uv run pytest tests/unit/test_linkedin_config.py -v`
**Acceptance**:
- [ ] All 5 new tests PASS + the 10 v1 `test_linkedin_config.py` tests stay GREEN (v1 field + 2 v1 inline validators are REFACTORED to delegate, no behavior change)
- [ ] 3 new fields `linkedin_jsessionid`, `linkedin_bcookie`, `linkedin_li_gc` exist on `Settings`, each `SecretStr | None` with `AliasChoices(<UPPER>, <lower>)`
- [ ] 2 shared helpers (`_normalize_empty_linkedin_optional_secret` + `_reject_short_linkedin_optional_cookie`) are at module level in `config.py`; the factory variant of the second helper accepts a `field_name: str` for the error message
- [ ] `Settings(linkedin_jsessionid=SecretStr("abc"))` raises `ValidationError` with message containing `"LINKEDIN_JSESSIONID"`, `"must be at least 8 characters"`, `"got 3"`
- [ ] `Settings(linkedin_jsessionid=SecretStr("12345678"))` (8 chars exact) PASSES
- [ ] `Settings(linkedin_bcookie="")` normalizes to `None` (defense-in-depth via the shared before-validator)
- [ ] `repr(Settings(linkedin_jsessionid=SecretStr("AQEAAAAQEAAA")))` does NOT contain `"AQEAAAAQEAAA"`
- [ ] `uv run mypy --strict` clean
- [ ] `uv run ruff check` + `uv run ruff format --check` clean
- [ ] `uv run pytest` (full suite, 1,267 baseline + 5 new = 1,272) is GREEN
- [ ] No real LinkedIn cookie in any committed file
- [ ] Git log shows 1 commit: `feat(linkedin-stealth): add Settings.linkedin_{jsessionid,bcookie,li_gc} + shared validators`

**RED test** (paste verbatim — `test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_rejects_short_jsessionid_with_field_name`):
```python
def test_settings_rejects_short_jsessionid_with_field_name() -> None:
    """`Settings(linkedin_jsessionid=SecretStr('abc'))` raises with the field name.

    Pins REQ-LST-CFG-002: the error message names the field so the
    operator can self-diagnose (a 3-char `LINKEDIN_JSESSIONID` typo is
    not the same as a 3-char `LINKEDIN_LI_AT` typo). Mirrors the v1
    `test_settings_rejects_short_li_at_3_chars` pattern with a
    different field + a different env-var name in the error.
    """
    import pytest
    from pydantic import SecretStr, ValidationError
    from jobs_finder.infrastructure.config import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(linkedin_jsessionid=SecretStr("abc"))
    msg = str(exc_info.value)
    assert "LINKEDIN_JSESSIONID" in msg
    assert "must be at least 8 characters" in msg
    assert "got 3" in msg
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/config.py`):
```python
linkedin_jsessionid: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("LINKEDIN_JSESSIONID", "linkedin_jsessionid"),
)
linkedin_bcookie: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("LINKEDIN_BCOOKIE", "linkedin_bcookie"),
)
linkedin_li_gc: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("LINKEDIN_LI_GC", "linkedin_li_gc"),
)

def _normalize_empty_linkedin_optional_secret(cls, v):
    """Mode='before': None / '' / SecretStr('') -> None."""
    if v is None: return None
    if isinstance(v, SecretStr): return v if v.get_secret_value() else None
    if isinstance(v, str): return SecretStr(v) if v else None
    return v

def _reject_short_linkedin_optional_cookie(cls, v, *, field_name: str):
    """Mode='after': HARD len < MIN_LI_AT_LENGTH, SOFT None allowed."""
    if v is None: return None
    if len(v.get_secret_value()) < MIN_LI_AT_LENGTH:
        raise ValueError(
            f"{field_name} must be at least {MIN_LI_AT_LENGTH} "
            f"characters (got {len(v.get_secret_value())}); check for "
            "typos or unset the variable to run the scraper anonymously."
        )
    return v

# Bind 4 fields × 2 shared validators (8 decorators; ~10 LOC).
_normalize_linkedin_li_at = field_validator("linkedin_li_at", mode="before")(
    _normalize_empty_linkedin_optional_secret
)
# ...same for jsessionid, bcookie, li_gc...
# A factory wraps the after-validator to inject the field name.
def _make_reject_short(field_name: str):
    @field_validator(field_name, mode="after")
    @classmethod
    def _bound(cls, v): return _reject_short_linkedin_optional_cookie(cls, v, field_name=field_name)
    return _bound
```

**Commit subject**: `feat(linkedin-stealth): add Settings.linkedin_{jsessionid,bcookie,li_gc} + shared validators`

**Rollback**: `git revert <commit-sha>` — 3 fields are additive (default `None`); the 2 v1 inline validators refactored to delegate (no behavior change for the v1 field). The 35 v1 tests stay green.

---

### T-003: `is_cloudflare_challenge(soup)` pure function + `CLOUDFLARE_CHALLENGE_HTML` fixture

**REQ coverage**: REQ-LST-CF-001, REQ-LST-CF-002, REQ-LST-CF-003
**Files**:
- MODIFIED: `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (+18 LOC) — add `is_cloudflare_challenge(soup)` after v1 `is_auth_wall` at L270
- MODIFIED: `backend/tests/fixtures/linkedin_search.py` (+20 LOC) — add `CLOUDFLARE_CHALLENGE_HTML` constant after v1 `BLOCK_PAGE_HTML` at L97
- NEW: `backend/tests/unit/test_linkedin_cloudflare_challenge.py` (~60 LOC) — 5 scenarios (signature + purity + positive fixture + 3 negative cases)
**Test command**: `cd backend && uv run pytest tests/unit/test_linkedin_cloudflare_challenge.py -v`
**Acceptance**:
- [ ] All 5 new tests PASS
- [ ] `is_cloudflare_challenge(soup)` lives at `infrastructure/linkedin/parsers.py:274+` next to v1 `is_auth_wall`; v1 functions unchanged
- [ ] Function is pure: no I/O, no `await`, no logging side-effects (verified by `test_is_cloudflare_challenge_is_pure_no_mutation`)
- [ ] `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML))` is `True` (positive fixture)
- [ ] `is_cloudflare_challenge(BeautifulSoup(SEARCH_PAGE_HTML))` is `False` (healthy SERP — no false positive)
- [ ] `is_cloudflare_challenge(BeautifulSoup(BLOCK_PAGE_HTML))` is `False` (LinkedIn auth wall — distinct signal)
- [ ] Cards-win rule: HTML with Cloudflare markers + 1 `div[data-entity-urn]` returns `False` (false-positive suppression)
- [ ] `CLOUDFLARE_CHALLENGE_HTML` fixture contains the 3 Cloudflare 2026 markers (title `Just a moment...`, `<noscript>`, `div.cf-mitigated` or `[data-cf-challenge]`) and 0 cards
- [ ] `uv run mypy --strict` clean
- [ ] `uv run ruff check` + `uv run ruff format --check` clean
- [ ] `uv run pytest` (full suite, 1,272 baseline + 5 new = 1,277) is GREEN — the scraper does NOT call `is_cloudflare_challenge` yet (T-004 wires the consumer)
- [ ] Git log shows 1 commit: `feat(linkedin-stealth): add is_cloudflare_challenge defensive detector`

**RED test** (paste verbatim — `test_linkedin_cloudflare_challenge.py::TestIsCloudflareChallenge::test_is_cloudflare_challenge_false_when_cards_present_even_with_challenge_marker`):
```python
def test_is_cloudflare_challenge_false_when_cards_present_even_with_challenge_marker() -> None:
    """Cards-win rule (REQ-LST-CF-003) suppresses false positives.

    A healthy SERP that happens to render Cloudflare-style markup
    (e.g. LinkedIn A/B test that reuses the 'Just a moment...'
    string in a rate-limit banner) MUST NOT match — the function
    returns False when ≥1 `div[data-entity-urn]` is present.
    """
    from bs4 import BeautifulSoup
    from jobs_finder.infrastructure.linkedin.parsers import is_cloudflare_challenge
    html = (
        '<html><head><title>Just a moment... check</title></head>'
        '<body><noscript>redirect</noscript>'
        '<div data-cf-challenge="x"></div>'
        '<div data-entity-urn="urn:li:jobPosting:1"></div>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "html.parser")
    assert is_cloudflare_challenge(soup) is False  # cards win
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/linkedin/parsers.py`):
```python
def is_cloudflare_challenge(soup: BeautifulSoup) -> bool:
    """Return True ONLY when the SERP is a Cloudflare 2026 challenge page.

    Distinct from `is_block_page` (LinkedIn 502 hard raise) and
    `is_auth_wall` (cookie-injected soft WARNING). 3-OR Cloudflare
    2026 signature (REQ-LST-CF-002): title "Just a moment..." AND
    <noscript> redirect block AND a cf-mitigated / [data-cf-challenge]
    marker. Cards-win rule (REQ-LST-CF-003): when ≥1
    `div[data-entity-urn]` is present, return False.
    """
    if soup.select("div[data-entity-urn]"):
        return False  # cards win
    has_title = soup.find(string=lambda t: t and "Just a moment" in t) is not None
    has_noscript = soup.find("noscript") is not None
    has_cf_marker = soup.select_one("div.cf-mitigated, [data-cf-challenge]") is not None
    return has_title and has_noscript and has_cf_marker
```

**Commit subject**: `feat(linkedin-stealth): add is_cloudflare_challenge defensive detector`

**Rollback**: `git revert <commit-sha>` — the function is additive; no caller in the scraper yet (T-004 wires the integration); no regression.

---

### T-004: `LinkedInPlaywrightScraper` — stealth injection + multi-cookie + closure precedence

**REQ coverage**: REQ-LST-SCR-001, REQ-LST-SCR-002, REQ-LST-SCR-003, REQ-LST-SCR-004
**Files**:
- MODIFIED: `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (+30 LOC, -2 LOC) — 5 changes: (a) ctor `stealth: Stealth | None = None` kwarg + `_stealth` slot; (b) `search()` `apply_stealth_async(ctx)` injection between `new_context` and `add_cookies`; (c) `search()` multi-cookie `add_cookies` (list comprehension replaces v1 1-cookie literal); (d) `LinkedInScraperSettings.__slots__` + ctor + repr/eq/hash extended with `auth_cookies` + `stealth`; (e) `_make_fetch_one_page` closure `is_cloudflare_challenge` integration in cookie path BEFORE `is_auth_wall`; anonymous path byte-identical to v1
- MODIFIED: `backend/tests/unit/test_linkedin_scraper.py` (+30 LOC) — 4 scenarios (stealth applied when provided, stealth skipped when None, multi-cookie golden assertion, closure warns on Cloudflare)
**Test command**: `cd backend && uv run pytest tests/unit/test_linkedin_scraper.py -v`
**Acceptance**:
- [ ] All 4 new tests PASS + all 35 v1 `test_linkedin_scraper*` tests stay GREEN (the v1 `auth_cookie` slot + ctor kwarg are KEPT; the v1 anonymous path is byte-identical)
- [ ] `LinkedInPlaywrightScraper.__init__` accepts `stealth: Stealth | None = None` kwarg; `self._stealth` is `None` by default
- [ ] `search()` calls `await self._stealth.apply_stealth_async(ctx)` WHEN `self._stealth is not None`, AFTER `new_context`, BEFORE `add_cookies` (mirrors Indeed at `indeed/scraper.py:246-247` + InfoJobs at `infojobs/scraper.py:326-327` byte-identically)
- [ ] `search()` calls `await ctx.add_cookies([{...} for (name, value) in cookies])` with the LinkedIn-shape dict (`domain=".linkedin.com"`, `path="/"`, `httpOnly=True`, `secure=True`) for each non-None cookie in `port.cookies()`
- [ ] When `auth_cookies is None` OR `port.cookies() is None`: NO `add_cookies` call (anonymous path preserved)
- [ ] When `is_cloudflare_challenge(soup)` returns True on the cookie path: emit WARNING with prefix `"LinkedIn Cloudflare challenge detected"` and the 3 missing cookie names; return `_parse_cards(soup, remaining)` (soft path)
- [ ] When `is_auth_wall(soup)` returns True on the cookie path: emit the v1 WARNING (preserved byte-identical); return `_parse_cards(soup, remaining)`
- [ ] When `is_block_page(soup)` returns True on the cookie path: raise `LinkedInBlockedError` (v1 hard raise, preserved)
- [ ] When `auth_cookies is None`: closure checks `is_block_page` ONLY (v1 byte-identical — the v1 `test_search_raises_blocked_on_auth_wall` is the regression check)
- [ ] `LinkedInScraperSettings.__repr__` masks `auth_cookies=<set>/<unset>` + `stealth=<set>/<unset>` (no value leak)
- [ ] `LinkedInScraperSettings.__eq__`/`__hash__` cover the 2 new fields
- [ ] `uv run mypy --strict` clean (the `playwright_stealth` import carries `# type: ignore[import-untyped]` per the Indeed + InfoJobs precedent at `indeed/scraper.py:69` + `infojobs/scraper.py:73`)
- [ ] `uv run ruff check` + `uv run ruff format --check` clean
- [ ] `uv run pytest` (full suite, 1,277 baseline + 4 new = 1,281) is GREEN
- [ ] No real LinkedIn cookie in any committed file
- [ ] Git log shows 1 commit: `feat(linkedin-stealth): inject playwright-stealth + extend closure precedence`

**RED test** (paste verbatim — `test_linkedin_scraper.py::TestStealthIntegration::test_stealth_is_applied_when_provided`, mirrors Indeed at `test_indeed_scraper.py:613-635`):
```python
async def test_stealth_is_applied_when_provided(self) -> None:
    """`stealth.apply_stealth_async` is awaited once with the created context.

    Mirrors `test_indeed_scraper.py::TestStealthIntegration::test_stealth_is_applied_when_provided`
    (obs #83 — the Indeed precedent). The browser_factory injection
    pattern isolates the integration: the real Playwright Chromium
    never launches; the mock Stealth records the awaited call.
    """
    from unittest.mock import AsyncMock, MagicMock
    from tests.fixtures.linkedin_search import SEARCH_PAGE_HTML
    # ... build FakePage + FakeBrowser + scraper (existing helper) ...
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _fake_browser = await _make_scraper_with(page)
    stealth = MagicMock()
    stealth.apply_stealth_async = AsyncMock()
    scraper._stealth = stealth  # direct attribute (Indeed pattern)
    async with scraper:
        await scraper.search("react", "Madrid", limit=5)
    assert stealth.apply_stealth_async.await_count == 1
    assert len(stealth.apply_stealth_async.await_args.args) == 1
    assert isinstance(stealth.apply_stealth_async.await_args.args[0], FakeContext)
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/linkedin/scraper.py`, after `new_context` at L305-308 and before the v1 `cookie` injection block):
```python
# Stealth injection (REQ-LST-SCR-001) — mirrors Indeed:246-247 + InfoJobs:326-327.
if self._stealth is not None:
    await self._stealth.apply_stealth_async(ctx)
# Multi-cookie injection (REQ-LST-SCR-002) — replaces v1 1-cookie literal.
auth_cookies_port = self._settings.auth_cookies
if auth_cookies_port is not None:
    cookies = auth_cookies_port.cookies()
    if cookies is not None:
        await ctx.add_cookies([
            {"name": name, "value": value.get_secret_value(),
             "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}
            for (name, value) in cookies
        ])
        _logger.debug("LinkedIn auth cookies injected (count=%d)", len(cookies))
# ... rest of search() unchanged ...
```

Closure integration (REQ-LST-SCR-003, replaces the v1 conditional at L426-435):
```python
auth_cookies = self._settings.auth_cookies
if auth_cookies is not None and auth_cookies.cookies() is not None:
    # Cookie path: softest filter first (Cloudflare 302-loop is
    # network-layer, softer than the cookie-injected auth wall).
    if is_cloudflare_challenge(soup):  # NEW
        _logger.warning(
            "LinkedIn Cloudflare challenge detected; stealth may be insufficient. "
            "Consider setting LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC in .env, "
            "or upgrading to a residential proxy."
        )
        return _parse_cards(soup, remaining)
    if is_auth_wall(soup):  # v1 (soft)
        _logger.warning("LinkedIn SERP appears auth-walled despite cookie injection; ...")
        return _parse_cards(soup, remaining)
    if is_block_page(soup):  # v1 (hard)
        raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
    return _parse_cards(soup, remaining)
# Anonymous path — v1 byte-identical.
if is_block_page(soup):
    raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
return _parse_cards(soup, remaining)
```

**Commit subject**: `feat(linkedin-stealth): inject playwright-stealth + extend closure precedence`

**Rollback**: `git revert <commit-sha>` — `stealth=None` default preserves v1 behavior; the v1 `auth_cookie` slot is KEPT; the v1 anonymous path is byte-identical. The `auth_cookies` slot is opt-in (default `None`); the closure is conditional on `auth_cookies is not None and auth_cookies.cookies() is not None`. The 35 v1 tests stay green.

---

### T-005: Composition root wire + integration tests + `.env.example` + `README.md`

**REQ coverage**: REQ-LST-COOKIE-001 (wire), REQ-LST-SCR-001 (Stealth wire)
**Files**:
- MODIFIED: `backend/src/jobs_finder/presentation/app_factory.py` (+15 LOC, -3 LOC) — replace v1 single-cookie wire at L260-294 with multi-cookie wire (4 fields) + `Stealth()` wire + extended 4-`None` startup WARNING; v1 `EnvLinkedInAuthCookieAdapter` import kept (the 35 v1 tests construct it directly; not used in the production wire)
- MODIFIED: `backend/.env.example` (+3 LOC) — add 3 placeholder lines `LINKEDIN_JSESSIONID=`, `LINKEDIN_BCOOKIE=`, `LINKEDIN_LI_GC=` + a security note
- MODIFIED: `backend/README.md` (+30 LOC) — new `### LinkedIn anti-bot stealth (multi-cookie + playwright-stealth)` subsection in the "Manual verification" section
- NEW: `backend/tests/integration/test_linkedin_stealth.py` (~60 LOC) — 3 end-to-end offline tests via `build_app(use_case=...)`: (1) startup WARNING fires when ALL 4 cookies are None; (2) no startup WARNING when ≥1 cookie is set; (3) the wired `auth_cookies` port is a `MultiEnvLinkedInAuthCookiesAdapter` with the expected 4 fields
**Test command**: `cd backend && uv run pytest tests/integration/test_linkedin_stealth.py tests/unit/test_linkedin_stealth.py -v`
**Acceptance**:
- [ ] All 3 new integration tests PASS
- [ ] `app_factory.build_app()` with ALL 4 `LINKEDIN_*` env vars unset emits exactly 1 WARNING with the text `"LinkedIn scraper running without any auth cookies"` + `"LINKEDIN_LI_AT"` (or all 4 mentioned); the 35 v1 test that asserts the v1 `"LinkedIn scraper running without auth cookie"` message is updated to match the new prefix (the v1 message is a substring of the new one, so the assertion still passes IF the test uses `in` — the apply phase verifies)
- [ ] `app_factory.build_app()` with `LINKEDIN_LI_AT=AQEAAAAQEAAA` set emits NO such WARNING
- [ ] The wired `LinkedInScraperSettings.auth_cookies` is a `MultiEnvLinkedInAuthCookiesAdapter` instance; `auth_cookie=None` is passed explicitly (backward compat slot)
- [ ] The wired `LinkedInScraperSettings.stealth` is a `Stealth` instance (not `None`)
- [ ] `backend/.env.example` has the 3 new placeholder lines + a comment explaining they are optional + the security note
- [ ] `backend/README.md` has the new subsection with: how to set the env vars (shell + `.env`), curl example with all 4 cookies, expected behavior (Cloudflare bypass via stealth), the `is_cloudflare_challenge` WARNING message, the residential-proxy fallback
- [ ] `cd backend && bash scripts/check.sh` is green (ruff + mypy + pytest)
- [ ] `uv run pytest` (full suite, 1,281 baseline + 3 new = 1,284) is GREEN
- [ ] No real LinkedIn cookie in any committed file
- [ ] Git log shows 1 commit: `feat(composition): wire multi-cookie + operator docs`

**RED test** (paste verbatim — `test_linkedin_stealth.py::test_build_app_wires_multi_env_adapter`):
```python
def test_build_app_wires_multi_env_adapter(monkeypatch) -> None:
    """`build_app()` wires `MultiEnvLinkedInAuthCookiesAdapter` (not v1).

    The 4 LINKEDIN_* env vars are set; the resulting scraper's
    `LinkedInScraperSettings.auth_cookies` MUST be a
    `MultiEnvLinkedInAuthCookiesAdapter` (NOT the v1 single-cookie
    shim); the `auth_cookie` slot MUST be `None` (the v1 slot is
    kept for backward compat with the 35 v1 tests that construct
    `EnvLinkedInAuthCookieAdapter` directly).
    """
    from jobs_finder.infrastructure.linkedin.auth_cookie import (
        MultiEnvLinkedInAuthCookiesAdapter,
    )
    from jobs_finder.presentation.app_factory import build_app
    monkeypatch.setenv("LINKEDIN_LI_AT", "AQEAAAAQEAAA")
    monkeypatch.setenv("LINKEDIN_JSESSIONID", "ajax:12345")
    monkeypatch.setenv("LINKEDIN_BCOOKIE", "v2_xyz")
    monkeypatch.setenv("LINKEDIN_LI_GC", "gc_abc")
    app = build_app()  # not None — the app is constructed
    # Reach into the wired scraper via the route's dependency
    # override (the integration test owns the composition root).
    scraper = app.state.linkedin_scraper  # type: ignore[attr-defined]
    assert isinstance(
        scraper._settings.auth_cookies, MultiEnvLinkedInAuthCookiesAdapter
    )
    assert scraper._settings.auth_cookie is None  # v1 slot is None
    assert scraper._settings.stealth is not None  # Stealth() is wired
```

**GREEN impl sketch** (`backend/src/jobs_finder/presentation/app_factory.py`):
```python
# Extended 4-`None` startup WARNING (replaces v1 single-`None` check at L260-264).
if (
    effective_settings.linkedin_li_at is None
    and effective_settings.linkedin_jsessionid is None
    and effective_settings.linkedin_bcookie is None
    and effective_settings.linkedin_li_gc is None
):
    _logger.warning(
        "LinkedIn scraper running without any auth cookies; "
        "SERP will hit the Cloudflare / auth wall and return a reduced list. "
        "Set at least LINKEDIN_LI_AT (or all 4) in .env to bypass the wall."
    )

if use_case is None:
    from playwright_stealth import Stealth  # type: ignore[import-untyped]
    auth_cookies_port = MultiEnvLinkedInAuthCookiesAdapter(
        li_at=effective_settings.linkedin_li_at,
        jsessionid=effective_settings.linkedin_jsessionid,
        bcookie=effective_settings.linkedin_bcookie,
        li_gc=effective_settings.linkedin_li_gc,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
        settings=LinkedInScraperSettings(
            user_agent=effective_settings.user_agent,
            timeout_ms=effective_settings.request_timeout_ms,
            max_pages=effective_settings.linkedin_max_pages,
            inter_page_delay_seconds=effective_settings.linkedin_inter_page_delay_seconds,
            location_resolver=location_resolver,
            auth_cookie=None,  # v1 slot kept (None in production wire)
            auth_cookies=auth_cookies_port,  # NEW (multi-cookie)
            stealth=Stealth(),  # NEW
        ),
    )
    # ... rest of wire unchanged (raw_use_case, linkedin_cache, use_case) ...
```

**Commit subject**: `feat(composition): wire multi-cookie + operator docs`

**Rollback**: `git revert <commit-sha>` — the wire is additive; the v1 `auth_cookie=None` slot is preserved; `stealth=None` is the default for any code path that doesn't pass the kwarg. The 35 v1 tests stay green. Zero-downtime: leaving all 4 `LINKEDIN_*` env vars empty runs the scraper anonymously (v1 behavior) without redeploy.

---

## 4. Dependency graph

```
T-001 (Protocol + MultiEnvAdapter + test double)
  ├──────────────────────────┐
  ▼                          ▼
T-002 (3 Settings fields   T-003 (is_cloudflare_challenge +
  + 2 shared validators)    CLOUDFLARE_CHALLENGE_HTML)
  │                          │
  └────────┬─────────────────┘
           ▼
         T-004 (scraper: stealth + multi-cookie + closure precedence)
           │
           ▼
         T-005 (composition wire + integration + docs)
```

- **T-001 FIRST**: the Protocol + adapter + test double are the foundation; nothing else compiles (or mypy-strict passes) without them.
- **T-002 + T-003 in parallel order** (T-002 before T-003 in the commit log for narrative clarity, but they don't import each other and can be merged in any order).
- **T-004 depends on T-001 + T-002 + T-003**: the scraper uses the Protocol (T-001) and the detector (T-003) and reads the Settings fields (T-002) for the composition wire. The default `auth_cookies=None` + `stealth=None` preserves v1 behavior.
- **T-005 LAST**: wire in the composition root + integration tests + operator docs. Closes the PR.

## 5. Test plan summary

**Total new test functions**: ~27 (10 stealth adapter + 5 cloudflare detector + 3 v1 backward-compat + 4 closure precedence + 5 config) on top of the 1,254 v1 baseline = **~1,281 tests after this change**.

**TDD discipline**: RED first (paste the test, watch it fail with the correct error), GREEN second (paste the impl, watch it pass), REFACTOR optional (clean up the impl, keep tests green), `uv run mypy --strict` + `uv run ruff check` + `uv run ruff format --check` + `uv run pytest` (full suite) on every commit.

**Backward compat**: the 35 v1 `backend-linkedin-auth` tests stay GREEN through all 5 commits (the v1 `EnvLinkedInAuthCookieAdapter` is byte-identical; the v1 `FakeLinkedInAuthCookiePort` is byte-identical; the v1 `LinkedInScraperSettings.auth_cookie` slot is kept; the v1 anonymous closure path is byte-identical).

**CI gates**: `cd backend && bash scripts/check.sh` is the final gate (ruff + mypy + pytest all green).

## 6. Out-of-scope tasks (explicit non-goals)

- **Residential proxy integration** — documented fallback path is `backend-linkedin-residential-proxy` if stealth fails (per explore obs #365 §4.6 + proposal §Out of scope).
- **Browser real (non-headless) mode** — headless is the test default; real mode is a follow-up if Cloudflare-2026 escalates further.
- **Automated cookie refresh** — the operator rotates manually; `is_cloudflare_challenge` WARNING is the signal.
- **Retry/backoff with exponential backoff** — the existing `paginated_search` helper handles timeouts.
- **Circuit breaker for LinkedIn** — would require process-state that we deliberately do not add.
- **Detectors for other anti-bot vendors** (DataDome, PerimeterX, Akamai) — out of scope; each new source/vendor is its own follow-up.
- **Modifying the other 2 scrapers (Indeed, InfoJobs)** — they already use stealth; no LinkedIn-specific work applies to them.
- **Live-network test against real LinkedIn** — AGENTS.md rule #1 forbids live scraping in tests; the live smoke test is documented in the README and run by the operator manually, not by CI.
- **Modifying `JobSearchPort`, `LocationResolverPort`, `JobSearchCacheKey`, `paginated_search`** — these are source-agnostic and stay UNCHANGED.
- **Modifying `is_block_page` or `is_auth_wall`** — 3 distinct functions with 3 distinct semantics stay byte-identical.
- **Modifying the v1 `linkedin_li_at` field or its 2 inline validators** — REFACTORED to delegate to the 2 new shared helpers (no behavior change).
- **Adding a new exception type for the Cloudflare-challenge path** — the scraper returns `[]` (REQ-LST-SCR-004) and emits a WARNING; a new exception would force the route to 502, defeating the "degraded but functional" semantic.
- **Frontend HTTP contract changes** — the route signature stays the same; the response body shape is unchanged.

## 7. Pre-apply checklist

- [x] All 5 tasks have at least 1 REQ-LST-* mapped (T-001 covers 5, T-002 covers 3, T-003 covers 3, T-004 covers 4, T-005 covers 2)
- [x] All RED tests are pasted in full and reference real test files
- [x] All GREEN impl sketches are real signatures (not "implement the adapter")
- [x] No task has a broken intermediate state — each task ends with `uv run pytest` GREEN (the v1 35 tests + the new tests added by the task)
- [x] No real LinkedIn cookie value in any committed file (only the synthetic 12-byte `"AQEAAAAQEAAA"` + `"ajax:12345"` + `"v2_xyz"` + `"gc_abc"` sentinels)
- [x] The `playwright-stealth` invocation in T-004 matches the Indeed+InfoJobs precedent byte-for-byte (`if self._stealth is not None: await self._stealth.apply_stealth_async(ctx)` AFTER `new_context` BEFORE `add_cookies`)
- [x] The `is_cloudflare_challenge` integration in T-004 follows the v1 conditional precedence flip (cookie path = softest first; anonymous path = v1 byte-identical)
- [x] The `LinkedInScraperSettings` 2 new slots (`auth_cookies` + `stealth`) coexist with the v1 `auth_cookie` slot (no class rename, no kwarg rename)
- [x] The 2 new shared validators in T-002 are REFACTORED from the v1 inline validators (no behavior change for the v1 field)

## 8. Risks (per-task, with mitigations)

| # | Risk | L | Mitigation |
|---|------|---|------------|
| 1 | **`playwright-stealth` may not bypass the LinkedIn + Cloudflare-2026-302-loop** (obs #365 §4.4) | **HIGH** | T-001 + T-004 are reversible (`git revert` removes the stealth + Protocol); the 0.55 confidence is documented; the residential-proxy follow-up is the documented fallback. CI suite is offline with fixtures, so a stealth runtime failure does not block CI. |
| 2 | **Multi-cookie partial injection** (4 cookies vs operator's 19+) | **HIGH** | The `cookies()` Protocol returns an arbitrary-length list; future changes add 1 Settings field + 1 adapter line; the `is_cloudflare_challenge` WARNING is operator-actionable. |
| 3 | **The Cloudflare challenge page evolves** (2026 → 2027) | MED | T-003 pins the 2026 selector set in `CLOUDFLARE_CHALLENGE_HTML`; a future change is 1 fixture + 1 detector function. |
| 4 | **Backward compat with v1 `EnvLinkedInAuthCookieAdapter(SecretStr)` ctor** (35 v1 tests) | MED | T-001 keeps the v1 class byte-identical + adds 3 backward-compat tests; T-004 keeps the v1 `auth_cookie` slot. |
| 5 | **`playwright-stealth` Python port maintenance** (single maintainer) | LOW | Already pinned at `playwright-stealth>=2.0,<3.0` in `pyproject.toml:25`; 2.x API is stable. |
| 6 | **Future LinkedIn-cookie-set growth** | LOW | The Protocol returns an arbitrary `list[tuple[str, SecretStr]]`. |
| 7 | **`__repr__` cookie-count side-channel** | LOW | T-001 pins the count-only mask (acceptable 1-bit side-channel; the operator's `ls -la .env` is richer). |
| 8 | **The 3 new env vars leak via process listings** (`/proc/<pid>/environ`) | LOW | Same risk as `LINKEDIN_LI_AT`; mitigated by `direnv` (per v1 README). |
| 9 | **`is_cloudflare_challenge` fires a false positive on a healthy SERP** | LOW | T-003 + T-004 cards-win rule + 3 negative scenarios in the test. A healthy SERP with cards never matches. |
| 10 | **V1 lessons not applied** (e.g. `__init__.py` re-export hub, real cookie value) | LOW | AGENTS.md rule #4 + rule #7 enforced at every T-XXX. |

## 9. Rollback plan

Each task is independently revertible with `git revert <commit-sha>`:

- **T-001 revert**: removes the `LinkedInAuthCookiesPort` Protocol + the `MultiEnvLinkedInAuthCookiesAdapter` + the `FakeLinkedInAuthCookiesPort` + the 13 new tests. The v1 `EnvLinkedInAuthCookieAdapter` + v1 `FakeLinkedInAuthCookiePort` are byte-identical. The 35 v1 tests stay green.
- **T-002 revert**: removes the 3 new `Settings.linkedin_*` fields + the 2 shared validator helpers. The v1 `linkedin_li_at` field + 2 v1 inline validators are REFACTORED back (the diff is symmetric; the apply phase keeps the refactor reversible). The 35 v1 tests stay green.
- **T-003 revert**: removes `is_cloudflare_challenge` + the `CLOUDFLARE_CHALLENGE_HTML` fixture + the 5 new tests. The scraper does NOT call the function yet; the 35 v1 tests stay green.
- **T-004 revert**: removes the `stealth` ctor kwarg + the `_stealth` slot + the `apply_stealth_async(ctx)` call + the multi-cookie `add_cookies` + the `auth_cookies` + `stealth` settings slots + the closure `is_cloudflare_challenge` integration. The v1 `auth_cookie` slot + ctor kwarg are KEPT; the v1 anonymous closure path is byte-identical; the v1 single-cookie `add_cookies` literal is restored. The 35 v1 tests stay green.
- **T-005 revert**: removes the multi-cookie wire + the `Stealth()` wire + the extended 4-`None` startup WARNING + the integration tests + the `.env.example` lines + the `README.md` subsection. The v1 `EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)` wire is restored; the 35 v1 tests stay green.

**Zero-downtime rollback**: leaving all 4 `LINKEDIN_*` env vars empty in `.env` runs the scraper anonymously (v1 behavior) without redeploy. The composition root kwarg default preserves v1 behavior at runtime.

## 10. Anti-patterns explicitly avoided

- **No `__init__.py` business logic** (AGENTS.md rule #4) — the `infrastructure/linkedin/__init__.py` stays docstring-only; the new modules contain real code.
- **No real LinkedIn cookie value in any committed file** (AGENTS.md rule #7) — only the synthetic 12-byte `"AQEAAAAQEAAA"` + `"ajax:12345"` + `"v2_xyz"` + `"gc_abc"` sentinels appear in test code.
- **No global `os.environ['LINKEDIN_*']` read in the scraper** — the composition root is the only site that knows about env vars; the scraper receives the port + the `Settings` (or the values extracted from it).
- **No log of the cookie value at any level** — `__repr__` masks the count only; DEBUG uses `count=%d`; the WARNING message names the 3 missing cookies (env-var names) but not any value.
- **No test that requires a live network call to LinkedIn or Cloudflare** (AGENTS.md rule #1) — all tests are offline with fixtures; the `CLOUDFLARE_CHALLENGE_HTML` fixture is committed.
- **No `playwright-stealth` import at the top of `scraper.py` without the `await stealth.apply_stealth_async(ctx)` call site also present** — the import + the call site ship in the same commit (T-004).
- **No modification of `JobSearchPort`, `LocationResolverPort`, `JobSearchCacheKey`, `paginated_search`** — these are source-agnostic and stay UNCHANGED.
- **No modification of `is_block_page` or `is_auth_wall`** — 3 distinct functions with 3 distinct semantics stay byte-identical.
- **No modification of the v1 `Settings.linkedin_li_at` field or its 2 inline validators** — REFACTORED to delegate (no behavior change).
- **No breaking of the v1 single-cookie `EnvLinkedInAuthCookieAdapter` ctor** — kept byte-identical.
- **No changing of the v1 closure's anonymous path** — byte-identical to v1 (the v1 `test_search_raises_blocked_on_auth_wall` is the regression check).
- **No new exception type for the Cloudflare-challenge path** — soft path returns `[]` + WARNING.
- **No `Co-Authored-By:` trailer or AI attribution** (AGENTS.md rule #6) — conventional commits only.

## 11. Open questions

- **None** — all 5 design-level questions (Q1-Q5) from explore obs #365 §6 are auto-resolved by the orchestrator. The 0.55 confidence on `playwright-stealth` is the documented open risk.

## 12. Commit plan

| Task | Commit subject |
|---|---|
| T-001 | `feat(linkedin-stealth): add LinkedInAuthCookiesPort + MultiEnvAdapter + test double` |
| T-002 | `feat(linkedin-stealth): add Settings.linkedin_{jsessionid,bcookie,li_gc} + shared validators` |
| T-003 | `feat(linkedin-stealth): add is_cloudflare_challenge defensive detector` |
| T-004 | `feat(linkedin-stealth): inject playwright-stealth + extend closure precedence` |
| T-005 | `feat(composition): wire multi-cookie + operator docs` |

5 conventional commits, single PR, no chained PRs.

## 13. Review Workload Forecast

> **This section is mandatory and is the input to the orchestrator's Review Workload Guard.**

| Metric | Value |
|---|---|
| Total new lines (sum of all task LOC estimates) | ~543 |
| Total modified lines | -15 (the v1 single-cookie wiring is replaced) |
| Total net lines touched (rough: new + modified) | ~528 |
| Review budget (cached) | 5,000 |
| Budget utilization | ~10.6% |
| Work-unit count | 5 |
| Files added | 4 (`test_linkedin_stealth.py`, `test_linkedin_cloudflare_challenge.py`, `test_linkedin_stealth.py` integration, `CLOUDFLARE_CHALLENGE_HTML` is MODIFIED in the existing fixtures file) |
| Files modified | 11 (ports.py, auth_cookie.py, parsers.py, scraper.py, config.py, app_factory.py, conftest.py, .env.example, README.md, fixtures/linkedin_search.py, test_linkedin_scraper.py, test_linkedin_config.py, test_linkedin_auth_cookie.py) |
| Tests added | ~27 (10 stealth adapter + 5 cloudflare detector + 3 v1 backward-compat + 4 closure precedence + 5 config) |
| Docs added | 2 (`.env.example` +3 LOC, `README.md` +30 LOC) |
| Chained PRs recommended | **No** (single PR is sufficient; well-bounded, ~528 LOC, orthogonally scoped) |
| 400-line budget risk | **Low** (~105 LOC/commit avg; well under the 400-line per-commit sub-budget) |
| Decision needed before apply | **No** (no design-level decisions remain; budget is Low; v1 cycle used the same single-PR strategy successfully) |
| Predicted delivery strategy | `single-pr` (5 conventional commits) |
| Predicted chain strategy | N/A (single PR; no chaining) |

**Guard lines** (per sdd-phase-common §E):
```
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: N/A
400-line budget risk: Low
```
