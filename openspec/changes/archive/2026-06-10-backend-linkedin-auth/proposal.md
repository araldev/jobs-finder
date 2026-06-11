# Proposal: `backend-linkedin-auth`

> **Cambio**: `backend-linkedin-auth` • **Modo**: `both` (OpenSpec files + Engram copy) • **Strict TDD**: ACTIVE
> **Fecha**: 2026-06-10 • **Base**: `017d6fa` (post `backend-infojobs-provinces` + `backend-scraper-query-tuning` merge, main; working tree clean)
> **Status**: `proposed` (listo para `sdd-spec`)
> **Upstream**: obs #353 (explore — §2-§7 contract + precedent shapes) + obs #4 (linkedin-endpoint, where auth was OUT of scope) + obs #302 (fix-linkedin-geoid — the resolver/sidecar-port precedent this change mirrors)

## 1. Intención

El `LinkedInPlaywrightScraper` actual (v1) corre anónimo: cada `search()` abre un `BrowserContext` con sólo `user_agent` + `viewport` (`scraper.py:274-277`). LinkedIn responde al SERP público con un modal de sign-in hidden en el HTML (los cards SE renderizan, pero los links no resuelven al detail panel sin sesión) y un cap funcional de ~3-5 ofertas por query — el resto del stream llega detrás del auth wall y se ignora client-side. El usuario lo confirmó explícitamente en español el 2026-06-10: *"Implementar la cookie de linkedin para que pueda extraer los jobs, mira en engram o en specs tiene uqe estar documentado"*. Este cambio plumb la `li_at` session cookie del operador al contexto de Playwright vía `LINKEDIN_LI_AT` env var, restaurando el stream completo sin programar login, sin auto-refresh, sin multi-cuenta, sin DB.

## 2. Alcance

### 2.1 In scope

