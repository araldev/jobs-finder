# Spec: `linkedin-auth-wall-detector` — `is_auth_wall(soup)` defensive detector

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/backend-linkedin-auth/spec.md`
> §"Capability: `linkedin-auth-wall-detector` (NEW)" (Domain 4
> of the multi-capability delta spec).
>
> This is a NEW capability delta — no prior
> `openspec/specs/linkedin-auth-wall-detector/spec.md` existed.
> The delta is promoted in full as the foundational spec for
> the capability, capturing the pure `is_auth_wall(soup)`
> function, the semantic split with the pre-existing
> `is_block_page(soup)`, the integration in the
> `_make_fetch_one_page` closure, and the soft-path
> (WARNING + return `[]`, do NOT raise) contract for
> cookie-injected auth-wall variants. Source observation IDs
> for traceability: explore #353, proposal #354, spec #355,
> design #356, tasks #357, apply-progress #358, verify-report
> #360.

## Purpose

The `linkedin-auth-wall-detector` capability is the
**operator-observability safety net** for the LinkedIn
scraper's cookie-injection path. When the operator has
configured a `LINKEDIN_LI_AT` cookie, the scraper injects it
into the Playwright `BrowserContext` (per the
`linkedin-scraper` §REQ-LA-SCR-001..006). If the cookie is
expired, the SERP renders an auth-wall variant (the `<body
class="auth-wall">` class is present) and the user sees 0
results — without an operator signal, the operator would not
know the cookie expired and the scraper is degraded.

The `is_auth_wall(soup)` function detects this auth-wall
variant at the closure level (per page) and emits a WARNING
log line. The function is distinct from the pre-existing
`is_block_page(soup)` (which is the 502 hard-raise path —
used by the v1 anonymous scraper). The two functions coexist:
`is_block_page` is the v1 hard-raise (anonymous path,
unchanged); `is_auth_wall` is the new soft-WARNING
(cookie-injection path).

The capability is the **detection seam** between the parser
(BS4 selectors) and the scraper's per-page closure. The
function is pure (no I/O, no await, no logging side-effects);
the WARNING emission is the caller's responsibility (in the
`_make_fetch_one_page` closure).

## Requirements

### REQ-LA-AWALL-001 — `is_auth_wall(soup)` is a pure function

The function `is_auth_wall(soup: BeautifulSoup) -> bool` MUST
be a pure function in
`backend/src/jobs_finder/infrastructure/linkedin/parsers.py`.
Pure means: no I/O, no `await`, no module-level mutable
state, no logging side-effects. The function's only inputs
are its `soup` argument; its only output is a `bool`.

Mirrors the v1 `is_block_page` precedent (lines 213-242 of
`parsers.py`). A pure function is trivially testable with
the existing `BLOCK_PAGE_HTML` and `SEARCH_PAGE_HTML`
fixtures (no Playwright, no async). The semantic split
between `is_block_page` (0 cards + auth signals = 502 path)
and `is_auth_wall` (auth-wall class + 0 cards = WARNING
path) is load-bearing for the operator observability value
(per Q3 in the proposal).

The function does NOT mutate the input `soup` (pure read);
the function does NOT import `logging` and does NOT emit log
records.

#### Scenario: is_auth_wall signature is (soup: BeautifulSoup) -> bool

- **GIVEN** `is_auth_wall` is imported from `jobs_finder.infrastructure.linkedin.parsers`
- **WHEN** `inspect.signature(is_auth_wall)` is introspected
- **THEN** returns `(soup: BeautifulSoup) -> bool`
- **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_signature` passes

#### Scenario: is_auth_wall is pure (no mutation)

- **GIVEN** `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` is called
- **WHEN** the result is captured
- **THEN** it returns `True` (the BLOCK_PAGE_HTML fixture has `<body class="auth-wall">`)
- **AND** the input `soup` is NOT mutated (`soup.prettify()` after the call returns the same bytes as before)
- **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_is_pure_no_mutation` passes

### REQ-LA-AWALL-002 — `is_auth_wall` returns `True` for the `BLOCK_PAGE_HTML` fixture

`is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` MUST return
`True`. The existing `BLOCK_PAGE_HTML` fixture
(`backend/tests/fixtures/linkedin_search.py:80-98`) has
`<body class="auth-wall">` AND zero job cards — both
conditions required by the new detector.

The fixture is the canonical "auth wall with no results"
representation. Reusing the fixture for the new detector
(the v1 `is_block_page` already uses it) keeps the test
suite consistent and proves the two functions are testing
distinct semantics on the same HTML.

#### Scenario: is_auth_wall True for BLOCK_PAGE_HTML fixture

- **GIVEN** the `BLOCK_PAGE_HTML` string from `tests/fixtures/linkedin_search.py`
- **WHEN** `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML, "html.parser"))` is called
- **THEN** returns `True`
- **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_true_for_block_page_fixture` passes

