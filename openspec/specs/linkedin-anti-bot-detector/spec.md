# Spec: `linkedin-anti-bot-detector` — `is_cloudflare_challenge(soup)` defensive detector

> **PROMOTED to source of truth on 2026-06-11** from
> `openspec/changes/backend-linkedin-stealth/spec.md`
> §"Capability: `linkedin-anti-bot-detector` (NEW)" (Domain 1
> of the multi-capability delta spec).
>
> This is a NEW foundational capability spec — no prior
> `openspec/specs/linkedin-anti-bot-detector/spec.md` existed.
> The delta is promoted in full as the foundational spec for
> the capability, capturing the pure `is_cloudflare_challenge(soup)`
> function, the `CLOUDFLARE_CHALLENGE_HTML` fixture, the
> semantic split with the v1 `is_block_page` and `is_auth_wall`
> detectors, and the "cards win" false-positive suppression
> rule. Source observation IDs for traceability: explore #365,
> proposal #366, spec #367, design #368, tasks #369,
> apply-progress #370, verify-report #371.
>
> **Status of the upstream feature**: the live smoke test
> against real LinkedIn + Cloudflare-2026 (per
> `verify-report` obs #371 §4) returned `HTTP 502` with
> `ERR_TOO_MANY_REDIRECTS` in <5s with the operator's
> fresh cookies + `playwright-stealth`. The detector itself is
> correctly implemented (3/3 negative scenarios + 1/1 positive
> scenario pass with the `CLOUDFLARE_CHALLENGE_HTML` fixture);
> the operational outcome is that LinkedIn's anti-bot closes
> the connection BEFORE the page renders as HTML, so the
> detector never has a chance to fire on the live request. The
> documented follow-up is `backend-linkedin-xvfb` (a real
> browser under Xvfb to get a non-headless TLS fingerprint).

## Purpose

The `linkedin-anti-bot-detector` capability is the
**network-layer-anti-bot surfacing safety net** for the
LinkedIn scraper. When the operator has configured at least one
`LINKEDIN_*` auth cookie AND `playwright-stealth` (the v1
extension shipped by this same change), the scraper injects
the cookies and applies stealth on the Playwright
`BrowserContext` (per `linkedin-scraper` §REQ-LST-SCR-001 + §
REQ-LST-SCR-002). If Cloudflare is challenging the request at
the network layer (the 2026 "Just a moment..." challenge page
or the 302-loop), the operator gets NO HTML back — without an
operator signal, the operator would not know the upstream is
blocked and the scraper is degraded.

The `is_cloudflare_challenge(soup)` function detects the
Cloudflare challenge variant at the closure level (per page)
and emits a WARNING log line. The function is distinct from
the pre-existing v1 `is_block_page(soup)` (the 502 hard-raise
path) and the v1 `is_auth_wall(soup)` (the soft-path
auth-walled-with-cookie WARNING). The three functions coexist
with distinct semantics:

- `is_block_page` — v1 hard-raise (anonymous path, unchanged)
- `is_auth_wall` — v1 soft-WARNING (cookie path, unchanged)
- `is_cloudflare_challenge` — NEW soft-WARNING (cookie path,
  fires BEFORE `is_auth_wall` and `is_block_page` per the
  cookie-path precedence in `linkedin-scraper`
  §REQ-LST-SCR-003)

The capability is the **detection seam** between the parser
(BS4 selectors for the Cloudflare 2026 challenge markers) and
the scraper's per-page closure. The function is pure (no I/O,
no `await`, no logging side-effects); the WARNING emission is
the caller's responsibility (in the `_make_fetch_one_page`
closure).

## Requirements

### REQ-LST-CF-001 — `is_cloudflare_challenge(soup)` is a pure function

The function
`is_cloudflare_challenge(soup: BeautifulSoup) -> bool` MUST be
a pure function in
`backend/src/jobs_finder/infrastructure/linkedin/parsers.py`,
defined next to the v1 `is_block_page` and `is_auth_wall`
functions. "Pure" means: no I/O, no `await`, no module-level
mutable state, no logging side-effects. The function does NOT
import `logging` and does NOT emit log records. The function
does NOT mutate the input `soup` (pure read — verified by
`soup.prettify()` byte-for-byte equality before vs. after).

Mirrors the v1 `is_block_page` + `is_auth_wall` precedent
(per the `linkedin-auth-wall-detector` spec §REQ-LA-AWALL-001).
A pure function is trivially testable offline with the new
`CLOUDFLARE_CHALLENGE_HTML` fixture (no Playwright, no async).
The distinct semantics — Cloudflare's 302-loop challenge at
the network/JS layer (not LinkedIn's auth wall, not the
LinkedIn 502 block) — is the third detector in the suite.

