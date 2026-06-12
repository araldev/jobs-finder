# Spec: `linkedin-scraper` — `LinkedInPlaywrightScraper` URL Builder + Cookie Injection (EXTENDED)

> **EXTENDED on 2026-06-10** from the foundational
> `linkedin-scraper` spec promoted on 2026-06-10 from
> `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/specs/backend-linkedin-location-fallback/spec.md`
> (Domain 2, archived in
> `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/`).
>
> The foundational spec covered the URL builder (item 1: the
> 3-branch priority `geoId > structured > raw`, 4 REQ-LI-SCR-*).
> This delta ADDS 6 REQ-LA-SCR-001..006 (the cookie-plumb
> requirements for the `li_at` session cookie injection) on top
> of the pre-existing 4 REQ-LI-SCR-001..004 (URL builder). The
> pre-existing REQs are preserved verbatim below. Source
> observation IDs for the cookie delta: explore #353, proposal
> #354, spec #355, design #356, tasks #357, apply-progress
> #358, verify-report #360. Source observation IDs for the
> foundational spec: explore #332, proposal #333, spec #336,
> design #338, tasks #340, apply-progress #345, verify-report
> #348.

## Purpose

`LinkedInPlaywrightScraper` (in
`backend/src/jobs_finder/infrastructure/linkedin/scraper.py`) is
the adapter of Playwright for the LinkedIn job-search portal. Its
responsibility is to:

1. Build the search URL with the correct query parameters.
2. Open a fresh browser context + page.
3. **Inject the operator's `li_at` session cookie** (this
   delta's `REQ-LA-SCR-001..006`) BEFORE the first navigation,
   when the operator has configured one.
4. Drive the auto-pagination loop via the shared
   `paginated_search` helper.
5. Detect auth-wall variants and emit a WARNING (the
   `linkedin-auth-wall-detector` capability's
   `REQ-LA-AWALL-001..006`).
6. Parse each page into a `list[Job]`.

This spec covers items 1 (URL builder) and 3 (cookie
injection). The pagination loop, the `paginated_search` helper,
the parser, and the browser lifecycle are out of scope for
this spec (covered by upstream change
`backend-scraper-query-tuning`, archived 2026-06-09, and the
pre-change LinkedIn scraper baseline).

---

## Foundational requirements (UNCHANGED — promoted 2026-06-10)

### REQ-LI-SCR-001 — `_build_url` prioridad `geoId > structured > raw`

The `_build_url` method (private) MUST accept two kwargs:
`geo_id: int | None = None` (pre-existing, from
`backend-scraper-query-tuning`) and `structured: tuple[str, str, str] | None = None`
(NUEVO, from the location-fallback change). The priority MUST be:

1. **Si `geo_id is not None`**: `?keywords={k}&geoId={int}&start={s}`
   (existing — the most precise; `geoId` is LinkedIn's preferred
   format).
2. **Si `structured is not None`**: `?keywords={k}&location={quote(city,province,country)}&start={s}`
   (NUEVO — triplet estructurado).
3. **Si ninguno**: `?keywords={k}&location={quote(raw)}&start={s}`
   (existing — legacy fallback for cities without any mapping).

The structured location format MUST be
`f"{city},{province},{country}"` (3 parts, comma-separated, Title
Case with NFC tildes) and MUST be URL-encoded with
`urllib.parse.quote` (default `safe="/"`), which encodes the
commas as `%2C` and the tildes (NFC composed `í` = U+00ED) as
`%C3%AD` (UTF-8 multibyte). The encoding reproduces byte-for-byte
the user-captured URL `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain`.

#### Scenario: `geoId` toma priority sobre `structured`

- **GIVEN** ambos `geo_id=103374081` (Madrid) y
  `structured=("Antequera", "Andalucía", "Spain")` están
  disponibles
- **WHEN** se llama `_build_url("react", "Antequera", 0, geo_id=103374081, structured=("Antequera", "Andalucía", "Spain"))`
- **THEN** retorna `https://www.linkedin.com/jobs/search?keywords=react&geoId=103374081&start=0` (NO `location=...`)
- **AND** el test `test_linkedin_scraper.py::test_build_url_geoId_priority_over_structured` pasa

#### Scenario: `structured` toma priority sobre `raw`

- **GIVEN** solo `structured=("Antequera", "Andalucía", "Spain")` está disponible (sin `geo_id`)
- **WHEN** se llama `_build_url("react", "Antequera", 0, geo_id=None, structured=("Antequera", "Andalucía", "Spain"))`
- **THEN** retorna `https://www.linkedin.com/jobs/search?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0`
- **AND** el test `test_linkedin_scraper.py::test_build_url_structured_priority_over_raw` pasa

