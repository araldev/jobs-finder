# Propuesta: `backend-linkedin-location-fallback`

> **Cambio**: `backend-linkedin-location-fallback` • **Modo**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
> **Fecha**: 2026-06-10 • **Base**: `f41aa90` (post `backend-scraper-query-tuning` merge, main; 1,142 passed / 13 skipped)
> **Upstream**: obs #302 (fix-linkedin-geoid archive — el resolver base), obs #322 (`backend-scraper-query-tuning` proposal §11 follow-up #2 — pre-acordó este cambio), obs #330 (parallel `backend-infojobs-provinces` explore — coordina el Protocol shape).

## 1. Intención

El `HardcodedLocationResolver` (obs #302) traduce 34 strings canónicos a un `geoId` numérico de LinkedIn (vía `?geoId=<int>`). Para cualquier ciudad NO presente en el dict — `Antequera`, `Fuengirola`, `Marbella`, `Toledo`, `Salamanca`, `Cádiz`, `Granada`, `Gijón`, `León`, `Vigo`, etc. — el LinkedIn scraper cae al fallback legacy `?location=<raw_str>`, que LinkedIn **silently ignora** y retorna resultados sin filtro de ubicación (este es el gap residual del `backend-scraper-query-tuning`: el usuario siguió viendo 8 ofertas de "DataAnnotation" en "Washington" para `?q=react&location=Antequera`).

El usuario encontró una **URL real de LinkedIn** que muestra un tercer formato soportado: `?location=<city>,<province>,<country>` (ej. `location=Antequera,Andalucía,Spain` URL-decoded de `Antequera%2CAndaluc%C3%ADa%2CSpain`). LinkedIn's fuzzy match funciona mejor con el triplet estructurado que con un string crudo. Este cambio agrega un fallback intermedio `?location=City,Province,Country` para ciudades con triplet conocido pero sin geoId capturado. El fallback legacy `?location=<raw>` se preserva para ciudades sin NINGÚN mapping (no regresión).

## 2. Alcance

### 2.1 Dentro de alcance

| # | Mejora | Archivos | Esfuerzo |
|---|---|---|---|
| 1 | `LocationResolverPort` crece un segundo método `resolve_structured(location) -> tuple[str, str, str] | None` | `application/ports.py` (Protocol) | ~5-10 LOC |
| 2 | `HardcodedLocationResolver` implementa `resolve_structured` con reuso de la normalización 4-step + alias chain | `infrastructure/location/hardcoded_resolver.py` | ~30-50 LOC |
| 3 | Nuevo módulo `_structured_mapping.py` con el dict de triplets `dict[str, tuple[str, str, str]]` para ciudades sin geoId | `infrastructure/location/_structured_mapping.py` (NEW) | ~30-50 LOC (data) |
| 4 | `LinkedInPlaywrightScraper.search()` consulta `resolve_structured` después de `resolve`; el resultado se captura en el closure de `_make_fetch_one_page` | `infrastructure/linkedin/scraper.py` | ~15-25 LOC delta |
| 5 | `_build_url` acepta un nuevo kwarg `structured: tuple[str, str, str] | None`; prioridad `geoId > structured > raw` | `infrastructure/linkedin/scraper.py` | ~15-20 LOC delta |
| 6 | `FakeLocationResolver` en `tests/conftest.py` (y los 2-3 test doubles en otros archivos) ganan el segundo método con default `None` | `tests/conftest.py`, `tests/unit/test_*.py` (EXTEND) | ~10-15 LOC delta |
| 7 | Tests del resolver: ~12-16 nuevos scenarios (tabla-driven) | `tests/unit/test_hardcoded_location_resolver.py` (EXTEND) | ~120-180 LOC |
| 8 | Tests del scraper: ~3-4 nuevos scenarios cubriendo la prioridad de URL building y URL encoding con tildes | `tests/unit/test_linkedin_scraper.py` (EXTEND) | ~50-80 LOC |
| 9 | README — nota en "LinkedIn manual verification" + tabla de triplet support | `backend/README.md` (MODIFY) | ~30-50 LOC |
| 10 | 1 LIVE test gated `LLM_LIVE_TESTS=1` (no en CI per AGENTS.md rule #1) que verifica que `?q=react&location=Antequera` retorna ofertas en Málaga/Andalucía | `tests/integration/test_linkedin_live.py` (EXTEND o NEW) | ~30-50 LOC |

**Total estimado**: ~150-200 LOC prod + ~200-300 LOC tests + ~30-50 docs = **~380-550 LOC netos** (~600-800 LOC con tax de strict TDD). Muy por debajo del presupuesto de 5000 líneas del orchestrator. **Single PR es suficiente — no chained PR needed**.

### 2.2 Fuera de alcance

- Agregar nuevas ciudades al `_CANONICAL_MAPPING` (geoIds) — el user debe capturar geoIds adicionales con `scripts/capture_linkedin_geo_ids.py` (sanctioned per AGENTS.md rule #1). Este change NO modifica `_mapping.py`.
- Cambiar el InfoJobs scraper — eso es el cambio paralelo `backend-infojobs-provinces` (obs #330), que se mergeará de forma independiente.
- Cambiar el v1 chat-filter path (`_execute_v1` en `FilterJobsByIntentUseCase`) — el v1 path no llama al resolver (verificado en `filter_jobs_by_intent.py:267-277, 525-527, 660-662`); modificar el v1 path es un follow-up separado. El usuario obtiene el beneficio del nuevo fallback en el chat 2-stage + el `/jobs` route.
- Soporte para ciudades en otros idiomas (Berlin, Tokyo, etc.) — la estructura soporta extensión, pero el dict v1 cubre solo ciudades españolas. Agregar `("Tokio", "Tokio", "Japan")` o `("Berlin", "Berlin", "Germany")` es trivial en un follow-up.
- Cambiar la firma primaria `resolve(location) -> int | None` — se mantiene intacta. El segundo método es ADITIVO.
- Auto-detección del country desde el input — el country es siempre "Spain" (o el country que el user añada explícitamente al dict). No hay heurística.
- Mover el `_CANONICAL_MAPPING` a un JSON file o DB — mismo pattern hardcoded que ya existe; el `_STRUCTURED_MAPPING` sigue el mismo patrón.
- Mover el resolver a un patrón async — el lookup es dict, sub-microsegundo, no vale la pena el cambio.

## 3. Capabilities (contrato con `sdd-spec`)

### 3.1 New
- `linkedin-structured-location-fallback`: la capacidad del `HardcodedLocationResolver` de retornar un triplet `(city, province, country)` para ciudades sin geoId capturado, y del LinkedIn scraper de usar ese triplet como `?location=<city>,<province>,<country>` antes de caer al fallback legacy. La capability cubre las 5-7 REQ- que `sdd-spec` redactará (canonical lookup, alias normalization, alias-to-canonical recurse, None semantic, URL formula priority, URL encoding con tildes, backward compat).

### 3.2 Modified (delta specs)
- `linkedin-scraper` (REQ-L-001..L-010, REQ-LOC-GEO-001..009): la URL formula crece una rama intermedia (priority `geoId > structured > raw`); la firma de `_build_url` y `_make_fetch_one_page` crece un kwarg.
- `location-resolver` (REQ-LOC-GEO-001..009): el Protocol crece un segundo método `resolve_structured`; el impl `HardcodedLocationResolver` implementa ambos.

### 3.3 Sin cambios
- `domain` (Job, exceptions), `infrastructure/indeed/scraper.py`, `infrastructure/infojobs/scraper.py`, `application/aggregator.py`, `application/usecases/search_linkedin_jobs.py`, `application/usecases/filter_jobs_by_intent.py`, `presentation/schemas.py`, `presentation/routes/*`, `frontend/*`. El HTTP contract es preservado (frontend sigue enviando `location=...`; el resolver convierte internamente).

## 4. Enfoque técnico

### 4.1 Cambio 1: Extender `LocationResolverPort` con `resolve_structured`

En `application/ports.py:170`, agregar el segundo método al Protocol existente:

```python
class LocationResolverPort(Protocol):
    def resolve(self, location: str) -> int | None: ...
    def resolve_structured(self, location: str) -> tuple[str, str, str] | None: ...
```

El método retorna `(city, province, country)` en Title Case con tildes preservadas (NFC), o `None` si el input no tiene triplet conocido. El docstring del Protocol documenta que los dos métodos son independientes: una ciudad puede tener solo `geoId`, solo `structured`, ambos, o ninguno.

**Backward compat**: mypy --strict detecta que cualquier `FakeLocationResolver` o test double existente deja de satisfacer el Protocol. **Mitigation**: extender el `FakeLocationResolver` en `tests/conftest.py` con `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` (default `None` = legacy fallback). Los tests existentes siguen GREEN.

### 4.2 Cambio 2: `HardcodedLocationResolver.resolve_structured`

En `infrastructure/location/hardcoded_resolver.py`, agregar el método:

```python
def resolve_structured(self, location: str) -> tuple[str, str, str] | None:
    if not location:
        return None
    normalized = self._normalize(location)  # reuso
    canonical_key = self._aliases.get(normalized, normalized)
    if canonical_key in self._structured_mapping:
        return self._structured_mapping[canonical_key]
    _logger.warning(
        "HardcodedLocationResolver: could not resolve location %r to a structured "
        "(city, province, country) triplet. Falling back to ?location=<str>.",
        location,
    )
    return None
```

Reuso de `_normalize` (misma 4-step chain NFC + casefold + strip + remove accents) y `_ALIASES` (alias-to-canonical recurse). El ctor agrega un kwarg `structured_mapping: Mapping[str, tuple[str, str, str]] | None = None` (default = el nuevo `_STRUCTURED_MAPPING`).

**Prioridad de URL building en `_build_url`** (camino nuevo):

```python
@staticmethod
def _build_url(
    keywords: str, location: str, start: int,
    geo_id: int | None = None,
    structured: tuple[str, str, str] | None = None,
) -> str:
    if geo_id is not None:
        return f"https://www.linkedin.com/jobs/search/?keywords={quote(keywords)}&geoId={geo_id}&start={start}"
    if structured is not None:
        city, province, country = structured
        formatted = f"{city},{province},{country}"
        return f"https://www.linkedin.com/jobs/search/?keywords={quote(keywords)}&location={quote(formatted)}&start={start}"
    # Legacy fallback
    return f"https://www.linkedin.com/jobs/search/?keywords={quote(keywords)}&location={quote(location)}&start={start}"
```

**URL encoding con tildes**: `urllib.parse.quote("Antequera,Andalucía,Spain")` retorna `Antequera%2CAndaluc%C3%ADa%2CSpain` (NFC composed, exactamente el formato de la URL capturada del usuario). Las tildes se preservan; el fallback legacy `?location=Antequera` produce `location=Antequera` (sin el triplet).

### 4.3 Cambio 3: Nuevo `_structured_mapping.py`

```python
# infrastructure/location/_structured_mapping.py
"""Structured (city, province, country) triplets for cities without a captured geoId.

Complements `_mapping.py`: the canonical mapping returns LinkedIn geoIds (numeric,
highest-priority format). The structured mapping returns Title Case triplets
suitable for `?location=City,Province,Country` (LinkedIn's second-best format
for fuzzy matching).

Add new entries here when:
  - A user reports a city not in the canonical mapping (no geoId captured).
  - The triplet is verified to work (LIVE test, gated `LLM_LIVE_TESTS=1`).
"""
_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]] = {
    "antequera": ("Antequera", "Andalucía", "Spain"),
    "fuengirola": ("Fuengirola", "Málaga", "Spain"),
    "marbella": ("Marbella", "Málaga", "Spain"),
    "toledo": ("Toledo", "Castilla-La Mancha", "Spain"),
    "salamanca": ("Salamanca", "Castilla y León", "Spain"),
    "cadiz": ("Cádiz", "Andalucía", "Spain"),
    "granada": ("Granada", "Andalucía", "Spain"),
    "gijon": ("Gijón", "Asturias", "Spain"),
    "leon": ("León", "Castilla y León", "Spain"),
    "vigo": ("Vigo", "Galicia", "Spain"),
}
```

Los 10 entries son la lista recomendada; el user puede agregar/quitar en el PR. Cada triplet es Title Case con tildes preservadas; el `_normalize` se encarga del matching contra el input del user (lowercase + sin tildes en el lookup, Title Case + con tildes en el output).

### 4.4 Cambio 4-5: `LinkedInPlaywrightScraper.search()` + `_make_fetch_one_page` + `_build_url`

En `search()` (líneas 249-250), después de resolver el `geo_id`, también resolver el `structured`:

```python
structured: tuple[str, str, str] | None = None
if geo_id is None and self._settings.location_resolver is not None:
    geo_id = self._settings.location_resolver.resolve(location)
    structured = self._settings.location_resolver.resolve_structured(location)
```

Pasar `structured=structured` a `paginated_search` (vía el closure, igual que `geo_id`).

En `_make_fetch_one_page(keywords, location, geo_id=None, structured=None)`, capturar `structured` en el closure y pasarlo a `_build_url(...)` en cada page.

En `_build_url`, agregar el kwarg `structured` con la prioridad `geoId > structured > raw` documentada arriba.

### 4.5 Tests (Strict TDD — RED → GREEN → REFACTOR)

**`test_hardcoded_location_resolver.py` EXTEND (~12-16 scenarios nuevos)**:
1. `resolve_structured` happy-path para cada una de las 10 entries del dict (parametrized).
2. `resolve_structured` alias normalization: NFC (`"Málaga"` vs `"Málaga"`), casefold (`"ANTEQUERA"`), strip (`"  Antequera  "`), remove accents (`"Cadiz"` → `"Cádiz"`).
3. `resolve_structured` alias-to-canonical recurse: e.g. `"costa del sol"` → (futuro alias) → `"marbella"` → triplet.
4. `resolve_structured` None semantic: unknown city (`"Atlantis"`), empty string (no warning), País Vasco / Canarias (no triplet — son CCAA sin city-level).
5. `resolve()` y `resolve_structured()` son independientes: una ciudad puede tener solo uno, solo el otro, o ambos (e.g. `Madrid` tiene `geoId` pero NO structured; `Antequera` tiene structured pero NO geoId; `Barcelona` tiene ambos — no, en v1 solo `geoId`).
6. Ctor custom `structured_mapping` override (same pattern as `mapping` override).
7. `mapping` y `structured_mapping` son independientes (cambiar uno no afecta al otro).

**`test_linkedin_scraper.py` EXTEND (~3-4 scenarios nuevos)**:
1. `_build_url(geo_id=None, structured=("Antequera", "Andalucía", "Spain"))` → `?keywords=...&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=...` (URL-encoded with tildes).
2. Priority `geoId > structured`: `_build_url(geo_id=103374081, structured=("Antequera", "Andalucía", "Spain"))` → uses `geoId=`, NOT `structured`.
3. Priority `structured > raw`: `_build_url(geo_id=None, structured=("Antequera", "Andalucía", "Spain"), location="raw_str")` → uses `structured`, NOT `raw_str`.
4. Fallback legacy: `_build_url(geo_id=None, structured=None, location="Atlantis")` → `?location=Atlantis` (no triplet, no geoId — the broken-but-doesn't-500 path).
5. `_make_fetch_one_page` captures `structured` in closure and emits the same URL on every page.
6. URL encoding con caracteres especiales: `("León", "Castilla y León", "Spain")` → `Le%C3%B3n%2CCastilla%20y%20Le%C3%B3n%2CSpain`.

**`test_conftest.py` EXTEND (~3-5 LOC)**: agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` al `FakeLocationResolver`.

**Integration `test_chat_endpoint_2stage.py` EXTEND (~1 scenario)**: end-to-end con `intent.location="Antequera"` → resolver returns `("Antequera", "Andalucía", "Spain")` → LinkedIn scraper receives `structured=("Antequera", "Andalucía", "Spain")` → URL contains `location=Antequera%2CAndaluc%C3%ADa%2CSpain`. (Assert via `FakeJobSearchPort` recording the structured kwarg, no Playwright.)

**`test_linkedin_live.py` NEW (gated `LLM_LIVE_TESTS=1`)**: 1 LIVE test contra LinkedIn real. `query=react&location=Antequera` → assert that all returned jobs have `location` containing "Antequera" OR "Málaga" OR "Andalucía" (no "Washington"). NO se ejecuta en CI per AGENTS.md rule #1.

### 4.6 Quality gates

- `cd backend && bash scripts/check.sh` después de cada commit: `ruff check` + `ruff format --check` + `mypy --strict` + `pytest`.
- 1,142 baseline + 0 regresiones. Los ~20 nuevos scenarios pasan. Total estimado después del change: ~1,160 passed / 13 skipped.
- `mypy --strict` verifica que el Protocol extendido es satisfecho por `HardcodedLocationResolver` + `FakeLocationResolver` + cualquier test double.

## 5. Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `application/ports.py` | Modified | Protocol `LocationResolverPort` + 1 método `resolve_structured` (línea 170-208) |
| `infrastructure/location/hardcoded_resolver.py` | Modified | +`resolve_structured` + ctor kwarg `structured_mapping` (línea 40-151) |
| `infrastructure/location/_structured_mapping.py` | **NEW** | Dict de triplets `dict[str, tuple[str, str, str]]` (data, ~10 entries) |
| `infrastructure/location/__init__.py` | Modified | Re-export del dict (opcional, para que tests lo importen) |
| `infrastructure/linkedin/scraper.py` | Modified | `search()` + `_make_fetch_one_page` + `_build_url` aceptan `structured`; prioridad `geoId > structured > raw` |
| `backend/tests/conftest.py` | Modified | `FakeLocationResolver` + 1 método default `None` |
| `tests/unit/test_hardcoded_location_resolver.py` | Modified | +12-16 scenarios structured lookup |
| `tests/unit/test_linkedin_scraper.py` | Modified | +3-4 scenarios URL priority + URL encoding |
| `tests/integration/test_chat_endpoint_2stage.py` | Modified | +1 scenario end-to-end structured plumb |
| `tests/integration/test_linkedin_live.py` | **NEW** (opcional) | 1 LIVE test gated `LLM_LIVE_TESTS=1` |
| `backend/README.md` | Modified | Nota en "LinkedIn manual verification" + tabla de triplet support |
| `.env.example` | UNCHANGED | No new env vars |
| `frontend/src/**` | UNCHANGED | HTTP contract preservado |

## 6. Decisión arquitectónica (la pregunta que la propuesta cierra)

**Q (de explore §8)**: ¿Extender `LocationResolverPort` con un segundo método (`resolve_structured`), crear un sibling resolver separado, o usar tagged union en el mismo método?

**A (esta propuesta)**: **Extender `LocationResolverPort` con un segundo método `resolve_structured(location) -> tuple[str, str, str] | None`**.

**Justificación** (repite explore §6 con la decisión locked-in):

1. **Type clarity per-source**: cada método retorna el shape exacto que su consumer necesita (`int | None` para `geoId`; `tuple[str, str, str] | None` para triplet). No tuple abuse ni discriminated unions.
2. **Mirrors `LLMClientPort` pattern**: ya tenemos `complete()` + `stream_complete()` en `application/ports.py:374-451`. Multi-method Protocol es el pattern del codebase.
3. **Backward compat**: el `FakeLocationResolver` en `conftest.py` agrega el segundo método con default `None`. Los ~51 unit tests existentes de `test_hardcoded_location_resolver.py` siguen GREEN (solo testean `resolve()`; los nuevos tests testean `resolve_structured()`).
4. **Composition root sin cambios**: el `HardcodedLocationResolver` ya está wired en 3 call sites (scraper settings, `app.state`, chat use case). Un solo objeto implementa ambos métodos.
5. **Normalización reusada**: la 4-step chain se llama 2 veces (una por método), no hay duplicación.

**Alternativas rejected** (resumidas):
- **Sibling resolver `StructuredLocationResolver`**: dos clases, dos wirings, dos dicts; la normalización se duplica. Más LOC, más complexity, mismo resultado.
- **Tagged union en `resolve()`**: type abuse (discriminated union); rompe `geo_id: int | None` en `JobSearchCacheKey` 5to field; el `isinstance(...)` se repite en cada call site.

## 7. Open Questions (decisiones del usuario)

1. **¿Qué ciudades entran en `_STRUCTURED_MAPPING`?** La propuesta lista 10 ciudades (Antequera, Fuengirola, Marbella, Toledo, Salamanca, Cádiz, Granada, Gijón, León, Vigo). El user puede agregar/quitar. **Recomendación**: ship con 8-10 ciudades validadas por el user; agregar más es trivial.
2. **¿Las ciudades YA en el dict de geoIds (Madrid, Barcelona, etc.) entran también al structured mapping?** **Recomendación**: NO. El `geoId` es LinkedIn's preferred format y siempre gana. El structured solo aplica cuando NO hay geoId. Si una ciudad tiene ambos (raro en v1), se usa el geoId.
3. **¿`resolve_structured` aplica al v1 path también?** El v1 path (`_execute_v1`) no llama al resolver. **Recomendación**: NO en v1 — el v1 path es legacy. Si el user quiere el beneficio, que habilite 2-stage.
4. **¿`Remote` tiene structured triplet?** El `_CANONICAL_MAPPING` ya tiene `remote → 118424786`. **Recomendación**: NO structured para `remote` — el geoId es LinkedIn's "worldwide remote" y es superior.
5. **¿`Spain` country-level entra como fallback universal?** **Recomendación**: NO — sería el peor caso (pierde city).
6. **¿Country en español (`"España"`) o inglés (`"Spain"`)?** La URL real del user dice `"Spain"`. **Recomendación**: hardcodear `"Spain"` (inglés) en el dict; agregar alias `españa → spain` + `espana → spain` (sin tilde) en `_ALIASES` por si el frontend envía el nombre español.

**Default de los 6 si el user no responde antes de `sdd-spec`**: aplicar las recomendaciones (lista de 10 ciudades, NO duplicar con geoIds, NO v1 path, NO `Remote` structured, NO `Spain` fallback universal, country en inglés + alias español).

## 8. Riesgos

| # | Riesgo | Likelihood | Mitigación |
|---|--------|------------|------------|
| 1 | El formato `?location=City,Province,Country` puede NO funcionar para todas las ciudades (LinkedIn's fuzzy match es impredecible) | M | LIVE test gated `LLM_LIVE_TESTS=1` verifica el format con Antequera; si el user reporta fallos, la ciudad se quita del dict; el fallback legacy `?location=<raw>` se preserva para los misses |
| 2 | Country en español vs. inglés — el frontend podría enviar `España` y LinkedIn esperar `Spain` (o viceversa) | M | Dict hardcodea `Spain` (matching el example real del user); alias `españa → spain` + `espana → spain` cubre el caso español; tests pin ambos |
| 3 | Province naming con/sin tildes — el dict usa `Andalucía` (con tilde) y el `_normalize` preserva las tildes en el OUTPUT (no en el lookup key) | L | El `_normalize` quita tildes del lookup key pero el dict value preserva tildes; tests pin ambos formatos |
| 4 | El dict de triplets crece a 30+ entries — `_structured_mapping.py` se vuelve largo | L | 10 entries v1; el patrón hardcoded es el mismo que `_CANONICAL_MAPPING` (34 entries). No migrar a JSON. |
| 5 | Backward compat con ciudades sin NINGÚN mapping (Tokio, Berlin) | L | El fallback legacy `?location=<raw>` se preserva. Test `test_resolve_structured_unknown_city_returns_none` pin explícitamente. |
| 6 | URL building priority race condition — futuros métodos al Protocol podrían romper la prioridad | L | Comment explícito en `_build_url` documentando `geoId > structured > raw`; 4 tests pinnean la prioridad |
| 7 | El v1 path no usa el nuevo structured — usuario podría sorprenderse | M | Documentar en README "v1 path requires `INTENT_EXTRACTION_ENABLED=true` for full resolver behavior"; tests existentes de v1 no cambian |
| 8 | `FakeLocationResolver` en `conftest.py` necesita el segundo método para satisfacer el Protocol | L | Agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` al fake; mypy detecta cualquier otro test double que no lo tenga |
| 9 | Conflict con el paralelo `backend-infojobs-provinces` (obs #330) — ambos extienden `LocationResolverPort` con métodos nuevos | L | Los métodos son aditivos (no colisionan nombres: `resolve_structured` vs `resolve_infojobs`); el orchestrator coordina el orden de merge; el conflict en `LocationResolverPort` se resuelve manualmente |
| 10 | El dict hardcoded no se puede extender sin redeploy | L | Mismo pattern que `_CANONICAL_MAPPING` (34 entries hardcoded); el equipo ha aceptado este trade-off. JSON file es un follow-up si el dict crece past ~30 |

## 9. Rollback Plan

Cada cambio es independientemente revertible:
- **Cambio 1 (Protocol + impl)**: revert el commit que modifica `application/ports.py` + `infrastructure/location/hardcoded_resolver.py` + `_structured_mapping.py`. 1 commit.
- **Cambio 2 (scraper URL builder)**: revert el commit que modifica `infrastructure/linkedin/scraper.py`. 1 commit. El scraper vuelve a la URL formula `geoId | location=` (sin la rama `structured`).
- **Tests + docs**: revert los commits de tests + README.

**Zero-downtime rollback**: el Protocol extendido es backward-compat (los test doubles agregan el método con default `None`). Un deploy con el Protocol extendido pero el scraper NO actualizado es seguro (el scraper no llama al método nuevo).

**Runtime kill switch**: NO necesario para v1 (el dict es read-only, no hay env var). Si una ciudad causa problemas, se quita del dict en un commit siguiente.

## 10. Dependencies

**No new external dependencies.** Todo en stdlib + código existente:
- `urllib.parse.quote` (ya importado en `scraper.py:55`)
- `unicodedata` (ya importado en `hardcoded_resolver.py:30`)
- `logging` (ya importado en `hardcoded_resolver.py:29`)

**No new env vars.** El dict es hardcoded; no hay `STRUCTURED_MAPPING_ENABLED` ni equivalente.

**No new spec files en `openspec/specs/`** — la capability `linkedin-structured-location-fallback` se crea en `openspec/changes/backend-linkedin-location-fallback/specs/linkedin-structured-location-fallback/spec.md` y se sincroniza al archive (mismo pattern que `aggregator-relevance` en obs #322).

## 11. Success Criteria

- `GET /jobs?q=react&location=Antequera` retorna SOLO ofertas en Antequera/Málaga/Andalucía (verificable con LIVE test contra LinkedIn real con `LLM_LIVE_TESTS=1`).
- `GET /jobs?q=react&location=Fuengirola` retorna SOLO ofertas en Fuengirola/Málaga/Andalucía.
- Las 8 ciudades del `HardcodedLocationResolver` (Madrid, Barcelona, Valencia, Sevilla, Zaragoza, Málaga, Murcia, Bilbao) SIGUEN usando `?geoId=<int>` (priority `geoId > structured`).
- Una ciudad NO en ningún mapping (e.g. `"Tokio"`, `"Berlin"`) sigue cayendo al legacy `?location=<raw>` (no regresión vs. hoy).
- Los 51+ tests existentes de `test_hardcoded_location_resolver.py` siguen GREEN sin modificación.
- Los 6+ tests existentes de `test_linkedin_scraper.py` siguen GREEN sin modificación.
- Los tests existentes de `test_chat_endpoint_2stage.py` (end-to-end) siguen GREEN.
- 4 quality gates GREEN: `pytest` (1,160+ passed / 13 skipped), `mypy --strict`, `ruff check`, `ruff format --check`.
- ≥12 nuevos tests en `test_hardcoded_location_resolver.py`, ≥3 en `test_linkedin_scraper.py`, ≥1 en `test_chat_endpoint_2stage.py`, 1 LIVE test gated.
- `sdd-verify` PASS con 0 critical findings.

## 12. Workload Forecast & Suggested Tasks

**Total estimado**: ~150-200 LOC prod + ~200-300 tests + ~30-50 docs = **~380-550 LOC netos** (~600-800 LOC con tax de strict TDD). Muy por debajo del presupuesto de 5000 líneas del orchestrator. **Single PR es suficiente — no chained PR needed**.

**Tareas (para `sdd-tasks`)**:

- **T-001**: NEW `_structured_mapping.py` con el dict de triplets (~10 entries) + `__init__.py` re-export. 1 commit, ~50 LOC.
- **T-002**: EXTEND `LocationResolverPort` Protocol con `resolve_structured()` (RED test: `test_protocol_has_resolve_structured_method` que verifica que `HardcodedLocationResolver` implementa el método). GREEN: agregar el método al Protocol + al `HardcodedLocationResolver` (con la normalización 4-step reusada). 1 commit, ~30-50 LOC.
- **T-003**: EXTEND `test_hardcoded_location_resolver.py` con 12-16 scenarios structured lookup (happy-path, alias normalization, None semantic, ctor override, independence of mappings). 1 commit, ~120-180 LOC tests.
- **T-004**: EXTEND `LinkedInPlaywrightScraper.search()` + `_make_fetch_one_page` + `_build_url` con el kwarg `structured` + prioridad `geoId > structured > raw`. 1 commit, ~30-45 LOC prod.
- **T-005**: EXTEND `test_linkedin_scraper.py` con 3-4 scenarios URL priority + URL encoding con tildes. 1 commit, ~50-80 LOC tests.
- **T-006**: EXTEND `FakeLocationResolver` en `tests/conftest.py` con `resolve_structured` default `None`. 1 commit, ~3-5 LOC.
- **T-007**: EXTEND `test_chat_endpoint_2stage.py` con 1 end-to-end scenario (`intent.location="Antequera"` → URL contains `location=Antequera%2CAndaluc%C3%ADa%2CSpain`). 1 commit, ~30-50 LOC tests.
- **T-008**: EXTEND `backend/README.md` con nota en "LinkedIn manual verification" + tabla de triplet support + 1 LIVE test gated (opcional, no bloquea el PR). 1 commit, ~30-50 LOC docs.
- **T-009**: Integration final + `bash scripts/check.sh` + commit de polish.

**Review strategy**: single PR con 5-9 commits (uno por tarea). Cada commit ~30-180 LOC, independientemente revertible. El work-unit-commits pattern aplica directamente.

## 13. Next Step

Listo para `sdd-spec`. El orchestrator debe:
1. Confirmar las 6 Open Questions (§7) con el user antes de `sdd-spec` — defaults propuestos en §7 si el user no responde.
2. Confirmar single PR vs. chained (recomiendo single PR; el cambio es pequeño y aditivo).
3. Verificar que el paralelo `backend-infojobs-provinces` no está en el mismo Protocol (obs #330 propone `resolve_infojobs`, no `resolve_structured` — sin colisión de nombres, OK).
4. Delegar a `sdd-spec` para escribir:
   - 1 NEW spec: `openspec/changes/backend-linkedin-location-fallback/specs/linkedin-structured-location-fallback/spec.md` con 5-7 REQ-.
   - 2 delta specs: `openspec/changes/backend-linkedin-location-fallback/specs/location-resolver/spec.md` (Protocol + impl) + `openspec/changes/backend-linkedin-location-fallback/specs/linkedin-scraper/spec.md` (URL formula priority).

**Skill resolution**: `paths-injected` — orchestrator pre-resolvió `sdd-propose/SKILL.md` + `_shared/SKILL.md` + `openspec-convention.md` + `engram-convention.md` + `persistence-contract.md`.