#### Scenario: is_cloudflare_challenge signature is (soup: BeautifulSoup) -> bool

- **GIVEN** `is_cloudflare_challenge` is imported from
  `jobs_finder.infrastructure.linkedin.parsers`
- **WHEN** `inspect.signature(is_cloudflare_challenge)` is
  introspected
- **THEN** returns `(soup: BeautifulSoup) -> bool`
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_signature`
  passes

#### Scenario: is_cloudflare_challenge is pure (no mutation)

- **GIVEN** `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser"))`
  is called
- **WHEN** the result is captured AND `soup.prettify()` is
  called again
- **THEN** returns `True` AND the post-call `soup.prettify()` is
  byte-identical to the pre-call
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_is_pure_no_mutation`
  passes

### REQ-LST-CF-002 — `is_cloudflare_challenge` returns `True` for the `CLOUDFLARE_CHALLENGE_HTML` fixture

`is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML))`
MUST return `True`. The new `CLOUDFLARE_CHALLENGE_HTML`
fixture (in `backend/tests/fixtures/linkedin_search.py`) is a
string containing the Cloudflare 2026 challenge signature —
the `<title>Just a moment...</title>` element AND/OR the
`<noscript>` redirect message AND/OR a `cf-mitigated`
challenge marker (the exact selector set is pinned in the
test). The detector MUST match at least ONE of the pinned
Cloudflare 2026 selectors.

The fixture is the canonical "Cloudflare 302-loop page"
representation (per `explore` obs #365 §2.9 + the Indeed
precedent at `tests/fixtures/indeed_search.py:BLOCKED_PAGE_HTML`
that was proved against the live Cloudflare variant per
obs #74). Captured offline — committed, no live network
(AGENTS.md rule #1).

#### Scenario: is_cloudflare_challenge True for challenge fixture

- **GIVEN** the `CLOUDFLARE_CHALLENGE_HTML` string from
  `tests/fixtures/linkedin_search.py` (a Cloudflare 2026
  challenge page with `<title>Just a moment...</title>` and a
  `<noscript>` redirect block)
- **WHEN**
  `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser"))`
  is called
- **THEN** returns `True`
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_true_for_challenge_fixture`
  passes

#### Scenario: fixture contains the 3 pinned Cloudflare 2026 markers

- **GIVEN** the `CLOUDFLARE_CHALLENGE_HTML` string
- **WHEN** the fixture is parsed and inspected
- **THEN** it contains all 3 pinned Cloudflare 2026 markers:
  `<title>Just a moment...</title>`, a `<noscript>` redirect
  block, and a `div.cf-mitigated[data-cf-challenge]` (or
  equivalent) marker
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_fixture_contains_three_cloudflare_markers`
  passes

### REQ-LST-CF-003 — `is_cloudflare_challenge` returns `False` for healthy SERP, `BLOCK_PAGE_HTML`, and cards-win edge case

The detector MUST return `False` on three independent inputs
to prevent false positives:

1. The v1 `SEARCH_PAGE_HTML` fixture (a healthy SERP with 3+
   `<div data-entity-urn="...">` job cards).
2. The v1 `BLOCK_PAGE_HTML` fixture (LinkedIn's
   `<body class="auth-wall">` page — a different anti-bot
   signal owned by the v1 `is_auth_wall` detector).
3. An HTML fragment containing BOTH a Cloudflare challenge
   marker AND at least one job card
   (`<div data-entity-urn="...">`) — the "cards win" rule
   suppresses the false positive (same pattern as v1
   `is_auth_wall` per `REQ-LA-AWALL-004`).

Per `explore` obs #365 risk #9: a false positive on a healthy
SERP would break the operator UX (the scraper returns `[]`
when actually a valid SERP rendered). Per the v1 `is_auth_wall`
precedent, the "cards win" rule is the load-bearing
false-positive suppression. The detector and the v1
`is_auth_wall` are **distinct signals** for distinct anti-bot
layers — a healthy SERP with `class="auth-wall"` as defensive
markup is a known LinkedIn pattern.

#### Scenario: is_cloudflare_challenge False for healthy SERP

- **GIVEN** the v1 `SEARCH_PAGE_HTML` fixture (healthy SERP
  with 3+ job cards, no Cloudflare markers)