#### Scenario: legacy fallback cuando ambos son `None`

- **GIVEN** ni `geo_id` ni `structured` están disponibles
- **WHEN** se llama `_build_url("react", "Berlin", 0, geo_id=None, structured=None)`
- **THEN** retorna `https://www.linkedin.com/jobs/search?keywords=react&location=Berlin&start=0` (legacy, sin cambios)
- **AND** el test `test_linkedin_scraper.py::test_build_url_legacy_fallback` pasa (no regresión)

#### Scenario: `start` param se preserva en todas las ramas

- **GIVEN** un search con `start=50` (page 3)
- **WHEN** se llama `_build_url` con `start=50` en las 3 ramas
- **THEN** las 3 URLs terminan con `&start=50` (paginación inalterada)
- **AND** el test `test_linkedin_scraper.py::test_build_url_start_preserved_across_branches` pasa (parametrized: 3 branches × 2 start values)

### REQ-LI-SCR-002 — URL encoding con tildes (NFC) y caracteres especiales

The `?location=City,Province,Country` format MUST URL-encode
tildes as `%C3%AD` (NFC composed, UTF-8 multibyte) and commas
as `%2C`. `urllib.parse.quote` por defecto (con `safe="/"`)
encodea solo los caracteres que no son letras/dígitos/ASCII-safe
(`/`, `:`, `@`, etc.), preservando caracteres Unicode como `í`
que se codifican como UTF-8 multibyte. **Importante**:
`quote(s, safe=",", ...)` NO es correcto — mantendría la coma
como literal en la URL pero rompería el byte-for-byte match con
la URL real del user (que tiene `%2C`).

#### Scenario: tildes en city y province se encodean como UTF-8

- **GIVEN** `structured=("Cádiz", "Andalucía", "Spain")`
- **WHEN** se llama `_build_url("react", "Cadiz", 0, structured=("Cádiz", "Andalucía", "Spain"))`
- **THEN** la URL contiene `location=C%C3%A1diz%2CAndaluc%C3%ADa%2CSpain` (`á` y `í` encoded)
- **AND** el test `test_linkedin_scraper.py::test_build_url_encodes_tildes_cadiz` pasa

#### Scenario: caracteres especiales en province (espacios, multi-word)

- **GIVEN** `structured=("León", "Castilla y León", "Spain")` (province con espacio y multi-word)
- **WHEN** se llama `_build_url` con ese structured
- **THEN** la URL contiene `location=Le%C3%B3n%2CCastilla%20y%20Le%C3%B3n%2CSpain` (espacio → `%20`, `ó` → `%C3%B3`)
- **AND** el test `test_linkedin_scraper.py::test_build_url_encodes_multiword_province` pasa

#### Scenario: URL example real del usuario se reproduce exactamente

- **GIVEN** la URL capturada por el usuario es
  `https://www.linkedin.com/jobs/search?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0`
- **WHEN** se llama `_build_url("react", "Antequera", 0, structured=("Antequera", "Andalucía", "Spain"))`
- **THEN** la URL retornada es **exactamente** la URL real (byte-for-byte)
- **AND** el test `test_linkedin_scraper.py::test_build_url_matches_user_captured_url` pasa (golden assertion)

### REQ-LI-SCR-003 — `search()` consulta AMBOS resolvers una sola vez

`LinkedInPlaywrightScraper.search()` MUST llamar
`resolver.resolve(location)` AND
`resolver.resolve_structured(location)` exactamente UNA vez
(no por página) al inicio de la búsqueda, y capturar los
resultados en el closure de `_make_fetch_one_page`. La URL se
construye una vez con los valores resueltos y se reusa con
`start` cambiando por página (a través del helper compartido
`paginated_search`).

#### Scenario: ambos resolvers se llaman exactamente 1 vez

- **GIVEN** un `_FakeLocationResolver` (test double) que cuenta llamadas
- **WHEN** `LinkedInPlaywrightScraper.search("react", "Antequera", 20)` ejecuta 3 páginas vía `paginated_search`
- **THEN** `fake.resolve.call_count == 1` Y `fake.resolve_structured.call_count == 1` (no 3)
- **AND** el test `test_linkedin_scraper.py::test_resolver_called_once_per_search` pasa

#### Scenario: `structured` se captura en el closure y se reusa

- **GIVEN** `structured=("Antequera", "Andalucía", "Spain")` se resuelve en `search()`
- **WHEN** el closure `_make_fetch_one_page` construye URLs para 3 páginas
- **THEN** las 3 URLs tienen la misma `location=...` y solo cambia `start=0/25/50`
- **AND** el test `test_linkedin_scraper.py::test_structured_closure_reused_across_pages` pasa

### REQ-LI-SCR-004 — Backward compat con wiring sin resolver y con `None` triplet