### REQ-LA-AWALL-003 — `is_auth_wall` returns `False` for a healthy SERP

`is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML))` MUST return
`False`. The existing `SEARCH_PAGE_HTML` fixture (per
`tests/fixtures/linkedin_search.py:21-78`) is a healthy SERP
with multiple `<div data-entity-urn="...">` job cards and NO
`<body class="auth-wall">` — the detector's "cards win, no
false positive" rule returns `False`.

The semantic split between `is_block_page` (502 path) and
`is_auth_wall` (WARNING path) requires that healthy SERPs do
NOT trigger the new detector. The `SEARCH_PAGE_HTML` fixture
is the canonical healthy SERP and the contract anchor.

#### Scenario: is_auth_wall False for healthy SERP

- **GIVEN** the `SEARCH_PAGE_HTML` string from `tests/fixtures/linkedin_search.py`
- **WHEN** `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML, "html.parser"))` is called
- **THEN** returns `False` (no `auth-wall` class on the body; job cards present, so the `body.auth-wall` selector matches nothing relevant)
- **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_false_for_healthy_serp` passes

### REQ-LA-AWALL-004 — `is_auth_wall` returns `False` when cards are present even with auth-wall class (cards win)

When the parsed HTML has BOTH a `body.auth-wall` (or
`.auth-wall` descendant) AND at least one job card (`<div
data-entity-urn="...">`), the function MUST return `False` —
cards win, the auth-wall class is a false positive
(defensive markup from LinkedIn on a session that DOES see
results).

The pre-change `is_block_page` already pins this "cards win"
rule (per `parsers.py:233-234` and its scenario
`test_is_block_page_false_when_cards_present`). The new
`is_auth_wall` MUST use the same rule so the two functions
share semantics and produce consistent verdicts on the same
HTML. The rule prevents false-positive WARNINGs on healthy
SERPs that happen to render the `auth-wall` class on a
sub-element.

#### Scenario: cards present suppresses auth-wall false positive

- **GIVEN** an HTML fragment `<body class="auth-wall"><div data-entity-urn="urn:li:jobPosting:1"></div></body>` (auth-wall class + 1 card)
- **WHEN** `is_auth_wall(BeautifulSoup(fragment, "html.parser"))` is called
- **THEN** returns `False` (cards win, the auth-wall signal is a false positive)
- **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class` passes

### REQ-LA-AWALL-005 — `is_auth_wall` WARNING log inside `_make_fetch_one_page`

Inside `LinkedInPlaywrightScraper._make_fetch_one_page`, the
closure MUST check `is_auth_wall(soup)` and emit a single
WARNING log line when it returns `True`. The WARNING message
MUST be
`"LinkedIn SERP appears auth-walled despite cookie injection; cookie
may be expired. Returning <N> jobs from this page (degraded)."`
where `<N>` is `len(jobs)` from the parsed page (the value
the page WOULD return). The closure MUST continue parsing
and return the parsed jobs (does NOT raise, does NOT
short-circuit).

The WARNING is the operator signal that the cookie may be
expired (the auth wall is showing despite the cookie). The
scraper still returns the partial results so the user sees
degraded-but-not-empty responses (matching the v1
partial-results contract on rate-limit responses).

**Conditional precedence (archive note)**: The apply phase
implements the WARNING path with a **conditional precedence
flip** between `is_block_page` and `is_auth_wall`:

- **Cookie-injection path** (`auth_cookie is not None`):
  `is_auth_wall` is checked FIRST (soft path → WARNING + return
  `[]`). `is_block_page` is checked SECOND (only fires on a
  genuine hard block that survived the soft filter — extremely
  rare).
- **Anonymous path** (`auth_cookie is None`, the v1
  zero-config default): `is_block_page` is checked FIRST
  (hard path → raise `LinkedInBlockedError`). `is_auth_wall`
  is NOT consulted (the v1 test
  `test_search_raises_blocked_on_auth_wall` is preserved
  unchanged).

The conditional gate is the v1-vs-cookie discriminator. The
spec contract is fully satisfied by both branches; the
deviation from design §2.6's ordering is documented in
`openspec/changes/archive/2026-06-10-backend-linkedin-auth/design.md`
§"11. Deviations from Design".

The WARNING is emitted ONCE per page that triggers it (not
per `search()` — a multi-page search can hit the wall on a
subset of pages).