| # | Deliverable | Archivos | Esfuerzo |
|---|---|---|---|
| 1 | NEW `LinkedInAuthCookiePort` Protocol en `application/ports.py` — un valor provider sync (no I/O), retorna `SecretStr \| None` (idéntico patrón a `LocationResolverPort`) | `application/ports.py` (Protocol) | ~10-15 LOC |
| 2 | NEW `EnvLinkedInAuthCookieAdapter` en `infrastructure/linkedin/auth_cookie.py` — implementa el Protocol, lee `Settings.linkedin_li_at` (cero I/O en runtime) | `infrastructure/linkedin/auth_cookie.py` (NEW) | ~20-30 LOC |
| 3 | NEW `linkedin_li_at: SecretStr \| None` field en `Settings` con `validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at")` + `field_validator` mode=before que normaliza empty→`None` (mismo patrón que `_normalize_empty_secret` para `llm_api_key:714-751`) + un `field_validator` mode=after que rechaza `len < 8` con `ValueError` claro (Q1=opción C: HARD cuando presente+<8, soft WARNING cuando ausente) | `infrastructure/config.py` | ~30-45 LOC |
| 4 | EXTEND `LinkedInScraperSettings` con `__slots__` field `auth_cookie: SecretStr \| None = None` + `__init__` kwarg + `__repr__` que retorna `"<set>"` / `"<unset>"` (NO repr del value — AGENTS.md rule #7) | `infrastructure/linkedin/scraper.py:111-176` | ~10-15 LOC |
| 5 | EXTEND `LinkedInPlaywrightScraper.search()` con `await ctx.add_cookies([{"name": "li_at", "value": ..., "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}])` entre `new_context()` y `paginated_search()` (per-context, per-search — single injection point, cookie viaja con cada page request del loop) | `infrastructure/linkedin/scraper.py:274-277` | ~10-15 LOC |
| 6 | NEW `is_auth_wall(soup: BeautifulSoup) -> bool` pure function en `infrastructure/linkedin/parsers.py` — distinto de `is_block_page` (que ya existe en `parsers.py:213`); semántica: "resultados SE renderizaron pero el contenido sugiere auth wall inminente (cards insuficientes + auth-wall class)" — TRUE para el `BLOCK_PAGE_HTML` fixture existente, FALSE para `SEARCH_PAGE_HTML` healthy | `infrastructure/linkedin/parsers.py` | ~10-20 LOC |
| 7 | EXTEND el closure de `_make_fetch_one_page` con un WARNING log `logger.warning("LinkedIn SERP appears auth-walled despite cookie injection; cookie may be expired")` cuando `is_auth_wall(soup)` returns True (Q3 — defensive detector included) | `infrastructure/linkedin/scraper.py:_make_fetch_one_page` | ~5-8 LOC |
| 8 | Wire del adapter en `app_factory.build_app()`: `EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)` se construye una vez, se inyecta como `auth_cookie=` kwarg en `LinkedInScraperSettings`. WARNING log at app startup cuando `linkedin_li_at is None` (Q1 soft path) | `presentation/app_factory.py:240-258` | ~15-25 LOC |
| 9 | EXTEND `LinkedInScraperSettings.__repr__` para enmascarar `auth_cookie` como `"<set>"` / `"<unset>"` (AGENTS.md rule #7 — sin log leakage del value) | `infrastructure/linkedin/scraper.py:148-154` | ~3-5 LOC |
| 10 | EXTEND `FakeLocationResolver` test double en `tests/conftest.py` con un `FakeLinkedInAuthCookiePort` companion que implementa el nuevo Protocol (default `None` = anonymous scraper) | `tests/conftest.py` | ~10-15 LOC |
| 11 | Tests unit (TDD-strict, RED first): `tests/unit/test_linkedin_auth_cookie.py` (NEW) cubre (a) `EnvLinkedInAuthCookieAdapter` happy-path, (b) `Settings.linkedin_li_at` validator scenarios (3 empty inputs → `None`, non-empty ≥8 → `SecretStr`, present+<8 → `ValueError`, absent → `None`+WARNING), (c) `LinkedInScraperSettings.__repr__` masking | `tests/unit/test_linkedin_auth_cookie.py` (NEW) | ~150-200 LOC |
| 12 | Tests unit: `tests/unit/test_linkedin_auth_wall.py` (NEW) cubre (a) `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` → True, (b) `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML))` → False, (c) edge case: results + auth-wall class ambos presentes → False (cards win) | `tests/unit/test_linkedin_auth_wall.py` (NEW) | ~40-60 LOC |
| 13 | Tests unit EXTEND: `tests/unit/test_linkedin_scraper.py` agrega 2-3 scenarios: (a) `auth_cookie=None` → `ctx.add_cookies` NO se llama (legacy path), (b) `auth_cookie=SecretStr("AQEAAAAQEAAA")` → `ctx.add_cookies` recibe el cookie con `name="li_at"`, `value=...`, `domain=".linkedin.com"`, (c) el cookie se inyecta una sola vez por `search()` (no per-page) | `tests/unit/test_linkedin_scraper.py` (EXTEND) | ~60-90 LOC |
| 14 | Test de integration: `tests/integration/test_linkedin_auth_cookie.py` (NEW) end-to-end via `build_app(use_case=...)` con `FakeLinkedInAuthCookiePort` retornando un `SecretStr` sintético — asserta que la cookie alcanza `ctx.add_cookies()` con el shape correcto y que el scraper no rompe con la cookie ausente | `tests/integration/test_linkedin_auth_cookie.py` (NEW) | ~60-90 LOC |
| 15 | EXTEND `backend/README.md` "Manual verification" section con un nuevo `### LinkedIn auth cookie (optional)` subsection DESPUÉS de los subsections LinkedIn-related existentes (líneas 1418-1577 per AGENTS.md). Incluye: curl example con `LINKEDIN_LI_AT` en el shell, .env snippet, FAQ "¿qué pasa si mi cookie expira?" (link al detector WARNING), legal notice link | `backend/README.md` (MODIFY) | ~30-50 LOC |
| 16 | EXTEND `backend/.env.example` con `LINKEDIN_LI_AT=` placeholder line (empty, commented-out, con nota de seguridad "NEVER commit a real value") después del bloque LinkedIn existente (líneas 22-51) | `backend/.env.example` (MODIFY) | ~5-10 LOC |

**Total estimado**: ~80-130 LOC prod + ~310-440 tests + ~35-60 docs = **~425-630 LOC netos** (incluyendo tax de strict TDD). Muy por debajo del presupuesto de 5000 líneas; **single PR es suficiente — no chained PR needed**.

### 2.2 Out of scope (explicit)

- **Programmatic login** (navegar a `linkedin.com/login`, llenar form, submit) — el usuario provee su propia cookie via env var; el scraper NO intenta obtenerla.
- **Auto-refresh de la cookie** — cuando la `li_at` expira (típico: ~1 año), el scraper degrada a v1 behavior (anonymous, ~3-5 results); el `is_auth_wall` detector emite un WARNING log para que ops lo note.
- **Multi-cuenta / multi-cookie** — un solo `LINKEDIN_LI_AT` por instancia; multi-cuenta es un follow-up.
- **Persistencia de la cookie en DB / Redis** — el env var es la única source of truth; el `Settings` field se re-evalúa en cada process start.
- **OAuth flow** — LinkedIn no expone OAuth para first-party job scraping; no aplica.
- **Modificar `JobSearchPort` Protocol** — la cookie se inyecta via `LinkedInScraperSettings` (kwarg aditivo), no via Port signature (mantiene el Port source-agnostic).
- **Modificar `paginated_search` helper** — la cookie es per-context, se aplica antes de entrar al loop; el helper es source-agnostic y no necesita cambios.
- **Modificar los otros 2 scrapers (Indeed, InfoJobs)** — sus anti-bot measures son distintos (Distil, Geetest); el patrón de cookie no aplica directamente. Follow-up si surge la misma necesidad.
- **Mover el `is_block_page` a `is_auth_wall`** — son funciones distintas: `is_block_page` es "0 cards + auth-wall signals" (el 502 path existente); `is_auth_wall` es "results rendered pero posiblemente degraded" (el WARNING path nuevo). Conviven; `is_block_page` no se toca.
- **Commit del `li_at` real** — explícitamente prohibido por AGENTS.md rule #7; el test usa un valor sintético de 12 bytes ASCII.
- **Cambiar el HTTP contract del frontend** — `GET /jobs?q=...&location=...` queda intacto; el `location` string viaja sin cambios; la cookie es internal al scraper.
- **Cambiar `LocationResolverPort`** — el nuevo `LinkedInAuthCookiePort` es un Protocol NUEVO e independiente (no extiende el resolver; son concerns distintos — resolver mapea strings, cookie provee auth).
- **Live test contra LinkedIn real** — NO requerido (resuelve el HIGH risk de obs #254 — la cookie se evalúa offline via `ctx.add_cookies` call shape, no via DOM render). El LIVE test sería gateado `LLM_LIVE_TESTS=1` y es opcional.

## 3. Capabilities (contrato con `sdd-spec`)

### 3.1 New

- `linkedin-auth-cookie`: la capacidad de inyectar una `li_at` session cookie en el `BrowserContext` de Playwright del LinkedIn scraper antes del primer navigation. Cubre 5-6 REQs (Port Protocol, env-var adapter, `Settings` field + Q1 validator, per-context injection via `ctx.add_cookies`, cookie shape, no-log-leakage via `__repr__` masking). El spec cubre el camino "cookie presente" (full SERP) Y el camino "cookie ausente" (soft WARNING, v1 fallback preservado).
- `linkedin-auth-wall-detector`: la capacidad de detectar — durante un `search()` — que el SERP retornó una auth-wall variant (cards insuficientes + `class="auth-wall"` presente) a pesar de la cookie inyectada, y emitir un WARNING log. Cubre 2-3 REQs (función pura `is_auth_wall(soup)`, semantic split con `is_block_page`, integration con el closure de `_make_fetch_one_page`).

### 3.2 Modified (delta specs)

- `linkedin-scraper` (REQ-L-001..L-010, REQ-STR-LOC-001..009): `LinkedInScraperSettings` crece un kwarg `auth_cookie: SecretStr | None = None`; `LinkedInPlaywrightScraper.search()` agrega `await ctx.add_cookies(...)` entre `new_context()` y `paginated_search()`; el closure de `_make_fetch_one_page` llama a `is_auth_wall(soup)` después de cada `_parse_cards` y emite WARNING si True. La URL formula NO cambia (la cookie NO afecta la URL — afecta el session state del browser context). El paginated loop NO cambia. La `LinkedInScraperSettings.__repr__` agrega masking.
- `linkedin-config` (REQ-SET-LI-001..010): `Settings.linkedin_li_at: SecretStr | None` se agrega al bloque "LinkedIn scraper" existente (después de `linkedin_inter_page_delay_seconds` en `config.py:287-292`); 2 `field_validator`s (mode=before empty→None, mode=after <8→`ValueError`); WARNING log at app startup cuando `None`; sin cambios al resto del bloque.

### 3.3 Sin cambios

- `domain` (Job, exceptions) — la cookie NO agrega nuevos exception types; usa los existentes (`LinkedInBlockedError` cuando el 502 path dispara).
- `application/aggregator.py` — el dispatch es transparente; la cookie NO aparece en `AggregatedJobsQuery` (es internal al scraper, mirrors `location_resolver`).
- `application/ports.py` `JobSearchPort` — signature intacta (5to kwarg `geo_id` ya existe; la cookie se inyecta via `LinkedInScraperSettings`, no via Port).
- `application/ports.py` `LocationResolverPort` — NO se modifica (cookie ≠ resolver; son concerns distintos).
- `application/ports.py` `JobSearchCacheKey` — NO se modifica (el cache key actual `keywords|location|limit|geo_id|source` cubre el 5to campo LinkedIn-specific; la cookie no es parte del cache key porque una cookie expirada cambia el resultado pero la cache hit NO debería servir un resultado con cookie distinta — la cookie es side-effect state, no input).
- `infrastructure/linkedin/throttle.py` — la cookie no afecta throttling.
- `infrastructure/linkedin/parsers.py` `is_block_page` — se PRESERVA intacto (semántica distinta: `is_block_page` = "0 cards + auth signals" = 502 path; `is_auth_wall` = "results rendered pero degraded" = WARNING path).
- `infrastructure/indeed/scraper.py`, `infrastructure/infojobs/scraper.py` — sin cambios (anti-bot distinto).
- `infrastructure/pagination.py` — sin cambios (helper es source-agnostic; la cookie se aplica pre-loop).
- `presentation/schemas.py` (HTTP shape) — sin cambios (el JSON de `GET /jobs` no expone el estado de la cookie).
- `presentation/routes/linkedin.py`, `presentation/routes/aggregator.py` — sin cambios.
- `frontend/*` — sin cambios (el HTTP contract es el mismo).
- `linkedin-endpoint` (obs #4) — la flag "auth OUT of scope" se cierra con este change; no se reabre el debate.
- `linkedin-structured-location-fallback` (obs #302) — los 2 cambios son ortogonales; `auth_cookie` y `location_resolver` viven en fields distintos de `LinkedInScraperSettings`.

## 4. Enfoque técnico

### 4.1 Protocol + Adapter (Q1 validation ya resuelta)

En `application/ports.py` (después de `LocationResolverPort:170-262`, antes de `RateLimitPort:337`):

```python
class LinkedInAuthCookiePort(Protocol):
    """Returns the operator's `li_at` session cookie for LinkedIn.

    The protocol is sync (no I/O — the value comes from `Settings`
    at process start). When `None`, the scraper runs anonymously
    (the v1 behavior: auth-wall modal hidden in HTML, ~3-5
    results per query). When a `SecretStr`, the scraper injects
    the cookie into the Playwright `BrowserContext` before the
    first navigation (per-context, per-search) — the cookie
    travels with every page request in the pagination loop.
    """

    def cookie(self) -> SecretStr | None: ...
```

En `infrastructure/linkedin/auth_cookie.py` (NEW, ~25 LOC):

```python
class EnvLinkedInAuthCookieAdapter:
    """Reads `li_at` from `Settings.linkedin_li_at` (no I/O)."""

    __slots__ = ("_cookie",)

    def __init__(self, cookie: SecretStr | None) -> None:
        self._cookie = cookie

    def cookie(self) -> SecretStr | None:
        return self._cookie
```

### 4.2 Settings field + Q1 validator

En `infrastructure/config.py` (después de `linkedin_inter_page_delay_seconds:287-292`):

```python
# T-002 of `backend-linkedin-auth` — REQ-SET-LI-001 cookie plumb.
#
# `linkedin_li_at` (default `None`) is the operator's personal
# `li_at` session cookie. Mirrors the `llm_api_key: SecretStr |
# None` pattern at `config.py:714` (same `field_validator`
# mode=before empty→`None` normalization) and adds a second
# mode=after validator that rejects values with `len < 8` as
# `ValueError` (Q1 option C: catches operator typos at boot).
#
# When UNSET: app_factory emits a WARNING log at startup;
# scraper proceeds anonymously (v1 behavior preserved).
# When SET + len >= 8: scraper injects the cookie.
# When SET + len < 8: HARD error at Settings() ctor — the
# most common case is `LINKEDIN_LI_AT=abc` (a typo).
linkedin_li_at: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at"),
)

@field_validator("linkedin_li_at", mode="before")
@classmethod
def _normalize_empty_li_at(cls, v: SecretStr | str | None) -> SecretStr | None:
    if v is None:
        return None
    if isinstance(v, SecretStr):
        if v.get_secret_value() == "":
            return None
        return v
    if v == "":
        return None
    return v  # non-empty str — pydantic wraps in SecretStr

@field_validator("linkedin_li_at", mode="after")
@classmethod
def _reject_short_li_at(cls, v: SecretStr | None) -> SecretStr | None:
    if v is None:
        return None
    if len(v.get_secret_value()) < 8:
        raise ValueError(
            "LINKEDIN_LI_AT must be at least 8 characters (got "
            f"{len(v.get_secret_value())}); check for typos or "
            "unset the variable to run the scraper anonymously."
        )
    return v
```

### 4.3 Per-context injection en `LinkedInPlaywrightScraper.search()`

En `infrastructure/linkedin/scraper.py:274-277` (entre `new_context()` y `new_page()`):

```python
ctx = await self._browser.new_context(
    user_agent=self._settings.user_agent,
    viewport=VIEWPORT,
)
# T-003 of `backend-linkedin-auth` — REQ-LI-COOKIE-001 plumb.
# Inject the operator's `li_at` cookie ONCE per `search()`
# (per-context, not per-page). The cookie travels with every
# page request in the pagination loop (the `BrowserContext`
# shares the cookie store with all pages in the context).
cookie = self._settings.auth_cookie.cookie() if self._settings.auth_cookie is not None else None
if cookie is not None:
    await ctx.add_cookies([
        {
            "name": "li_at",
            "value": cookie.get_secret_value(),
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
        }
    ])
try:
    page = await ctx.new_page()
    # ... existing paginated_search call
```

El `__repr__` de `LinkedInScraperSettings` agrega masking (AGENTS.md rule #7 — el value NUNCA aparece en logs):

```python
def __repr__(self) -> str:
    auth_cookie_repr = "<set>" if self.auth_cookie is not None else "<unset>"
    return (
        f"LinkedInScraperSettings(user_agent={self.user_agent!r}, "
        f"timeout_ms={self.timeout_ms}, max_pages={self.max_pages}, "
        f"inter_page_delay_seconds={self.inter_page_delay_seconds}, "
        f"location_resolver={self.location_resolver!r}, "
        f"auth_cookie={auth_cookie_repr})"
    )
```

### 4.4 `is_auth_wall` defensive detector (Q3 included)

En `infrastructure/linkedin/parsers.py` (después de `is_block_page:213-242`):

```python
def is_auth_wall(soup: BeautifulSoup) -> bool:
    """Return True if the SERP rendered an auth-wall variant.

    Distinct from `is_block_page` (the 502 path): `is_block_page`
    fires when the page is a TRUE auth wall with ZERO cards; this
    function fires when results are present BUT the rendered
    structure suggests an imminent auth wall (e.g. the `<body>`
    carries `class="auth-wall"` while a partial card list is
    visible — the cookie may be expired or LinkedIn may be
    throttling the session).

    The function is a defensive observability helper: it lets the
    scraper emit a WARNING log so ops can detect a degraded cookie
    BEFORE the user starts seeing 0-result responses. The page
    itself is NOT treated as a hard block (results ARE returned
    to the caller); only the WARNING fires.

    Returns True when:
      - `<body class="auth-wall">` is present AND zero job cards
        are present (the BLOCK_PAGE_HTML fixture's case).
    Returns False when:
      - No `class="auth-wall"` signal is present (healthy SERP).
      - Job cards are present (results win — not a degraded render).
    """
    auth_wall_signal = soup.select_one("body.auth-wall, .auth-wall")
    if auth_wall_signal is None:
        return False
    # If cards are present, the auth-wall signal is a false
    # positive (the SERP has the class as defensive markup but
    # the user IS authenticated enough to see results).
    if soup.select("div[data-entity-urn]"):
        return False
    return True
```

En el closure de `_make_fetch_one_page` (después de `_parse_cards`):

```python
soup = BeautifulSoup(html, "html.parser")
if is_auth_wall(soup):
    _logger.warning(
        "LinkedIn SERP appears auth-walled despite cookie "
        "injection; cookie may be expired. Returning %d jobs "
        "from this page (degraded).",
        len(jobs),
    )
jobs = _parse_cards(soup, remaining)
# ... existing return
```

### 4.5 Tests (Strict TDD — RED → GREEN → REFACTOR)

**`test_linkedin_auth_cookie.py` NEW (~150-200 LOC)**:
1. `EnvLinkedInAuthCookieAdapter` happy-path: `cookie(SecretStr("AQEAAAAQEAAA"))` returns the value.
2. `EnvLinkedInAuthCookieAdapter` None path: `cookie(None)` returns `None`.
3. `Settings.linkedin_li_at` empty-string → `None` (3 input shapes: `""`, `SecretStr("")`, `None`).
4. `Settings.linkedin_li_at` non-empty ≥8 → `SecretStr` (e.g. `"AQEAAAAQEAAA"`).
5. `Settings.linkedin_li_at` present+<8 → raises `ValueError` con mensaje claro.
6. `Settings.linkedin_li_at` absent → `None` (env var unset).
7. `LinkedInScraperSettings.__repr__` masking: `auth_cookie=SecretStr("AQEAAAAQEAAA")` → repr contains `"<set>"`, NOT `"AQEAAAAQEAAA"`.
8. `LinkedInScraperSettings.__repr__` masking `None` case: repr contains `"<unset>"`.
9. `LinkedInScraperSettings.__eq__`/`__hash__` includes `auth_cookie`.

**`test_linkedin_auth_wall.py` NEW (~40-60 LOC)**:
1. `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` → `True` (the existing fixture has `<body class="auth-wall">` per obs #353).
2. `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML))` → `False` (healthy SERP, no auth-wall class).
3. `is_auth_wall(BeautifulSoup(<body class="auth-wall">` + 1 card)`)` → `False` (cards win, false positive suppressed).

**`test_linkedin_scraper.py` EXTEND (~60-90 LOC)**:
1. `auth_cookie=None` → `FakeBrowser.new_context_calls[0]` has NO `cookies` key (legacy path unchanged).
2. `auth_cookie=SecretStr("AQEAAAAQEAAA")` → `FakeBrowser.new_context_calls[0]["cookies"] == [{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]`.
3. Per-search injection: 1 call to `search()` → exactly 1 call to `add_cookies` (NOT per page in the loop).
4. Per-context scope: 2 calls to `search()` → 2 calls to `add_cookies` (one per `new_context` lifecycle).

**`test_conftest.py` EXTEND (~10-15 LOC)**: agregar `FakeLinkedInAuthCookiePort` companion con `__init__(self, cookie: SecretStr | None = None)` y `def cookie(self) -> SecretStr | None: return self._cookie`.

**`tests/integration/test_linkedin_auth_cookie.py` NEW (~60-90 LOC)**: end-to-end via `build_app(use_case=...)` con `FakeLinkedInAuthCookiePort(SecretStr("AQEAAAAQEAAA"))` — asserta que la cookie alcanza `ctx.add_cookies()` con el shape correcto cuando el route se invoca. NO live network (offline integration, no Playwright browser launch).

### 4.6 Quality gates

- `cd backend && bash scripts/check.sh` después de cada commit: `ruff check` + `ruff format --check` + `mypy --strict` + `pytest`.
- 1,142 baseline + 0 regresiones. Los ~17 nuevos scenarios pasan. Total estimado después del change: ~1,160+ passed / 13 skipped.
- `mypy --strict` verifica que el nuevo Protocol es satisfecho por `EnvLinkedInAuthCookieAdapter` + `FakeLinkedInAuthCookiePort` + cualquier test double.

## 5. Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `application/ports.py` | Modified | +`LinkedInAuthCookiePort` Protocol (~10-15 LOC) |
| `infrastructure/linkedin/auth_cookie.py` | **NEW** | `EnvLinkedInAuthCookieAdapter` (~20-30 LOC) |
| `infrastructure/linkedin/__init__.py` | Modified | Re-export del adapter (opcional) |
| `infrastructure/linkedin/scraper.py` | Modified | `LinkedInScraperSettings.auth_cookie` kwarg + `__repr__` masking; `search()` +`add_cookies()`; `_make_fetch_one_page` +`is_auth_wall()` check |
| `infrastructure/linkedin/parsers.py` | Modified | +`is_auth_wall(soup)` (~10-20 LOC) |
| `infrastructure/config.py` | Modified | +`linkedin_li_at: SecretStr \| None` + 2 `field_validator`s (mode=before empty→None, mode=after <8→ValueError) |
| `presentation/app_factory.py` | Modified | Construye `EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)` y lo inyecta en `LinkedInScraperSettings`; WARNING log al startup si `None` |
| `backend/.env.example` | Modified | +`LINKEDIN_LI_AT=` placeholder line con nota de seguridad |
| `backend/README.md` | Modified | +`### LinkedIn auth cookie (optional)` subsection en "Manual verification" |
| `backend/tests/conftest.py` | Modified | +`FakeLinkedInAuthCookiePort` companion |
| `tests/unit/test_linkedin_auth_cookie.py` | **NEW** | 9 scenarios (port + validator + repr masking) |
| `tests/unit/test_linkedin_auth_wall.py` | **NEW** | 3 scenarios (detector happy-path + edge cases) |
| `tests/unit/test_linkedin_scraper.py` | Modified | +4 scenarios (cookie injection shape + per-search lifecycle) |
| `tests/integration/test_linkedin_auth_cookie.py` | **NEW** | 1-2 end-to-end scenarios (offline integration) |
| `application/aggregator.py`, `application/usecases/*` | UNCHANGED | Cookie es internal al scraper |
| `presentation/routes/*`, `presentation/schemas.py` | UNCHANGED | HTTP contract preservado |
| `frontend/*` | UNCHANGED | Sin cambios en tipos, ninguna llamada nueva |
| `infrastructure/indeed/scraper.py`, `infrastructure/infojobs/scraper.py` | UNCHANGED | Anti-bot distinto |
| `infrastructure/pagination.py` | UNCHANGED | Helper source-agnostic |
| `application/ports.py` `JobSearchPort`, `LocationResolverPort`, `JobSearchCacheKey` | UNCHANGED | Cookie NO es parte del Port/Resolver/CacheKey |

## 6. Decisión arquitectónica (las preguntas que la propuesta cierra)

**Q1 (failure mode) — orchestrator preflight resolvió opción C**: HARD `ValueError` cuando `LINKEDIN_LI_AT` está presente y `len < 8`; soft WARNING log cuando ausente. **Justificación**: preserva v1 zero-config boot (operador sin cookie = app arranca, scraper corre anónimo, WARNING log) Y atrapa typos comunes (`LINKEDIN_LI_AT=abc` falla fast con mensaje claro). El threshold de 8 chars es arbitrario pero suficiente para descartar typos obvios (las `li_at` reales tienen ~150+ chars). Tests cubren los 4 paths (unset, empty, set+<8, set+≥8).

**Q3 (defensive detector) — orchestrator preflight resolvió include**: agregar `is_auth_wall(soup)` + 2-3 tests + 1 línea en el closure. **Justificación**: <50 LOC de costo, real operator-observability value (dice "tu cookie expiró" antes de que el usuario vea 0-result responses), y el closure pattern ya vive en el source. El `is_block_page` existente NO se toca — son funciones con semánticas distintas.

**Q2 (injection point) — explore §5 Q2 resuelto**: per-context, per-search. Single call site en `scraper.py:274-277` entre `new_context()` y `new_page()`. La cookie viaja con cada `page` request del loop automáticamente (Playwright `BrowserContext` comparte cookie store con todas las pages en el context).

**Q4 (README structure) — orchestrator preflight resolvió new_subsection**: agregar `### LinkedIn auth cookie (optional)` AFTER los subsections LinkedIn-related existentes. **Justificación**: preserva el manual verification path para operadores sin cookie (v1 behavior); el nuevo subsection es opt-in (link desde el index del README).

**Q5 (test cookie value) — explore §5 Q5 resuelto**: 12-byte ASCII sintético (`"AQEAAAAQEAAA"`). El test asserta el call shape, NO el page shape. **No live capture needed** (resuelve el HIGH risk de obs #254 — la cookie NO requiere DOM render para validarse, sólo el call a `ctx.add_cookies`).

**Alternativas rejected**:
- **Cookie via HTTP header injection (`ctx.set_extra_http_headers({"Cookie": "li_at=..."})`)** — funciona pero NO se persiste en el cookie store de Playwright; rompe CSRF cookies que LinkedIn setea via Set-Cookie. El approach `add_cookies` es el canon de Playwright y maneja ambos correctamente.
- **Reusable `BrowserContext` (cache entre `search()` calls)** — más rápido pero acopla el state entre queries (cookie expirada en una query afecta todas las siguientes). El approach per-search es el v1 pattern (`new_context()` por `search()`); la cookie se aplica UNA vez por `search()`.
- **Cookie en `JobSearchCacheKey`** — rompe el cache contract: una cookie expirada cambia el resultado del SERP pero el cache hit NO debería servir un resultado cacheado con cookie distinta. La cookie es side-effect state, no input.
- **`is_auth_wall` reemplaza `is_block_page`** — son funciones distintas: `is_block_page` = "0 cards + auth signals" = HARD block (502 path); `is_auth_wall` = "results rendered pero degraded" = WARNING path (operator observability). Conviven; reemplazar uno con otro pierde información.

## 7. Open Questions (decisiones del usuario)

**None — todas las preguntas abiertas (Q1, Q3, Q4) fueron resueltas en preflight**. El orchestrator preguntó al usuario antes de invocar `sdd-propose`; las 3 respuestas (C / include / new_subsection) están locked-in en este proposal. Las otras 2 preguntas (Q2 injection point, Q5 synthetic cookie value) fueron resueltas durante `sdd-explore` (obs #353 §5) y NO requieren user input adicional.

**Si el user quiere abrir de nuevo alguna decisión en `sdd-spec`/`sdd-design`**: la forma más limpia es responder "sí, revert" a la decisión correspondiente — el proposal se actualiza con un revision marker y `sdd-spec`/`sdd-design` siguen con el nuevo default.

## 8. Riesgos

| # | Riesgo | Likelihood | Mitigación |
|---|--------|------------|------------|
| 1 | `li_at` cookie real leak al repo (AGENTS.md rule #7 violation) | M | Triple guardrail: (a) `SecretStr` type enmascara repr/str; (b) `__repr__` override retorna `"<set>"`/`"<unset>"`; (c) test fixture usa valor sintético (`"AQEAAAAQEAAA"`, 12 bytes), no valor real; (d) `.env.example` con `LINKEDIN_LI_AT=` empty + nota "NEVER commit" |
| 2 | Cookie expirada produce resultados degradados sin que el operador lo sepa | M | `is_auth_wall` detector + WARNING log cuando el SERP renderiza auth-wall class con 0 cards (el caso típico de cookie expirada). El operador ve el log, rota la cookie |
| 3 | LinkedIn cambia el formato de la cookie (de `li_at` a `JSESSIONID` o similar) | L | El cookie name está hardcodeado como `li_at`; un cambio de LinkedIn requiere un PR de seguimiento. Mitigación: el design phase debe documentar el cookie name como un constant (no un string literal repetido) |
| 4 | `add_cookies` API change en Playwright (breaking change en upgrade) | L | Playwright es `>=1.45` pinned; el call shape es estable desde v1.10 (5+ años). Mitigación: el design phase pin la version |
| 5 | Validator mode=after de `Settings.linkedin_li_at` rechaza un `li_at` legítimo futuro si LinkedIn acorta las cookies (<8 chars) | L | Threshold de 8 chars es arbitrario pero cubre typos obvios; las `li_at` reales son ~150 chars. Si LinkedIn acorta las cookies, el threshold se baja en un follow-up |
| 6 | Backward compat: `FakeLocationResolver` en `conftest.py` (y otros test doubles) no implementan el nuevo Protocol — no rompe (no usan el Protocol), pero cualquier nuevo test que use `LinkedInScraperSettings` con `auth_cookie` debe pasar el adapter explícitamente | L | `FakeLinkedInAuthCookiePort` companion en `conftest.py` documenta el default `None` (anonymous); tests existentes siguen GREEN sin cambios |
| 7 | Race condition: 2 `search()` calls concurrentes en distintos event loops podrían compartir state si el `BrowserContext` se reusara — NO es el caso (cada `search()` abre un fresh `new_context()` y cierra en `finally`) | L | El `async with` pattern del `try/finally` en `search()` (`scraper.py:278-295`) garantiza isolation; el `add_cookies` corre dentro del `try` y aplica al context específico |
| 8 | Conflict con el parallel `backend-infojobs-provinces` change (obs #330) — ambos extienden la config | L | `infojobs-provinces` no toca el bloque LinkedIn (sus settings son `infojobs_*`-prefixed); los 2 changes son ortogonales y pueden mergear en cualquier orden |
| 9 | `is_auth_wall` false positives: una página healthy con `class="auth-wall"` en algún elemento incidental (e.g. un card link) dispara el WARNING | M | El detector sólo retorna True cuando `<body class="auth-wall">` está presente Y 0 cards. La regla "cards win, no false positive" se pin en `test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class` |
| 10 | Operador configura `LINKEDIN_LI_AT` con un valor expirado (>1 año) — el scraper corre con la cookie muerta, el `is_auth_wall` detector eventualmente dispara | M | Documentado en README ("¿qué pasa si mi cookie expira?" FAQ). El detector es la mitigation; el operador ve el log y rota la cookie |
| 11 | El test `test_linkedin_auth_cookie.py` no cubre la path "Settings ctor raises" en isolation — depende del integration test del campo | L | 2 unit tests cubren el validator mode=after (`test_settings_linkedin_li_at_rejects_short_value`, `test_settings_linkedin_li_at_accepts_long_value`); el integration test cubre el wire completo |

## 9. Rollback Plan

Cada cambio es independientemente revertible (3 commits lógicos):

- **Commit 1 (port + adapter + settings)**: revert el commit que modifica `application/ports.py` + crea `infrastructure/linkedin/auth_cookie.py` + modifica `infrastructure/config.py` + extiende `tests/conftest.py`. El Protocol desaparece; `Settings.linkedin_li_at` desaparece; el adapter desaparece; el scraper corre anónimo (v1 behavior preservado). Los tests existentes siguen GREEN.
- **Commit 2 (scraper + parsers + tests)**: revert el commit que modifica `infrastructure/linkedin/scraper.py` (kwarg `auth_cookie`, `__repr__` masking, `add_cookies` call) + `infrastructure/linkedin/parsers.py` (`is_auth_wall`) + `tests/unit/test_linkedin_*.py` + `tests/integration/test_linkedin_auth_cookie.py`. El scraper vuelve a la v1 path (no cookie, no auth-wall detector). Los tests existentes siguen GREEN.
- **Commit 3 (docs + .env.example)**: revert el commit que modifica `backend/README.md` + `backend/.env.example`. Cero impacto en runtime.

**Zero-downtime rollback**: el Protocol es backward-compat (no afecta a scrapers que no usen `LinkedInScraperSettings.auth_cookie`). Un deploy con el Protocol agregado pero el scraper NO actualizado es seguro (el scraper no llama al adapter nuevo, default `auth_cookie=None` = anonymous path).

**Runtime kill switch**: `LINKEDIN_LI_AT=` (empty) en `.env` deshabilita la cookie en runtime — el scraper corre anónimo sin re-deploy. El WARNING log al startup confirma el estado.

## 10. Dependencies

**No new external dependencies.** Todo en stdlib + código existente:
- `pydantic.SecretStr` (ya importado en `config.py:23`)
- `pydantic.field_validator` (ya importado en `config.py:24`)
- `pydantic.AliasChoices` (ya importado en `config.py:22`)
- `Playwright BrowserContext.add_cookies` (ya disponible vía `self._browser` en `scraper.py:193`)
- `bs4.BeautifulSoup.select_one` / `select` (ya importado en `parsers.py:21`)

**No new env vars** beyond `LINKEDIN_LI_AT` (added in this change).

**No new spec files en `openspec/specs/`** — las 2 new capabilities (`linkedin-auth-cookie`, `linkedin-auth-wall-detector`) se crean en `openspec/changes/backend-linkedin-auth/specs/{capability}/spec.md` y se sincronizan al archive (mismo pattern que `linkedin-scraper` en obs #302 y `aggregator-relevance` en obs #322).

## 11. Success Criteria

- `Settings()` ctor en `backend/.env.example` con `LINKEDIN_LI_AT=` (empty) arranca el app limpiamente: log WARNING "LinkedIn scraper running without auth cookie", scraper corre anónimo, NO raise.
- `Settings()` ctor con `LINKEDIN_LI_AT=abc` (3 chars) raises `ValueError` con mensaje "must be at least 8 characters".
- `Settings()` ctor con `LINKEDIN_LI_AT=AQEAAAAQEAAA` (12 chars) arranca limpiamente: scraper inyecta la cookie via `ctx.add_cookies` antes del primer navigation.
- `LinkedInPlaywrightScraper.search()` con `auth_cookie=SecretStr("AQEAAAAQEAAA")` invoca `ctx.add_cookies` exactamente UNA vez por `search()` (no per-page) con `cookies=[{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]`.
- `LinkedInScraperSettings.__repr__()` con `auth_cookie=SecretStr("AQEAAAAQEAAA")` retorna un string que contiene `"<set>"` y NO contiene `"AQEAAAAQEAAA"`.
- `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` returns `True` (el fixture tiene `<body class="auth-wall">`).
- `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML))` returns `False`.
- `is_auth_wall(BeautifulSoup(<body class="auth-wall">` + 1 card)`)` returns `False` (cards win, false positive suppressed).
- Cuando `is_auth_wall` returns `True` durante un `search()`, el logger emite un WARNING con el mensaje "LinkedIn SERP appears auth-walled despite cookie injection; cookie may be expired".
- Los 1,142+ tests existentes siguen GREEN sin modificación.
- 4 quality gates GREEN: `pytest` (1,160+ passed / 13 skipped), `mypy --strict`, `ruff check`, `ruff format --check`.
- ≥17 nuevos tests: ≥9 en `test_linkedin_auth_cookie.py`, ≥3 en `test_linkedin_auth_wall.py`, ≥4 en `test_linkedin_scraper.py`, ≥1-2 en `test_linkedin_auth_cookie.py` (integration).
- `sdd-verify` PASS con 0 critical findings.

## 12. Workload Forecast & Suggested Tasks

**Total estimado**: ~80-130 LOC prod + ~310-440 tests + ~35-60 docs = **~425-630 LOC netos** (incluyendo tax de strict TDD). Muy por debajo del presupuesto de 5000 líneas del orchestrator. **Single PR es suficiente — no chained PR needed**.

**Tareas (para `sdd-tasks`)**:

- **T-001**: NEW `EnvLinkedInAuthCookieAdapter` en `infrastructure/linkedin/auth_cookie.py` + `LinkedInAuthCookiePort` Protocol en `application/ports.py`. RED test: `test_port_protocol_structural_conformance`. GREEN: implementar el Protocol + el adapter. 1 commit, ~30-45 LOC.
- **T-002**: NEW `Settings.linkedin_li_at: SecretStr | None` field + 2 `field_validator`s (mode=before empty→None, mode=after <8→ValueError) en `infrastructure/config.py`. RED tests: 4 scenarios (unset, empty, set+<8, set+≥8). GREEN: agregar el field + los 2 validators. 1 commit, ~30-45 LOC.
- **T-003**: EXTEND `LinkedInScraperSettings` con `auth_cookie` kwarg + `__repr__` masking + `__slots__`/`__eq__`/`__hash__` extension. RED tests: 3 scenarios (`__repr__` masking set, masking unset, `__eq__`/`__hash__` includes field). GREEN: implementar. 1 commit, ~20-30 LOC.
- **T-004**: EXTEND `LinkedInPlaywrightScraper.search()` con `ctx.add_cookies` entre `new_context()` y `new_page()`. RED tests: 4 scenarios (no-cookie no-call, with-cookie shape match, per-search not per-page, 2-searches 2-calls). GREEN: implementar. 1 commit, ~20-30 LOC.
- **T-005**: NEW `is_auth_wall(soup)` en `infrastructure/linkedin/parsers.py` + integration en el closure de `_make_fetch_one_page` con WARNING log. RED tests: 3 scenarios (BLOCK_PAGE_HTML → True, SEARCH_PAGE_HTML → False, cards+auth-wall-class → False). GREEN: implementar. 1 commit, ~25-40 LOC.
- **T-006**: Wire en `app_factory.build_app()`: `EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)` se construye una vez, se inyecta como `auth_cookie=` kwarg. WARNING log al startup si `None`. Integration test: `tests/integration/test_linkedin_auth_cookie.py` (1-2 scenarios end-to-end offline). 1 commit, ~40-60 LOC.
- **T-007**: `FakeLinkedInAuthCookiePort` companion en `tests/conftest.py`. 1 commit, ~10-15 LOC.
- **T-008**: EXTEND `backend/README.md` con `### LinkedIn auth cookie (optional)` subsection + `backend/.env.example` con `LINKEDIN_LI_AT=` placeholder line. 1 commit, ~35-60 LOC docs.
- **T-009**: Integration final + `bash scripts/check.sh` + commit de polish (type annotations, docstrings, comments).

**Review strategy**: single PR con 8-9 commits (uno por tarea). Cada commit ~10-60 LOC, independientemente revertible. El work-unit-commits pattern aplica directamente.

## 13. Next Step

Listo para `sdd-spec`. El orchestrator debe:

1. Confirmar que las 3 Open Questions (§7) están todas locked-in (Q1=C, Q3=include, Q4=new_subsection) — ya confirmadas en preflight, no requiere user input adicional.
2. Confirmar single PR vs. chained (recomiendo single PR; el cambio es pequeño, ortogonal al `backend-infojobs-provinces` paralelo, well-bounded a un solo Protocol + 1 Settings field + 1 parsers function).
3. Verificar que el paralelo `backend-infojobs-provinces` no toca el bloque LinkedIn (obs #330 propone `infojobs_*` settings, no `linkedin_li_at` — sin colisión, OK).
4. Delegar a `sdd-spec` para escribir:
   - 2 NEW specs: `openspec/changes/backend-linkedin-auth/specs/linkedin-auth-cookie/spec.md` (5-6 REQ-) + `openspec/changes/backend-linkedin-auth/specs/linkedin-auth-wall-detector/spec.md` (2-3 REQ-).
   - 2 delta specs: `openspec/changes/backend-linkedin-auth/specs/linkedin-scraper/spec.md` (auth_cookie kwarg + add_cookies call + is_auth_wall closure integration) + `openspec/changes/backend-linkedin-auth/specs/linkedin-config/spec.md` (Settings.linkedin_li_at + 2 validators).

**Skill resolution**: `paths-injected` — orchestrator pre-resolvió `sdd-propose/SKILL.md` + `_shared/sdd-phase-common.md` + `_shared/openspec-convention.md` + `test-driven-development/SKILL.md`.