Si el `LinkedInScraperSettings.location_resolver` es `None`
(legacy wiring pre-`backend-scraper-query-tuning`), el scraper
MUST seguir funcionando con el fallback legacy
`?location=<raw>`. La rama `structured` se omite silenciosamente
(NO raise, NO log spam).

Si `resolver.resolve_structured()` retorna `None` (resolver
existe pero la ciudad no tiene mapping estructurado), el
scraper MUST caer al legacy `?location=<raw>`. NO raise, NO
log spam.

#### Scenario: scraper sin resolver cae al legacy

- **GIVEN** `LinkedInScraperSettings(location_resolver=None)` (legacy pre-`backend-scraper-query-tuning` wiring)
- **WHEN** se llama `LinkedInPlaywrightScraper.search("react", "Antequera", 20)` (sin resolver en absoluto)
- **THEN** la URL usa `?location=Antequera` (legacy fallback intacto, no `?location=Antequera,...`)
- **AND** el test `test_linkedin_scraper.py::test_legacy_wiring_without_resolver` (existente, de `backend-scraper-query-tuning`) sigue GREEN
- **AND** el test `test_linkedin_scraper.py::test_no_resolver_skips_structured_silently` pasa (NUEVO, específico para este change)

#### Scenario: `resolve_structured` retorna `None` cae al legacy (resolver existe pero ciudad sin mapping)

- **GIVEN** `_FakeLocationResolver` configurado con `resolve_structured.return_value = None` para `"Berlin"`
- **WHEN** se llama `search("react", "Berlin", 20)`
- **THEN** la URL usa `?location=Berlin` (legacy, no 500, no raise)
- **AND** el test `test_linkedin_scraper.py::test_resolve_structured_none_falls_to_legacy` pasa

---

## New requirements (this delta — added 2026-06-10)

### REQ-LA-SCR-001 — `search()` reads the cookie from the injected port (not from env, not from globals)

`LinkedInPlaywrightScraper.search()` MUST read the `li_at`
cookie from `self._settings.auth_cookie.cookie()` — never from
`os.environ`, never from a module-level global, never from a
hardcoded constant. The injected `LinkedInAuthCookiePort` is
the only source of truth.

Mirrors the v1 `location_resolver` injection pattern (per
the foundational `REQ-LI-SCR-004` above). The composition
root wires the port; tests inject test doubles. Reading from
`os.environ` inside `search()` would make the scraper
non-deterministic and untestable (the env var is
process-global).

#### Scenario: search reads cookie from injected port, not env

- **GIVEN** `LinkedInPlaywrightScraper` is constructed with
  `settings=LinkedInScraperSettings(..., auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("SYNTHETIC_FROM_PORT")))`
  AND `LINKEDIN_LI_AT="REAL_ENV_VALUE"` is set in the process
  environment