#### Scenario: closure warns on auth_wall + 0 cards (cookie path)

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` AND a `FakeBrowser` that returns `BLOCK_PAGE_HTML`-shaped HTML with 0 cards (auth wall with 0 cards)
- **WHEN** `search()` runs AND `caplog` is set to level `WARNING`
- **THEN** the closure logs the WARNING `"LinkedIn SERP appears auth-walled despite cookie injection; cookie may be expired. Returning 0 jobs from this page (degraded)."`
- **AND** `search()` returns `[]` (the empty list, NOT an exception)
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_warns_on_auth_wall_zero_cards` passes

#### Scenario: closure does NOT warn when cards present (cards win)

- **GIVEN** a `FakeBrowser` that returns `BLOCK_PAGE_HTML`-shaped HTML with 3 cards (the edge case: auth wall signal + cards present)
- **WHEN** `search()` runs
- **THEN** NO WARNING is emitted (the "cards win" rule from `REQ-LA-AWALL-004`)
- **AND** `search()` returns the 3 parsed jobs
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_does_not_warn_when_cards_present_with_auth_wall_class` passes (false-positive suppression at the closure level)

### REQ-LA-AWALL-006 — `is_auth_wall` does NOT raise; an auth-walled page returns whatever was collected

When `is_auth_wall(soup) is True` AND the page yields 0
cards, the scraper MUST return `[]` (an empty list) — NOT
raise a `LinkedInParseError`, NOT raise a
`LinkedInBlockedError`. The WARNING is the operator signal;
the empty list is the response contract.

This is a deviation from `is_block_page`'s
`LinkedInBlockedError` raise (the 502 path). The deviation
is intentional: an auth wall detected despite a cookie
injection is a soft failure (operator can rotate the
cookie); the `LinkedInBlockedError` raise would be a hard
failure (route returns 502). The spec deliberately keeps the
response graceful — the user gets an empty list (matching
the v1 anonymous-path behavior) instead of a 502.

The behavior is consistent with the v1 anonymous-path
contract: an anonymous search hitting the auth wall returns
`[]` with no WARNING (the v1 path's only signal is the hard
raise via `is_block_page` if the page is a true hard block);
an auth-cookie search hitting the auth wall returns `[]`
WITH WARNING (per `REQ-LA-AWALL-005`).

#### Scenario: closure returns empty list on auth_wall (no raise)

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` AND a `FakeBrowser` that returns `BLOCK_PAGE_HTML` HTML (auth wall, 0 cards) for every page
- **WHEN** `search("react", "Madrid", limit=20)` runs
- **THEN** returns `[]` (an empty list, not an exception)
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_returns_empty_list_on_auth_wall_no_raise` passes

## Out of scope

- **Replacing `is_block_page` with `is_auth_wall`** — they
  have distinct semantics and coexist; `is_block_page` is
  preserved untouched (the 502 hard-raise path is the v1
  contract).
- **Programmatic login / auto-refresh / OAuth** — out of
  scope; the operator rotates the cookie manually when the
  WARNING fires.
- **DB / Redis persistence of the auth-wall state** — the
  WARNING is the only signal; the scraper does not persist
  any state across `search()` calls.
- **The `LinkedInAuthCookiePort` Protocol and
  `EnvLinkedInAuthCookieAdapter`** — owned by the
  `linkedin-auth-cookie` capability spec.
- **The `Settings.linkedin_li_at` field** — owned by the
  `linkedin-config` capability spec.
- **The per-context `ctx.add_cookies` injection in
  `search()`** — owned by the `linkedin-scraper` capability
  spec.
- **Live test against real LinkedIn** — NOT required; the
  detector is validated offline via the `BLOCK_PAGE_HTML` and
  `SEARCH_PAGE_HTML` fixtures.

## Source of truth links

- **Delta spec source**: `openspec/changes/archive/2026-06-10-backend-linkedin-auth/spec.md` (Domain 4 of the multi-capability delta)
- **Sibling capabilities** (also promoted in the same archive):
  - `openspec/specs/linkedin-auth-cookie/spec.md` — NEW with `REQ-LA-COOKIE-001..004`
  - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED with `REQ-LA-SCR-001..006` (cookie injection in `search()`)
  - `openspec/specs/linkedin-config/spec.md` — EXTENDED with `REQ-LA-CFG-001..004`
- **Deviation note**: `openspec/changes/archive/2026-06-10-backend-linkedin-auth/design.md` §"11. Deviations from Design" (the conditional precedence flip between `is_block_page` and `is_auth_wall` is documented here)