- **WHEN**
  `is_cloudflare_challenge(BeautifulSoup(SEARCH_PAGE_HTML, "html.parser"))`
  is called
- **THEN** returns `False`
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_false_for_healthy_serp`
  passes

#### Scenario: is_cloudflare_challenge False for LinkedIn block page

- **GIVEN** the v1 `BLOCK_PAGE_HTML` fixture (LinkedIn auth
  wall, NOT Cloudflare)
- **WHEN**
  `is_cloudflare_challenge(BeautifulSoup(BLOCK_PAGE_HTML, "html.parser"))`
  is called
- **THEN** returns `False` (the `is_auth_wall` detector is
  the correct signal for this HTML)
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_false_for_linkedin_block_page`
  passes

#### Scenario: cards win (false positive suppression)

- **GIVEN** an HTML fragment
  `<body><title>Just a moment...</title><div data-entity-urn="urn:li:jobPosting:1"></div></body>`
  (Cloudflare title + 1 card)
- **WHEN**
  `is_cloudflare_challenge(BeautifulSoup(fragment, "html.parser"))`
  is called
- **THEN** returns `False` (cards win — false positive
  suppressed)
- **AND** the test
  `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_false_when_cards_present_even_with_challenge_marker`
  passes

## Out of scope

- **Replacing `is_block_page` or `is_auth_wall`** — they have
  distinct semantics and coexist; `is_block_page` is preserved
  untouched (the v1 502 hard-raise path) and `is_auth_wall` is
  preserved untouched (the v1 soft-WARNING cookie-path).
- **Detectors for other anti-bot vendors** (DataDome,
  PerimeterX, Akamai) — each new source/vendor is its own
  follow-up change.
- **A `linkedin-redirect-loop` exception class** — the live
  outcome (`ERR_TOO_MANY_REDIRECTS`) is a transport-level
  reject that surfaces as `Page.goto` failure BEFORE the page
  ever renders. The `is_cloudflare_challenge` detector only
  fires when the page renders. The redirect-loop case is
  handled by the upstream Playwright error path (the
  `LinkedInTimeoutError` raise). Documented in
  `verify-report` obs #371 §4.
- **The `_make_fetch_one_page` closure integration** — owned
  by the `linkedin-scraper` capability spec
  (§REQ-LST-SCR-003 + §REQ-LST-SCR-004). This spec covers the
  detector; the integration is a separate concern.
- **The `LinkedInAuthCookiesPort` (plural) Protocol** — owned
  by the `linkedin-auth-cookie` capability spec.
- **The `playwright-stealth` injection in `search()`** — owned
  by the `linkedin-scraper` capability spec (§REQ-LST-SCR-001).
- **The 3 new `Settings.linkedin_*` env vars** — owned by the
  `linkedin-config` capability spec.
- **Live test against real LinkedIn** — NOT required for the
  detector; the detector is validated offline via the
  `CLOUDFLARE_CHALLENGE_HTML` fixture. The live smoke test
  outcome is documented separately in the verify-report
  (obs #371).

## Source of truth links

- **Delta spec source**:
  `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
  (Domain 1 of the multi-capability delta)
- **Sibling capabilities** (also promoted in the same archive):
  - `openspec/specs/linkedin-auth-cookie/spec.md` — EXTENDED
    with `REQ-LST-COOKIE-001..005` (the multi-cookie Protocol
    + `MultiEnvLinkedInAuthCookiesAdapter` + deterministic
    order + repr mask)
  - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED with
    `REQ-LST-SCR-001..004` (stealth injection + multi-cookie
    injection + closure precedence + Cloudflare WARNING)
  - `openspec/specs/linkedin-config/spec.md` — EXTENDED with
    `REQ-LST-CFG-001..003` (3 new optional SecretStr fields +
    shared validator + repr no-leak)
- **Precedent**:
  `openspec/specs/linkedin-auth-wall-detector/spec.md`
  (the v1 `is_auth_wall` precedent for the pure function +
  "cards win" rule + soft-WARNING integration pattern)
- **Open discoveries** (linked to this spec but not closed by
  it):
  - `discovery/linkedin-fingerprinting-vs-rate-limit-hypothesis`
    (obs #373) — the live outcome may be rate-limiting, not
    fingerprinting; the orchestrator's "fingerprinting"
    diagnosis is a hypothesis, not validated.
  - `discovery/linkedin-redirect-loop-cookies-not-the-cause`
    (obs #374) — fresh cookies were tested; cookies are NOT
    the root cause. The redirect loop completes in <5s, not
    10s (the 10s timeout was masking the real failure mode).