- **WHEN** `search("react", "Madrid")` runs against a `FakeBrowser`
- **THEN** `fake_browser.new_context_calls[0]["cookies"]`
  contains `{"name": "li_at", "value": "SYNTHETIC_FROM_PORT", ...}`
  — NOT `"REAL_ENV_VALUE"`
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_search_reads_cookie_from_injected_port_not_env` passes

### REQ-LA-SCR-002 — `ctx.add_cookies` is called BEFORE the first navigation on the SAME `BrowserContext`

When the port returns a non-None cookie, `search()` MUST call
`await ctx.add_cookies([{...}])` immediately after
`await self._browser.new_context(...)` returns and BEFORE the
first `paginated_search()` navigation, on the SAME
`BrowserContext` instance the loop uses. The injection MUST
NOT happen on a new context (cookie would not travel) and MUST
NOT happen per-page in the loop (cookie already travels with
the context's cookie store).

Playwright's `BrowserContext` shares the cookie store with all
pages in the context. One `add_cookies` call on the context
makes the cookie available to every page request the loop
issues. Doing it per-page would be wasteful and would not
change the semantic.

The cookie shape passed to `add_cookies` is
`{"name": "li_at", "value": <secret>, "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}`
(per Playwright `BrowserContext.add_cookies` API contract — see
`REQ-LA-SCR-004`).

#### Scenario: add_cookies called with correct shape (golden assertion)

- **GIVEN** `LinkedInPlaywrightScraper` is constructed with
  `auth_cookie=SecretStr("AQEAAAAQEAAA")` and a
  `FakeBrowser`/`FakePage` test double
- **WHEN** `search("react", "Madrid", limit=10)` runs (limit=10 forces 1 page, not 2)
- **THEN** `fake_browser.new_context_calls[0]["cookies"] == [{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]` (exact shape match)
- **AND** `fake_browser.new_context_calls[0]` is the SAME context object that `fake_browser.new_context_calls[0].new_page_calls[0].page` came from
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_add_cookies_called_with_correct_shape` passes

### REQ-LA-SCR-003 — Soft mode (port returns `None`) skips `add_cookies` and logs a single startup WARNING

When the port returns `None`, `search()` MUST NOT call
`ctx.add_cookies(...)` and MUST proceed to the pagination loop
with the v1 anonymous behavior. A single WARNING log line MUST
be emitted at `app_factory.build_app()` startup (NOT inside
`search()` — startup warning avoids per-search log spam) with
the message
`"LinkedIn scraper running without auth cookie; SERP will hit the auth wall and return a reduced list"`.

The WARNING is an operator signal that the auth path is OFF.
The startup-only emission (vs. per-search) keeps the log volume
predictable. The auth-wall message in the warning primes the
operator to expect degraded results.

#### Scenario: no add_cookies call when auth_cookie is None (legacy path preserved)

- **GIVEN** `LinkedInPlaywrightScraper` is constructed with `auth_cookie=None`
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** `fake_browser.new_context_calls[0]` does NOT have a `"cookies"` key (the legacy path is preserved)
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_no_add_cookies_call_when_auth_cookie_none` passes

#### Scenario: single startup WARNING emitted when cookie absent

- **GIVEN** `build_app()` is called with no `LINKEDIN_LI_AT` env var
- **WHEN** the startup phase completes
- **THEN** exactly one WARNING log record with `msg == "LinkedIn scraper running without auth cookie; SERP will hit the auth wall and return a reduced list"` is emitted
- **AND** the test `tests/integration/test_linkedin_auth_cookie.py::test_startup_warning_when_cookie_absent` passes

### REQ-LA-SCR-004 — Cookie shape matches LinkedIn's issuance contract

The cookie passed to `add_cookies` MUST set
`domain=".linkedin.com"` (the leading dot makes it match all
subdomains — `www.linkedin.com`, `es.linkedin.com`, etc.),
`path="/"` (applies to all paths), `http_only=True` (the
cookie is NOT exposed to JS — LinkedIn's `li_at` is
server-side only), and `secure=True` (HTTPS-only).

LinkedIn issues `li_at` with these exact flags. A different
shape (e.g. `domain="linkedin.com"` without the leading dot)
would NOT match the subdomain the SERP actually uses, and the
cookie would silently not be sent. The `http_only` and
`secure` flags match the real cookie semantics — a regression
here would either break the auth (if `secure=True` is dropped,
the browser may reject it) or expose the cookie to JS (if
`http_only=False`, the cookie is in `document.cookie` and any
XSS exposes it).

The cookie `name` MUST be exactly `"li_at"` (lowercase, the
canonical name LinkedIn uses).

#### Scenario: cookie shape matches LinkedIn contract (golden assertion)

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` and a `FakeBrowser` capturing the `add_cookies` call
- **WHEN** `search()` runs
- **THEN** the captured cookie dict equals `{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}` (exact key set + value match)
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_add_cookies_shape_matches_linkedin_contract` passes (golden assertion)

### REQ-LA-SCR-005 — `search()` does NOT log the cookie value at any level

`LinkedInPlaywrightScraper.search()` and its closure
`_make_fetch_one_page` MUST NOT log the cookie value at any
level (DEBUG/INFO/WARNING/ERROR). A test MUST capture all log
records emitted during a `search()` call (using `caplog` or an
injected `LogCapture` handler) and assert that no record's
`message` or `args` contains the synthetic test cookie string
`"AQEAAAAQEAAA"`.

AGENTS.md rule #7 forbids `li_at` cookies in the repo, and the
`SecretStr` type only protects `__repr__`/`__str__` — explicit
`logger.info("cookie=%s", cookie)` would unwrap the
`SecretStr` and leak. The test pins the no-leak contract at
the integration boundary.

#### Scenario: caplog captures all log records; no record contains cookie value

- **GIVEN** `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` AND a `FakeBrowser` that emits one INFO log line per request
- **WHEN** `search("react", "Madrid", limit=10)` runs AND `caplog` is set to level `DEBUG`
- **THEN** no captured log record's `message` or `args` contains the substring `"AQEAAAAQEAAA"`
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_search_does_not_log_cookie_value` passes

### REQ-LA-SCR-006 — Cookie is injected ONCE per `search()` (per-context, not per-page)

`search()` MUST call `add_cookies` exactly ONCE per invocation
(per the `new_context()` lifecycle), NOT per page in the
pagination loop. Two calls to `search()` MUST each call
`add_cookies` exactly once (so the per-search lifecycle is
observable). The cookie travels with every page request in
the loop automatically because Playwright's `BrowserContext`
shares the cookie store with all pages in the context.

The per-context injection is the v1 pattern; doing it
per-page would be wasteful and would not change the observable
behavior. The per-search count is the load-bearing contract
for ops debugging (e.g. when monitoring how many cookie
injections happen over a window of time).

The injection happens INSIDE the `try:` block of `search()`
(before `paginated_search()`), so an exception during the
loop does NOT leave the cookie set on a context that is then
closed.

#### Scenario: add_cookies called once per search (not per page)

- **GIVEN** `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` and a `FakeBrowser` that returns 25 cards per page for 3 pages
- **WHEN** `search("react", "Madrid", limit=50)` runs (forcing 2 pages)
- **THEN** `len(fake_browser.add_cookies_calls) == 1` (one per `search()`, NOT per page)
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_add_cookies_called_once_per_search` passes

#### Scenario: add_cookies called once per search across multiple searches

- **GIVEN** the same scraper and `FakeBrowser`
- **WHEN** `await search("react", "Madrid", limit=10)` runs twice in sequence
- **THEN** `len(fake_browser.add_cookies_calls) == 2` (one per `search()` invocation)
- **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_add_cookies_called_once_per_search_for_multiple_searches` passes

---

## New requirements (added 2026-06-13 from `scheduler-source-fix` archive)

### REQ-SOURCE-002 — LinkedIn scraper sets source="linkedin" on Job construction

The `LinkedInPlaywrightScraper._parse_cards` closure MUST set
`source="linkedin"` when constructing each `Job` instance. The source
value MUST exactly match `"linkedin"` to satisfy the DB `CHECK` constraint
`source IN ('linkedin','indeed','infojobs')`.

#### Scenario: LinkedIn scraper sets source="linkedin" on Job construction

- GIVEN the LinkedIn scraper has parsed job cards from a search result page
- WHEN `_parse_cards` constructs `Job` instances
- THEN each `Job` is constructed with `source="linkedin"`

#### Scenario: Source is testable via job.source field

- GIVEN a `FakeBrowser` returning valid LinkedIn HTML with 3 job cards
- WHEN `LinkedInPlaywrightScraper.search("python", "Madrid", limit=20)` is called
- THEN the returned `list[Job]` has all 3 jobs with `source="linkedin"`

### REQ-QUERY-003 — LinkedIn scraper handles empty keywords without error

The scraper MUST pass `keywords=""` (empty string) verbatim to the URL
builder when the scheduler passes empty keywords. The scraper MUST NOT
raise an error or skip the search when keywords are empty.

#### Scenario: Empty keywords passed to URL builder as-is

- GIVEN `keywords=""` passed to `search()`
- WHEN the URL is built
- THEN the URL contains the empty keywords parameter without error
- AND the search executes against LinkedIn with an empty query string

---

## Out of scope

- **The `LinkedInAuthCookiePort` Protocol and
  `EnvLinkedInAuthCookieAdapter`** — owned by the
  `linkedin-auth-cookie` capability spec.
- **The `Settings.linkedin_li_at` field + 2 validators** —
  owned by the `linkedin-config` capability spec.
- **The `is_auth_wall` defensive detector** — owned by the
  `linkedin-auth-wall-detector` capability spec.
- **The pagination loop internals** (`paginated_search`
  helper, page count, inter-page delay, max-pages cap) — these
  are owned by the shared helper and the
  `backend-scraper-query-tuning` change (archived 2026-06-09).
- **The `Job` parser (BS4 selectors)** — owned by the
  `LinkedInPlaywrightScraper._parse_cards()` private method,
  no change from this SDD change.
- **The browser context lifecycle (open/close)** — owned by
  the scraper's `search()` method, no change from this SDD
  change.
- **Adding more branches to the URL formula** (e.g. a future
  `?f_TPR=r86400` date filter) — follow-up changes.
- **The `paginated_search` helper's throttle acquisition**,
  which happens once around the whole loop (covered by the
  `backend-scraper-query-tuning` archive, not this change).
- **Committing a real `li_at`** — AGENTS.md rule #7; the test
  uses the synthetic 12-byte value `"AQEAAAAQEAAA"`.
- **Live test against real LinkedIn** — NOT required; the
  cookie is validated offline via the `ctx.add_cookies` call
  shape.

## Source of truth links

- **Delta spec source**: `openspec/changes/archive/2026-06-10-backend-linkedin-auth/spec.md` (Domain 2 of the multi-capability delta)
- **Foundational spec source**: `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/specs/backend-linkedin-location-fallback/spec.md` Domain 2
- **Sibling capabilities** (also extended in the same archive):
  - `openspec/specs/linkedin-auth-cookie/spec.md` — NEW with `REQ-LA-COOKIE-001..004`
  - `openspec/specs/linkedin-config/spec.md` — EXTENDED with `REQ-LA-CFG-001..004`
  - `openspec/specs/linkedin-auth-wall-detector/spec.md` — NEW with `REQ-LA-AWALL-001..006`

---

## Stealth extension requirements (added 2026-06-11 from `backend-linkedin-stealth` archive)

> **EXTENDED on 2026-06-11** from
> `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
> §"Capability: `linkedin-scraper` (EXTENDED)" (Domain 3 of
> the multi-capability delta spec).
>
> The v1 cycle added 6 `REQ-LA-SCR-001..006` for the
> `li_at` cookie injection. This delta ADDS 4
> `REQ-LST-SCR-001..004` (the `playwright-stealth` injection
> + multi-cookie `add_cookies` + extended closure precedence
> + the `is_cloudflare_challenge` soft-WARNING) on top of the
> pre-existing 4 `REQ-LI-SCR-001..004` (URL builder) and 6
> `REQ-LA-SCR-001..006` (v1 cookie injection). The
> pre-existing REQs are preserved verbatim above. Source
> observation IDs for this delta: explore #365, proposal #366,
> spec #367, design #368, tasks #369, apply-progress #370,
> verify-report #371.
>
> The mixed namespace (`REQ-LI-*` for URL builder +
> `REQ-LA-*` for v1 cookie injection + `REQ-LST-*` for stealth
> + multi-cookie + Cloudflare) is intentional; the v1
> single-cookie `EnvLinkedInAuthCookieAdapter` is KEPT
> byte-identical, the v1 anonymous path is preserved
> byte-identical, and the v1 `test_search_raises_blocked_on_auth_wall`
> is the regression check for the v1 hard-raise behavior.

### REQ-LST-SCR-001 — `search()` applies `playwright-stealth` at the `BrowserContext` level

`LinkedInPlaywrightScraper` constructor MUST accept a new
keyword-only kwarg `stealth: Stealth | None = None` (default
`None` — the v1 behavior is preserved when no stealth is
wired). The `Stealth` instance is held in
`self._stealth: Stealth | None`. In `search()`, AFTER
`await self._browser.new_context(...)` returns the context
AND BEFORE `add_cookies` and `paginated_search()` are called,
`search()` MUST call
`await self._stealth.apply_stealth_async(ctx)` GATED on
`self._stealth is not None` (i.e. the call is skipped when
`stealth=None`, preserving v1 behavior). The import is
`from playwright_stealth import Stealth  # type: ignore[import-untyped]`
(matches Indeed+InfoJobs precedent at
`infrastructure/indeed/scraper.py:69`).

Per `explore` obs #365 §6 Q3 (auto-resolved): BrowserContext
level is the canonical pattern (Indeed+InfoJobs use it). The
Indeed precedent is at
`infrastructure/indeed/scraper.py:240-247` (the
`if self._stealth is not None:` gate +
`await self._stealth.apply_stealth_async(ctx)` call); the
InfoJobs precedent is at
`infrastructure/infojobs/scraper.py:206` (ctor kwarg) + L327
(the call). Mirroring them keeps code-review parity.

#### Scenario: stealth is applied when provided (mirrors Indeed pattern)

- **GIVEN** a `LinkedInPlaywrightScraper` constructed with
  `stealth=MagicMock()` whose `apply_stealth_async` is an
  `AsyncMock` AND a `FakeBrowser` capturing the call
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** the `MagicMock().apply_stealth_async` is called
  exactly once with the context object
- **AND** the call happens AFTER `new_context` AND BEFORE
  `add_cookies` (order is verified by the test)
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_stealth_is_applied_when_provided`
  passes (mirrors Indeed `TestStealthIntegration`)

#### Scenario: stealth is skipped when None (v1 behavior preserved)

- **GIVEN** a `LinkedInPlaywrightScraper` constructed with
  `stealth=None` (the v1 default)
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** the `apply_stealth_async` is NEVER called (the
  gate skips it)
- **AND** the v1 behavior is preserved (35 v1 tests stay
  GREEN)
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_stealth_is_skipped_when_none`
  passes

### REQ-LST-SCR-002 — `search()` injects all non-None cookies via `ctx.add_cookies` with the LinkedIn-shape Playwright dict

When the multi-cookie port returns a non-`None` list,
`search()` MUST call
`await ctx.add_cookies([{...} for (n, v) in cookies])` AFTER
`apply_stealth_async(ctx)` and BEFORE the first
`paginated_search()` navigation, on the SAME `BrowserContext`
instance. Each cookie dict MUST be
`{"name": <n>, "value": <v.get_secret_value()>, "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}`
(the LinkedIn-shape contract per the v1 `REQ-LA-SCR-004`
golden assertion, generalized to N cookies). When the port
returns `None` (the v1 anonymous path), `add_cookies` is NOT
called.

Per-context injection (not per-page) matches the v1 pattern
(per `REQ-LA-SCR-002` + `REQ-LA-SCR-006`). Generalizing from
1 to N cookies is a list comprehension; the per-cookie shape
is byte-identical to the v1 (LinkedIn's issuance contract).
The v1 `cookies: [{"name": "li_at", "value": ..., ...}]`
golden assertion extends to
`cookies: [{"name": n_i, "value": ..., "domain": ".linkedin.com", ...} for (n_i, v_i) in port.cookies()]`.

#### Scenario: add_cookies called with all non-None cookies (golden assertion)

- **GIVEN** a `LinkedInPlaywrightScraper` with
  `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), SecretStr("ajax:12345"), None, None)`
  (2 cookies) AND a `FakeBrowser` capturing `add_cookies`
  calls
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN**
  `add_cookies_calls[0] == [{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}, {"name": "jsessionid", "value": "ajax:12345", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]`
  (golden assertion on the full list)
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_multi_cookie_injection_golden`
  passes

#### Scenario: no add_cookies when all cookies are None (anonymous path preserved)

- **GIVEN** the same scraper with
  `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(None, None, None, None)`
  (the v1 anonymous sentinel — all 4 None)
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** `add_cookies` is NEVER called
- **AND** the v1 anonymous path is preserved
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_no_add_cookies_when_all_cookies_none`
  passes

### REQ-LST-SCR-003 — `_make_fetch_one_page` closure precedence: `is_cloudflare_challenge` → `is_auth_wall` → `is_block_page` (cookie path) / `is_block_page` first (anonymous path)

Inside `LinkedInPlaywrightScraper._make_fetch_one_page`
closure, the per-page check order MUST be:

- **Cookie-injection path** (`auth_cookies is not None` and
  `auth_cookies.cookies() is not None`):
  `is_cloudflare_challenge(soup)` checked FIRST (newest — soft
  path → WARNING + return whatever cards exist if it fires
  with 0 cards), THEN `is_auth_wall(soup)` (v1 soft path →
  WARNING if it fires), THEN `is_block_page(soup)` (v1 hard
  path → raise `LinkedInBlockedError` if it fires — extremely
  rare, only a genuine hard block).
- **Anonymous path** (`auth_cookies is None` OR
  `auth_cookies.cookies() is None`): `is_block_page(soup)`
  checked FIRST (the v1 hard-raise behavior is preserved
  byte-identical), `is_auth_wall` and `is_cloudflare_challenge`
  are NOT consulted (the v1
  `test_search_raises_blocked_on_auth_wall` test is preserved
  unchanged).

The newest-first precedence on the cookie path mirrors the v1
`is_auth_wall` design (per the v1 archive note: "the
cookie-injection path checks `is_auth_wall` FIRST, the
anonymous path keeps `is_block_page` FIRST"). The new
`is_cloudflare_challenge` is even SOFTER than `is_auth_wall`
(Cloudflare's 302-loop is a network-layer event, not a
soup-parseable page), so it gets the highest precedence
(lowest threshold to fire) on the cookie path. The v1
anonymous path is preserved byte-identical (the 35 v1 tests
stay GREEN).

#### Scenario: closure warns on cloudflare challenge (cookie path, 0 cards)

- **GIVEN** a `LinkedInPlaywrightScraper` with
  `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), None, None, None)`
  (cookie path) AND a `FakeBrowser` that returns
  `CLOUDFLARE_CHALLENGE_HTML` (Cloudflare marker, 0 cards) for
  every page
- **WHEN** `search("react", "Madrid", limit=10)` runs AND
  `caplog` is set to `WARNING`
- **THEN** the closure emits the WARNING per `REQ-LST-SCR-004`
  (the Cloudflare-challenge message)
- **AND** `search()` returns `[]` (the soft path, no raise)
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_closure_warns_on_cloudflare_challenge`
  passes

#### Scenario: closure falls through to is_auth_wall when cloudflare is False

- **GIVEN** the same scraper (cookie path) AND a `FakeBrowser`
  that returns `BLOCK_PAGE_HTML` (LinkedIn auth wall, 0 cards)
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** the closure emits the v1 `is_auth_wall` WARNING
  (the soft path wins because `is_cloudflare_challenge`
  returned False on the LinkedIn auth wall)
- **AND** `search()` returns `[]`
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_closure_warns_on_auth_wall_after_cloudflare_false`
  passes

#### Scenario: anonymous path keeps v1 byte-identical behavior

- **GIVEN** a `LinkedInPlaywrightScraper` with
  `auth_cookies=None` (anonymous path — v1 behavior) AND a
  `FakeBrowser` that returns `BLOCK_PAGE_HTML` for every page
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** raises `LinkedInBlockedError` (the v1 hard-raise
  path is preserved)
- **AND** `is_auth_wall` and `is_cloudflare_challenge` are
  NOT consulted (the v1 test
  `test_search_raises_blocked_on_auth_wall` is the regression
  check)
- **AND** the 35 v1 tests stay GREEN

### REQ-LST-SCR-004 — `is_cloudflare_challenge` WARNING log: soft path, no raise, returns `[]` on page-0 zero-cards

When `is_cloudflare_challenge(soup) is True` AND the page
yields 0 cards, the scraper MUST return `[]` (an empty list) —
NOT raise a `LinkedInParseError`, NOT raise a
`LinkedInBlockedError`. A single WARNING log line MUST be
emitted with the message
`"LinkedIn Cloudflare challenge detected; stealth may be insufficient. Consider setting LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC in .env, or upgrading to a residential proxy."`

The closure continues parsing whatever cards exist (does NOT
short-circuit on the marker). When the Cloudflare challenge
is on page 0 AND 0 cards are parsed, the scraper returns `[]`
(mirrors v1 `REQ-LA-AWALL-006`).

Per `explore` obs #365 §6 Q4: soft path mirrors v1
`is_auth_wall`. The WARNING is the operator signal that
stealth is insufficient (and gives the operator a concrete
action: add 3 more cookies or upgrade to a residential proxy).
The response is degraded-but-not-500 (so a frontend can render
a "Cloudflare challenge detected" UI rather than a generic 502
page).

**Live outcome caveat** (per `verify-report` obs #371 §4): the
live smoke test against real LinkedIn + Cloudflare-2026
returned `HTTP 502` with `ERR_TOO_MANY_REDIRECTS` in <5s with
the operator's fresh cookies + `playwright-stealth`. The
detector itself is correctly implemented (3/3 negative
scenarios + 1/1 positive scenario pass with the
`CLOUDFLARE_CHALLENGE_HTML` fixture); the operational outcome
is that LinkedIn's anti-bot closes the connection BEFORE the
page renders as HTML, so the detector never has a chance to
fire on the live request. The documented follow-up is
`backend-linkedin-xvfb` (a real browser under Xvfb to get a
non-headless TLS fingerprint).

#### Scenario: closure warns on cloudflare challenge with actionable message

- **GIVEN** a `LinkedInPlaywrightScraper` with
  `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), None, None, None)`
  AND a `FakeBrowser` that returns `CLOUDFLARE_CHALLENGE_HTML`
  (challenge marker, 0 cards) for every page
- **WHEN** `search("react", "Madrid", limit=10)` runs AND
  `caplog` is set to `WARNING`
- **THEN** exactly one WARNING log record contains
  `"LinkedIn Cloudflare challenge detected"` AND
  `"LINKEDIN_JSESSIONID"` AND `"LINKEDIN_BCOOKIE"` AND
  `"LINKEDIN_LI_GC"`
- **AND** `search()` returns `[]` (empty list, NOT a
  `LinkedInBlockedError`)
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_closure_warns_on_cloudflare_challenge_with_actionable_message`
  passes

#### Scenario: closure does NOT warn when cards present even with cloudflare marker (false-positive suppression)

- **GIVEN** a `FakeBrowser` that returns HTML with BOTH a
  Cloudflare marker AND 3 cards (cards win)
- **WHEN** `search("react", "Madrid", limit=10)` runs
- **THEN** NO Cloudflare WARNING is emitted (the "cards win"
  rule from `REQ-LST-CF-003` suppresses the false positive)
- **AND** `search()` returns the 3 parsed jobs
- **AND** the test
  `tests/unit/test_linkedin_scraper.py::TestStealthIntegration::test_closure_does_not_warn_when_cards_present_even_with_cloudflare_marker`
  passes (false-positive suppression at the closure level)

## Source of truth links (extensions)

- **Delta spec source (this extension)**:
  `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
  (Domain 3 of the multi-capability delta)
- **Sibling capabilities** (also promoted in the stealth archive):
  - `openspec/specs/linkedin-anti-bot-detector/spec.md` —
    NEW with `REQ-LST-CF-001..003` (the defensive
    `is_cloudflare_challenge` detector)
  - `openspec/specs/linkedin-auth-cookie/spec.md` —
    EXTENDED with `REQ-LST-COOKIE-001..005` (the multi-cookie
    Protocol + `MultiEnvLinkedInAuthCookiesAdapter` +
    deterministic order + repr mask)
  - `openspec/specs/linkedin-config/spec.md` — EXTENDED
    with `REQ-LST-CFG-001..003` (3 new optional SecretStr
    fields + shared validator + repr no-leak)
