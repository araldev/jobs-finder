# Spec: `linkedin-scraper` — `LinkedInPlaywrightScraper` URL Builder

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/specs/backend-linkedin-location-fallback/spec.md`
> (Domain 2, archived in `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/`).
>
> This was a MODIFIED delta — no prior
> `openspec/specs/linkedin-scraper/spec.md` existed. The delta
> documents the URL builder extension (priority
> `geoId > structured > raw`) on top of the pre-change
> `LinkedInPlaywrightScraper._build_url()` contract. The delta is
> promoted in full as the foundational spec for the capability,
> capturing the 3-branch URL priority. Source observation IDs for
> traceability: explore #332, proposal #333, spec #336, design #338,
> tasks #340, apply-progress #345, verify-report #348.

## Purpose

`LinkedInPlaywrightScraper` (in
`backend/src/jobs_finder/infrastructure/linkedin/scraper.py`) is
the adapter of Playwright for the LinkedIn job-search portal. Its
responsibility is to:

1. Build the search URL with the correct query parameters.
2. Open a fresh browser context + page.
3. Drive the auto-pagination loop via the shared
   `paginated_search` helper.
4. Parse each page into a `list[Job]`.

This spec covers the URL builder (item 1) — specifically the
`?keywords=...&location=...&start=...` / `?geoId=...&start=...`
formula and its 3-branch priority after this change. The
pagination loop, the `paginated_search` helper, the parser, and
the browser lifecycle are out of scope for this spec (covered by
upstream change `backend-scraper-query-tuning`, archived
2026-06-09, and the pre-change LinkedIn scraper baseline).

## Requirements

### REQ-LI-SCR-001 — `_build_url` prioridad `geoId > structured > raw`

The `_build_url` method (private) MUST accept two kwargs:
`geo_id: int | None = None` (pre-existing, from
`backend-scraper-query-tuning`) and `structured: tuple[str, str, str] | None = None`
(NUEVO, from this change). The priority MUST be:

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

- **GIVEN** ambos `geo_id=103374081` (Madrid) y `structured=("Antequera", "Andalucía", "Spain")` están disponibles
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

The `?location=City,Province,Country` format MUST URL-encode tildes
as `%C3%AD` (NFC composed, UTF-8 multibyte) and commas as `%2C`.
`urllib.parse.quote` por defecto (con `safe="/"`) encodea solo los
caracteres que no son letras/dígitos/ASCII-safe (`/`, `:`, `@`, etc.),
preservando caracteres Unicode como `í` que se codifican como
UTF-8 multibyte. **Importante**: `quote(s, safe=",", ...)` NO es
correcto — mantendría la coma como literal en la URL pero rompería
el byte-for-byte match con la URL real del user (que tiene `%2C`).

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

- **GIVEN** la URL capturada por el usuario es `https://www.linkedin.com/jobs/search?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0`
- **WHEN** se llama `_build_url("react", "Antequera", 0, structured=("Antequera", "Andalucía", "Spain"))`
- **THEN** la URL retornada es **exactamente** la URL real (byte-for-byte)
- **AND** el test `test_linkedin_scraper.py::test_build_url_matches_user_captured_url` pasa (golden assertion)

### REQ-LI-SCR-003 — `search()` consulta AMBOS resolvers una sola vez

`LinkedInPlaywrightScraper.search()` MUST llamar
`resolver.resolve(location)` AND
`resolver.resolve_structured(location)` exactamente UNA vez
(no por página) al inicio de la búsqueda, y capturar los
resultados en el closure de `_make_fetch_one_page`. La URL se
construye una vez con los valores resueltos y se reusa con `start`
cambiando por página (a través del helper compartido
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
existe pero la ciudad no tiene mapping estructurado), el scraper
MUST caer al legacy `?location=<raw>`. NO raise, NO log spam.

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

## Out of scope

- The pagination loop internals (`paginated_search` helper, page
  count, inter-page delay, max-pages cap) — these are owned by
  the shared helper and the `backend-scraper-query-tuning` change
  (archived 2026-06-09).
- The `Job` parser (BS4 selectors) — owned by the
  `LinkedInPlaywrightScraper._parse_cards()` private method, no
  change from this SDD change.
- The browser context lifecycle (open/close) — owned by the
  scraper's `search()` method, no change from this SDD change.
- Adding more branches to the URL formula (e.g. a future
  `?f_TPR=r86400` date filter) — follow-up changes.
- The `paginated_search` helper's throttle acquisition, which
  happens once around the whole loop (covered by the
  `backend-scraper-query-tuning` archive, not this change).
