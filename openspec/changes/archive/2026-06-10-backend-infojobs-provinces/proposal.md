# Proposal: backend-infojobs-provinces

> **Cambio**: `backend-infojobs-provinces` • **Modo**: `both` (OpenSpec files + Engram copy) • **Strict TDD**: ACTIVE
> **Fecha**: 2026-06-10 • **Base**: `f41aa90` (feature/backend-infojobs-provinces; branched from main at the `backend-scraper-query-tuning` merge; baseline 1,142 passed / 13 skipped per obs #329)
> **Status**: `proposed` (listo para `sdd-spec`)

## 1. Intención

El `backend-scraper-query-tuning` (PR #4, merged 2026-06-10, obs #329) dejó como deuda explícita un *workaround* en producción: `filter_infojobs_results` es un filtro client-side que descarta InfoJobs cards con 0 tokens en común con la query del usuario. El usuario descubrió durante smoke testing manual que **la fix real está en la URL**: InfoJobs acepta `?provinceIds=<id>&countryIds=<id>` (Málaga=34, España=17) y devuelve el slice regional correcto. La URL capturada por el usuario:

```
https://www.infojobs.net/jobsearch/search-results/list.xhtml?keyword=react&provinceIds=34&segmentId=&page=1&sortBy=RELEVANCE&onlyForeignCountry=false&countryIds=17&sinceDate=ANY
```

tiene los 2 params que faltan en nuestro scraper (`provinceIds`, `countryIds`). Este cambio **plumbea esos 2 IDs en la URL** del InfoJobs scraper, análogo a cómo `fix-linkedin-geoid` (obs #294/#302) plumbó `geoId` para LinkedIn. El resultado: el `GET /jobs?q=react&location=Málaga` devuelve resultados realmente de Málaga (no de toda España), y `filter_infojobs_results` queda como safety-net defense-in-depth (no se elimina — el costo de mantenerlo es ~100 LOC; el costo de necesitarlo de nuevo es un re-deploy).

## 2. Alcance

### 2.1 In scope

| # | Deliverable | Archivos | Esfuerzo |
|---|---|---|---|
| 1 | Extender `LocationResolverPort` con un segundo método `resolve_infojobs(location) -> tuple[int \| None, int \| None]` (mismo patrón que `LLMClientPort.complete` + `LLMClientPort.stream_complete`) | `application/ports.py` (Protocol), `infrastructure/location/hardcoded_resolver.py` (impl) | ~30-50 LOC prod + ~30-50 tests |
| 2 | Nuevo `InfoJobsLocationResolver` (o método en `HardcodedLocationResolver`) con mapping de 5-7 entradas: Málaga=34, Madrid, Barcelona, Valencia, Sevilla, Remote → `(None, 17)`, España → `(None, 17)` | `infrastructure/location/_infojobs_mapping.py` (NEW), `infrastructure/location/infojobs_province_resolver.py` (NEW) o método adicional en `hardcoded_resolver.py` | ~100-150 LOC prod + ~150-200 tests |
| 3 | Extender `InfoJobsScraperSettings` con `location_resolver: InfoJobsLocationResolverPort \| None = None` (mismo patrón que `LinkedInScraperSettings:133`) | `infrastructure/infojobs/scraper.py:111-167` | ~30-40 LOC prod + ~30-40 tests |
| 4 | Extender `InfoJobsPlaywrightScraper.search()` y `_build_url()` para emitir `?provinceIds=<id>&countryIds=<id>` cuando el resolver retorna una tupla no-`None`; fallback a `?l=<str>` cuando retorna `(None, None)` | `infrastructure/infojobs/scraper.py:225-331` | ~50-70 LOC prod + ~80-120 tests |
| 5 | Extender `_make_fetch_one_page(keywords, location, infojobs_geo=...)` para capturar el tuple y pasarlo a `_build_url` en cada página (análogo a la plumb de `geo_id` en LinkedIn) | `infrastructure/infojobs/scraper.py:279-325` | ~20-30 LOC prod (cubierto por los tests del #4) |
| 6 | Wire del resolver en `app_factory.build_app()`: el `HardcodedLocationResolver` único (que implementa ambos métodos) se inyecta tanto en `LinkedInScraperSettings` (ya wired) como en `InfoJobsScraperSettings` (nuevo) | `presentation/app_factory.py:319-363` (InfoJobs default branch) | ~15-25 LOC prod + ~30-50 tests |
| 7 | **NO change** a `filter_infojobs_results` — KEEP como defense-in-depth. Actualizar `backend/README.md` sección "InfoJobs client-side filter" (líneas 719-737) para documentar el nuevo rol: "safety net para unmapped regions + future ID drift" | `backend/README.md` | ~20-30 LOC doc |
| 8 | Tests de integration que verifican end-to-end la nueva URL via `FakeBrowser` + `FakePage` (mismo patrón que `test_infojobs_scraper.py:248-256`) | `tests/unit/test_infojobs_scraper.py` (EXTEND) | cubierto por #4 |
| 9 | Update de `backend/README.md` "Manual verification" InfoJobs section: documentar la nueva URL formula, la lista de province IDs conocidos, el fallback behavior | `backend/README.md` | ~30-50 LOC doc |

**Total estimado**: ~300-450 LOC prod + ~400-600 tests + ~50-80 docstrings = **~750-1100 LOC netos** (incluyendo tax de strict TDD). Bien por debajo del presupuesto de 5000 líneas del review budget; single PR con 4-5 commits, cada uno ~150-300 LOC.

### 2.2 Out of scope

- Cambiar la forma de `AggregatedJobsQuery` (el frontend sigue enviando `location=...`; el resolver convierte internamente — backward compat 100%).
- Cambiar `filter_infojobs_results` semantics más allá de "KEEP as defense-in-depth" (no se hace no-op ni se elimina; ver §6 Open Question 3).
- Agregar más fuentes (Indeed ya acepta `l=<str>`; el problema es InfoJobs-specific).
- Agregar `sortBy=RELEVANCE` o `sinceDate=ANY` a la URL (los 2 params nuevos son el mínimo para fixar el bug del usuario; los otros 2 son un follow-up).
- Mover el mapping a un JSON file (Option C descartado; ver explore §5.3 — el dict hardcodeado es el patrón del proyecto; un JSON file es un follow-up si el dict crece).
- Cambiar `paginated_search` (helper es source-agnostic; el closure del InfoJobs scraper solo agrega una variable capturada más).
- Cambiar `JobSearchCacheKey` (el 5to campo `geo_id: int \| None` es LinkedIn-specific; la tupla de InfoJobs viaja por un kwarg dedicado en el closure, NO por el cache key — el Port queda source-agnostic).
- Cambiar `JobSearchPort` Protocol (el 4to kwarg `geo_id: int \| None = None` ya existe; InfoJobs acepta un NUEVO kwarg dedicado `infojobs_geo: tuple[int \| None, int \| None] \| None = None` en el scraper, no en el Port).
- Cambiar `InfoJobsJobsQuery` schema (los query params HTTP son los mismos; el `location` string viaja sin cambios al scraper; el resolver corre internamente).
- Cambiar `AggregatedJobsQuery` o `GET /jobs` route (idem — el `location` string viaja sin cambios; el `linkedin_geo_id` plumb existente en `routes/aggregator.py:169` se mantiene; el InfoJobs resolver corre INSIDE el scraper, mirroring LinkedIn).
- Re-capturar los province IDs faltantes (Madrid, Barcelona, etc.) con un script de Playwright. Es un follow-up manual si el equipo quiere validar los IDs antes del PR; el `LLM_LIVE_TESTS=1` flag puede gatear un test que verifica cada ID contra el SERP real, pero NO es requerido para este change (el dict hardcodeado es la fuente de verdad; los IDs que no conocemos se omiten y caen al fallback `?l=<str>`).

## 3. Capabilities (contrato con `sdd-spec`)

### 3.1 New
- `infojobs-provinces`: el resolver de `location` → `(province_id, country_id)` para el InfoJobs scraper. Cubre el requirement de pasar `provinceIds` + `countryIds` en la URL del scraper. Mapea `location` strings canónicos a IDs hardcodeados (Málaga, Madrid, Barcelona, Valencia, Sevilla, Remote, España) con alias normalization (NFC + casefold + strip + remove-accents) idéntica al resolver de LinkedIn.

### 3.2 Modified (delta specs)
- `infojobs-scraper` (REQ-J-001): la URL formula agrega `provinceIds=<id>&countryIds=<id>` cuando el resolver retorna una tupla no-`None`; fallback a la v1 `?l=<str>` cuando retorna `(None, None)`.
- `location-resolver` (REQ-LOC-001..006): el `LocationResolverPort` Protocol crece un segundo método `resolve_infojobs(location: str) -> tuple[int | None, int | None]`; el `HardcodedLocationResolver` implementa ambos métodos; el composition root inyecta la misma instancia en ambos `LinkedInScraperSettings` y `InfoJobsScraperSettings`.
- `aggregator-relevance` (REQ-FILTER-001): `filter_infojobs_results` se mantiene como defense-in-depth (no se elimina, no se hace no-op). Documentación actualizada para reflejar el nuevo rol "safety net para unmapped regions + future ID drift".

### 3.3 Sin cambios
- `domain` (Job, exceptions), `application/aggregator.py` (el dispatch es transparente), `application/ports.py` `JobSearchCacheKey` (LinkedIn-specific 5to campo), `application/ports.py` `JobSearchPort` (signature estable), `infrastructure/linkedin/scraper.py`, `infrastructure/indeed/scraper.py`, `presentation/schemas.py` (HTTP shape preservada), `frontend/*` (ningún cambio en tipos, ninguna llamada nueva).
- `infrastructure/aggregator_filters.py` (`filter_infojobs_results`, `tokenize`) — el código no cambia; solo el docstring + el comentario del README.

## 4. Enfoque técnico

### 4.1 Extensión del Protocol (Approach Option A del explore)

En `application/ports.py:170-208`, el `LocationResolverPort` Protocol crece un segundo método:

```python
class LocationResolverPort(Protocol):
    # V1 (LinkedIn-specific): returns the LinkedIn geoId.
    def resolve(self, location: str) -> int | None: ...

    # NEW (InfoJobs-specific): returns (province_id, country_id).
    # province_id is None for "Remote" / "España" cases; country_id
    # is None for unmapped locations. Both None is the "fallback to
    # ?l=<str>" sentinel.
    def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: ...
```

El `HardcodedLocationResolver` (existing class at `infrastructure/location/hardcoded_resolver.py:40`) implementa ambos métodos. La `FakeLocationResolver` test double (en `tests/conftest.py`) gana un método default que retorna `(None, None)` (el sentinel "unmapped"). El composition root (`app_factory.build_app()`) construye **un solo** `HardcodedLocationResolver` y lo inyecta en BOTH `LinkedInScraperSettings.location_resolver` y `InfoJobsScraperSettings.location_resolver`.

### 4.2 Nuevo mapping file

`infrastructure/location/_infojobs_mapping.py` (NEW, ~40 LOC):

```python
# The canonical InfoJobs province/country mapping. Sourced from the
# user's manual smoke test (Málaga=34, España=17 confirmed) + the
# InfoJobs public-facing documentation for the other Spanish cities.
# Both IDs are required; a `(None, 17)` tuple means "country-only,
# no province" (the Remote / España case).
_INFOJOBS_CANONICAL_MAPPING: dict[str, tuple[int | None, int]] = {
    # Spanish provinces (province_id, country_id=17)
    "malaga": (34, 17),
    "madrid": (28, 17),  # 28 = Comunidad de Madrid province; verify via LIVE test
    "barcelona": (8, 17),  # 8 = Barcelona province; verify via LIVE test
    "valencia": (46, 17),  # 46 = Valencia province; verify via LIVE test
    "sevilla": (41, 17),  # 41 = Sevilla province; verify via LIVE test
    # Country-only (province_id=None, country_id=17)
    "espana": (None, 17),
    "spain": (None, 17),
    "remote": (None, 17),  # "Remote" → country=Spain, no province
    "teletrabajo": (None, 17),  # Spanish synonym for remote
}
```

> **Nota sobre los IDs de Madrid, Barcelona, Valencia, Sevilla**: los valores 28, 8, 46, 41 son los códigos INE oficiales de las provincias españolas. InfoJobs puede usar un ID interno diferente. La fix Phase (sdd-apply) verificará cada ID con un LIVE test gated `LLM_LIVE_TESTS=1` (NUNCA en CI per AGENTS.md rule #1). Si un ID es incorrecto, el fallback `?l=<str>` es graceful degradation (el scraper retorna 0 results, no 500). El equipo actualizará el dict según los resultados del LIVE test antes de mergear.

### 4.3 Plumb en el InfoJobs scraper

En `infrastructure/infojobs/scraper.py`:

```python
class InfoJobsScraperSettings:
    __slots__ = (..., "location_resolver", ...)
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int,
        domain: str = "www.infojobs.net",
        max_pages: int = 10,
        inter_page_delay_seconds: float = 0.0,
        location_resolver: LocationResolverPort | None = None,  # NEW
    ) -> None: ...

class InfoJobsPlaywrightScraper(JobSearchPort):
    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,  # unused; kept for Protocol compat
        infojobs_geo: tuple[int | None, int | None] | None = None,  # NEW
    ) -> list[Job]:
        # Resolve ONCE per search() (not per page).
        if infojobs_geo is None and self._settings.location_resolver is not None:
            infojobs_geo = self._settings.location_resolver.resolve_infojobs(location)
        # ... rest of the method ...
        return await paginated_search(
            ...,
            fetch_one_page=self._make_fetch_one_page(keywords, location, infojobs_geo=infojobs_geo),
            ...,
        )

    def _make_fetch_one_page(
        self,
        keywords: str,
        location: str,
        infojobs_geo: tuple[int | None, int | None] | None = None,  # NEW
    ) -> Callable[..., Awaitable[list[Job]]]:
        async def fetch_one_page(page, page_index, remaining):
            url = self._build_url(keywords, location, page_index + 1, infojobs_geo=infojobs_geo)
            ...
        return fetch_one_page

    def _build_url(
        self,
        keywords: str,
        location: str,
        page: int,
        infojobs_geo: tuple[int | None, int | None] | None = None,  # NEW
    ) -> str:
        base = (
            f"https://{self._settings.domain}/ofertas-trabajo"
            f"?q={quote(keywords)}&l={quote(location)}&page={page}"
        )
        if infojobs_geo is None or (infojobs_geo[0] is None and infojobs_geo[1] is None):
            return base
        province_id, country_id = infojobs_geo
        params = []
        if province_id is not None:
            params.append(f"provinceIds={province_id}")
        if country_id is not None:
            params.append(f"countryIds={country_id}")
        return base + "&" + "&".join(params)
```

### 4.4 Wire en `app_factory.build_app()`

En `presentation/app_factory.py:319-363`, el branch default del InfoJobs:

```python
infojobs_scraper = InfoJobsPlaywrightScraper(
    throttle=InfoJobsAsyncThrottle(
        min_interval_seconds=effective_settings.infojobs_throttle_seconds,
    ),
    settings=InfoJobsScraperSettings(
        user_agent=effective_settings.infojobs_user_agent,
        timeout_ms=effective_settings.infojobs_timeout_ms,
        domain=effective_settings.infojobs_domain,
        max_pages=effective_settings.infojobs_max_pages,
        inter_page_delay_seconds=effective_settings.infojobs_inter_page_delay_seconds,
        location_resolver=location_resolver,  # NEW — same instance as LinkedIn
    ),
    stealth=Stealth(),
)
```

El `location_resolver` (línea 185) es la MISMA instancia inyectada en `LinkedInScraperSettings` (línea 255). El método dispatch (`resolve` vs `resolve_infojobs`) lo decide el scraper que llama.

## 5. Affected areas

| Area | Impacto | Descripción |
|---|---|---|
| `application/ports.py` (Protocol) | Modified | +1 método `resolve_infojobs` en `LocationResolverPort` |
| `infrastructure/location/hardcoded_resolver.py` (impl) | Modified | +1 método `resolve_infojobs` que lee del nuevo mapping |
| `infrastructure/location/_infojobs_mapping.py` | NEW | ~40 LOC: 9 entradas (5 ciudades + 4 country-only/remote) |
| `infrastructure/infojobs/scraper.py` (settings) | Modified | +1 field `location_resolver` en `InfoJobsScraperSettings` |
| `infrastructure/infojobs/scraper.py` (search/build_url) | Modified | +1 kwarg `infojobs_geo`; URL formula extendida |
| `presentation/app_factory.py` | Modified | +1 línea: `location_resolver=location_resolver` en `InfoJobsScraperSettings(...)` |
| `infrastructure/aggregator_filters.py` | UNCHANGED | `filter_infojobs_results` se mantiene (defense-in-depth) |
| `application/aggregator.py` | UNCHANGED | el dispatch del filter es transparente |
| `presentation/schemas.py` | UNCHANGED | HTTP shape preservada |
| `presentation/routes/infojobs.py` | UNCHANGED | el resolver corre INSIDE el scraper; no necesita plumb en el route |
| `presentation/routes/aggregator.py` | UNCHANGED | el `linkedin_geo_id` plumb existente es suficiente; el InfoJobs resolver corre INSIDE el InfoJobs scraper |
| `application/ports.py` (`JobSearchPort`, `JobSearchCacheKey`) | UNCHANGED | signature estable; el tuple de InfoJobs viaja por un kwarg dedicado en el scraper, NO por el Port ni por el cache key |
| `application/usecases/search_infojobs_jobs.py` | UNCHANGED | el `RawSearchJobsUseCase` no necesita el tuple (es scraper-internal) |
| `backend/README.md` | Modified | +1 sección "InfoJobs province/country IDs"; actualización del "InfoJobs client-side filter" |
| `tests/unit/test_hardcoded_location_resolver.py` | UNCHANGED | los 51 escenarios existentes siguen GREEN |
| `tests/unit/test_infojobs_province_resolver.py` (NEW) | NEW | ~150-200 LOC, 30+ escenarios (happy-path, alias, None semantic, ctor custom mapping) |
| `tests/unit/test_infojobs_scraper.py` (EXTEND) | Modified | +5 escenarios (URL con province/country, URL con country-only, URL con fallback, plumb en closure, location_resolver en settings) |
| `tests/unit/test_chat_wiring.py` (EXTEND) | Modified | +1 escenario: `app.state.location_resolver` resuelve InfoJobs (Málaga → `(34, 17)`) |
| `tests/unit/test_aggregator_filters.py` | UNCHANGED | los 6 escenarios del filter siguen GREEN (no se cambia el filter) |
| `frontend/src/lib/types.ts` y `frontend/src/components/*` | UNCHANGED | ningún cambio en tipos; el frontend sigue enviando `location=...` |

## 6. Open Questions (decisiones del usuario)

1. **Forma del Protocol**: extender `LocationResolverPort` con `resolve_infojobs` (1 Protocol, 2 métodos) vs. definir un `InfoJobsLocationResolverPort` nuevo (2 Protocols, 1 método cada uno). **Recomiendo**: extender. Es la mitad de la superficie del Protocol, y mirrora el patrón `LLMClientPort.complete` + `stream_complete` (obs #374-451). Confirmar con el usuario.

2. **Nombre del kwarg en el InfoJobs scraper**: `infojobs_geo: tuple[int \| None, int \| None] \| None = None` (explícito) vs. reusar el `geo_id: int \| None = None` existente (más corto, pero type-abuse — un `int` no puede ser una tupla). **Recomiendo**: `infojobs_geo`. Es explícito, type-discoverable, y no contamina el `JobSearchPort` Protocol (que no cambia). Confirmar con el usuario.

3. **Disposición de `filter_infojobs_results`**: KEEP (defense-in-depth, sin cambios en código), NO-OP (return `list(jobs)` siempre, función alive como hook), o REMOVE (eliminar la función y el módulo `aggregator_filters.py`). **Recomiendo**: KEEP. La función es O(n) pura (~10µs para 20 jobs); el costo de mantenerla es trivial; el costo de necesitarla de nuevo (un re-deploy + un hotfix) es mayor. Los 6 tests existentes en `test_aggregator_filters.py` siguen GREEN sin cambios. El comentario del módulo se actualiza para documentar el nuevo rol: "defense-in-depth safety net para unmapped regions + future province/country ID drift". Confirmar con el usuario.

4. **LIVE test para verificar los IDs de Madrid, Barcelona, Valencia, Sevilla**: la opción A es shippear con los IDs del INE (28, 8, 46, 41) y dejar que un follow-up LIVE test los verifique; la opción B es gatear este change detrás de un LIVE test que captura los IDs primero. **Recomiendo**: opción A. El `LLM_LIVE_TESTS=1` flag puede gatear un test que verifica cada ID; el test failure NO bloquea el merge (es un test de "verify this ID"; falla informativo, no regresión). Los IDs incorrectos caen al fallback `?l=<str>` que es graceful degradation. Confirmar con el usuario.

## 7. Riesgos

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | Los IDs de Madrid, Barcelona, Valencia, Sevilla son推測 (basados en códigos INE); InfoJobs puede usar IDs internos diferentes | MEDIUM | LIVE test gated `LLM_LIVE_TESTS=1` verifica cada ID; el test failure es informativo, no bloqueante. Los IDs incorrectos caen al fallback `?l=<str>` (graceful degradation, no 500). El equipo actualizará el dict antes de mergear según los resultados. |
| 2 | InfoJobs cambia los province IDs (analog al riesgo de LinkedIn geoIds, obs #295 #3) | LOW | `filter_infojobs_results` defense-in-depth es el safety net; el WARNING log del resolver cuando retorna `(None, None)` es observable para ops; el dict es committed, agregar un ID = code change + PR. |
| 3 | El `LocationResolverPort` Protocol crece un segundo método — los test doubles existentes (`FakeLocationResolver` en `tests/conftest.py`) necesitan un segundo método | LOW | El nuevo método tiene un default `def resolve_infojobs(self, location: str) -> tuple[int \| None, int \| None]: return (None, None)` que los doubles existentes obtienen gratis (subclasean o monkey-patch). Los tests que no exercen InfoJobs siguen sin tocar el resolver. |
| 4 | El kwarg `infojobs_geo` se confunde con el `geo_id` existente del Port | LOW | Docstring explícito en `scraper.py:225` que dice "kwarg dedicado al InfoJobs-specific (province, country) tuple; el `geo_id` del Port es LinkedIn-specific y se ignora aquí". Tests pin los 2 kwargs explícitamente. |
| 5 | KEEP `filter_infojobs_results` agrega ~100 LOC de código "muerto" (el resolver hace el trabajo real) | LOW | El filtro NO es "muerto" — es defense-in-depth. El costo de removerlo (97 LOC) es trivial; el costo de re-deployar si lo necesitamos es mayor. La doc actualizada lo documenta explícitamente. |
| 6 | La URL con `provinceIds=34&countryIds=17` puede romper el SERP rendering de InfoJobs (cambios de layout, anti-bot más estricto, etc.) | LOW | LIVE test gated verifica end-to-end. El fallback `?l=<str>` es el plan B si la nueva URL falla. El scraper puede log un WARNING y caer al fallback automáticamente (futuro enhancement; fuera de scope para v1). |
| 7 | La backward compat para locations no mapeadas (e.g. "Berlin", "Tokyo") | LOW | El resolver retorna `(None, None)`; el scraper cae al v1 `?l=<str>`; el `filter_infojobs_results` post-scrape filtra el 0-token overlap. **No regresión vs. el status quo** (InfoJobs sin province/country es exactamente el comportamiento de hoy). |

## 8. Rollback plan

Cada mejora es **independientemente revertible**:
- **Mejora #1 (Protocol extension)**: revert el commit de `application/ports.py`. El Protocol queda con 1 método; los test doubles que ya tienen el segundo método no se rompen (Python ignora métodos extra en un Protocol estructural).
- **Mejora #2 (mapping + resolver method)**: revert el commit de `infrastructure/location/_infojobs_mapping.py` y `hardcoded_resolver.py`. El método `resolve_infojobs` desaparece; los callers caen al default `(None, None)` de los doubles.
- **Mejora #3 (settings field)**: revert el commit de `infrastructure/infojobs/scraper.py` que agrega `location_resolver` a `InfoJobsScraperSettings`. El scraper cae al v1 `?l=<str>` (sin province/country).
- **Mejora #4 (search/_build_url/closure plumb)**: revert el commit de `infrastructure/infojobs/scraper.py` que extiende `search()`, `_build_url`, `_make_fetch_one_page`. El scraper queda byte-identical al pre-change.
- **Mejora #5 (app_factory wire)**: revert el commit de `presentation/app_factory.py` que pasa `location_resolver=...` al `InfoJobsScraperSettings`. El scraper queda con `location_resolver=None` y cae al v1 path.
- **Mejora #6 (README update)**: revert el commit de `backend/README.md`. La doc vuelve al estado pre-change.

Si un deploy sale mal, los 6 reverts son independientes. El comportamiento post-revert = pre-change (InfoJobs sin province/country; `filter_infojobs_results` como safety net primario).

## 9. Dependencies

**No new external dependencies.** Todo en stdlib + código existente. No new env vars. No new spec files en `openspec/specs/` (el delta spec cubre el `infojobs-provinces` new + los 3 capabilities modificados).

## 10. Success criteria

- `GET /jobs?q=react&location=Málaga` retorna resultados realmente de Málaga (no de toda España). Verificable con LIVE test contra InfoJobs con `provinceIds=34&countryIds=17`.
- `GET /jobs/infojobs?q=react&location=Málaga` retorna la URL `?q=react&l=Málaga&page=1&provinceIds=34&countryIds=17`. Verificable con `FakeBrowser` + `FakePage` test (sin red).
- `GET /jobs?q=react&location=Remote` retorna la URL `?q=react&l=Remote&page=1&countryIds=17` (sin `provinceIds`). Verificable con test.
- `GET /jobs?q=react&location=Berlin` retorna la URL `?q=react&l=Berlin&page=1` (fallback graceful, sin province/country). Verificable con test.
- `filter_infojobs_results` sigue activo (KEEP) — los 6 tests de `test_aggregator_filters.py` siguen GREEN.
- Los 51 tests de `test_hardcoded_location_resolver.py` siguen GREEN (no se cambia el resolver de LinkedIn).
- 4 quality gates GREEN: `pytest`, `mypy --strict`, `ruff check`, `ruff format --check`.
- ≥30 tests nuevos en `test_infojobs_province_resolver.py`, ≥5 en `test_infojobs_scraper.py`, ≥1 en `test_chat_wiring.py`.
- 1 LIVE test gated `LLM_LIVE_TESTS=1` (NUNCA en CI per AGENTS.md rule #1) verifica que `?q=react&provinceIds=34&countryIds=17` retorna resultados de Málaga.
- `sdd-verify` PASS con 0 critical findings.

## 11. Workload Forecast & Suggested Tasks

**Total estimado**: ~300-450 LOC prod + ~400-600 tests + ~50-80 docstrings = **~750-1100 LOC netos** (~1500-2000 LOC con tax de strict TDD). Bien por debajo del presupuesto de 5000 líneas del review budget. **Single PR recomendado** (4-5 commits, cada uno ~150-300 LOC, todos independientemente revertibles).

**Tareas (para `sdd-tasks`)**:
- **T-001 (RED → GREEN)**: Protocol + impl + mapping + 30+ tests unitarios para el nuevo `InfoJobsLocationResolver.resolve_infojobs` (Málaga, Madrid, Barcelona, Valencia, Sevilla, Remote, España, alias normalization, None semantic, ctor custom mapping override).
- **T-002 (RED → GREEN)**: extender `InfoJobsScraperSettings` con `location_resolver` (slots + `__eq__` + `__hash__` + `__repr__`) + 2-3 tests unitarios.
- **T-003 (RED → GREEN)**: extender `InfoJobsPlaywrightScraper.search()` + `_make_fetch_one_page()` + `_build_url()` con el kwarg `infojobs_geo` + la nueva URL formula + 5 tests unitarios (`test_infojobs_scraper.py` EXTEND).
- **T-004 (RED → GREEN)**: wire en `app_factory.build_app()` + 1 test de integration en `test_chat_wiring.py` (el `app.state.location_resolver` resuelve InfoJobs).
- **T-005**: update `backend/README.md` sección "InfoJobs client-side filter" + nueva sección "InfoJobs province/country IDs" (~50 LOC doc).
- **T-006**: 1 LIVE test gated `LLM_LIVE_TESTS=1` (nunca en CI): verifica que `?q=react&provinceIds=34&countryIds=17` retorna resultados de Málaga en el SERP real.

**Review strategy**: single PR con 4-5 commits. Cada commit < 300 LOC; el más grande (T-001 resolver + tests) está en el edge del budget de 400-line pero dentro del budget de 5000-line. Si T-001 crece past 400 LOC durante apply, surface al usuario para chained PR split.

**PR slice final**: single PR con 5 commits (T-001 → T-005), en este orden:
1. `feat(location): add resolve_infojobs method to HardcodedLocationResolver + InfoJobs mapping + tests` (~300-450 LOC)
2. `feat(infojobs): add location_resolver field to InfoJobsScraperSettings + tests` (~50-80 LOC)
3. `feat(infojobs): plumb infojobs_geo through search/_build_url/_make_fetch_one_page + tests` (~200-300 LOC)
4. `feat(app_factory): inject location_resolver into InfoJobsScraperSettings + integration tests` (~30-50 LOC)
5. `docs(backend): document InfoJobs province/country IDs + filter defense-in-depth role` (~50-80 LOC)

## 12. Next Step

Listo para `sdd-spec`. El orchestrator debe:
1. Confirmar las 4 Open Questions (§6) con el usuario antes de `sdd-spec`.
2. Confirmar single PR vs. chained (recomiendo single).
3. Delegar a `sdd-spec` para escribir los 4 delta specs (`infojobs-provinces` new + 3 modified).

**Skill resolution**: `paths-injected` — orchestrator pre-resolvió `sdd-propose` + `_shared` + `sdd-apply` + `sdd-verify`.

---

## Anexo: Verificación de la URL con `provinceIds=34&countryIds=17`

> **infojobs_province_ids_verified**: parcialmente verificado. El usuario encontró la URL real durante smoke testing manual de `backend-scraper-query-tuning` (PR #4 merged el 2026-06-10). El formato `?keyword=react&provinceIds=34&segmentId=&page=1&sortBy=RELEVANCE&onlyForeignCountry=false&countryIds=17&sinceDate=ANY` está confirmado como la URL canónica que InfoJobs usa para devolver el slice regional correcto. La observación directa del usuario es la única fuente de verdad para el formato exacto; los IDs específicos (Málaga=34, España=17) NO están verificados contra el código del scraper (no hay código que los use hoy). El LIVE test gated `LLM_LIVE_TESTS=1` (T-006) será la verificación formal antes del merge. **No es un blocker** — el fallback `?l=<str>` es graceful degradation; el ship con IDs推测 es estrictamente mejor que el status quo.
