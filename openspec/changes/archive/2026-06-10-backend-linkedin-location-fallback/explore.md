# Exploration: `backend-linkedin-location-fallback`

> **Cambio**: `backend-linkedin-location-fallback` • **Modo**: `both` (OpenSpec + Engram)
> **Fecha**: 2026-06-10 • **Strict TDD**: ACTIVE • **Base**: `f41aa90` (post `backend-scraper-query-tuning` merge, main)

## 1. status
`explored`

## 2. executive_summary

El `HardcodedLocationResolver` actual (obs #302) traduce **34 strings** (8 ciudades ES + 16 CCAA + 9 ciudades LATAM + 1 remote) a un `geoId` numérico que LinkedIn acepta vía `?geoId=<int>`. **Cualquier ciudad que NO está en el dict cae a `?location=<raw_string>`** — y LinkedIn silently ignora ese string, retornando resultados sin filtro de ubicación (lo que el usuario vivió: 8 ofertas de "DataAnnotation" en "Washington, United States" para `?q=react&location=Málaga`).

El usuario encontró una URL real de LinkedIn que muestra un **tercer formato soportado**: `?location=<city>,<province>,<country>` (ej. `location=Antequera,Andalucía,Spain`). El fuzzy match de LinkedIn funciona mejor con este triplet estructurado que con un string crudo. El fix: cuando el resolver NO encuentra un `geoId`, intentar el segundo formato con un dict de triplets `(city → (province, country))`. Si tampoco hay triplet, caer al fallback `?location=<raw_string>` de hoy (sin regresión). Estructura limpia: extender `HardcodedLocationResolver` con un segundo método `resolve_structured(location) -> tuple[str, str, str] | None` que retorna el triplet. La composición root ya inyecta el resolver en el LinkedIn scraper settings; el scraper consulta AMBOS métodos en `search()`.

## 3. current_state_evidence

### 3.1 `HardcodedLocationResolver` y `_mapping.py` (verificado en `infrastructure/location/`)

- **Clase**: `HardcodedLocationResolver(LocationResolverPort)` en `hardcoded_resolver.py:40`.
- **Signature**: `def resolve(self, location: str) -> int | None` (línea 77). Único método público.
- **Mapping**: `_CANONICAL_MAPPING: dict[str, int]` en `_mapping.py:40-79` con **34 entries** (el título del módulo dice 34, no 43 como en el `fix-linkedin-geoid` original — el docstring explica que se excluyeron 9 entradas: País Vasco, Canarias, ES/MX/AR/CO/CL/PE country-level, y Aragón).
- **Aliases**: `_ALIASES: dict[str, str]` con 5 entries (`mad → madrid`, `bcn → barcelona`, `cdmx → ciudad_de_mexico`, `caba → buenos_aires`, `df → ciudad_de_mexico`).
- **Normalización**: NFC + casefold + strip + NFD-decompose + drop `Mn` marks (4 steps en `_normalize`, líneas 132-151).
- **Comportamiento de miss**: `None` + WARNING log (líneas 122-130). `""` short-circuits a `None` SIN warning (línea 107).
- **Ctor**: `__init__(*, mapping=None, aliases=None)` — ambos son pure override (no merge).

### 3.2 Mapping actual (34 entries — verificado)

| Categoría | Entries | Ejemplos |
|---|---|---|
| Ciudades ES (8) | `madrid, barcelona, valencia, sevilla, zaragoza, malaga, murcia, bilbao` | `malaga → 104401670` |
| CCAA ES (16) | `comunidad de madrid, cataluna, comunidad valenciana, andalucia, galicia, castilla y leon, castilla la mancha, extremadura, asturias, cantabria, la rioja, navarra, illes balears, ceuta, melilla, region de murcia` | `andalucia → 106151489` |
| Ciudades LATAM (9) | `ciudad de mexico, guadalajara, monterrey, buenos aires, cordoba, bogota, medellin, santiago, lima` | `bogota → 102361989` |
| Remote (1) | `remote → 118424786` | |

**Gap identificado**: ciudades como `antequera, fuengirola, marbella, toledo, salamanca, cadiz, granada` NO están en el mapping. El usuario confirmó que `Antequera` retorna resultados de LinkedIn con el formato `?location=Antequera,Andalucía,Spain` (URL-decoded del `location=Antequera%2CAndaluc%C3%ADa%2CSpain` que el usuario capturó). El fuzzy match de LinkedIn maneja bien ese triplet.

### 3.3 URL builder del LinkedIn scraper (verificado en `infrastructure/linkedin/scraper.py`)

- **`_build_url(keywords, location, start, geo_id=None)`** (líneas 316-356) tiene 2 paths:
  - `geo_id is not None` → `?keywords=...&geoId=<n>&start=...` (camino correcto, REQ-LOC-GEO-001).
  - `geo_id is None` → `?keywords=...&location=<str>&start=...` (camino legacy roto, "does not 500").
- **`search()`** (líneas 211-270) llama `self._settings.location_resolver.resolve(location)` cuando `geo_id is None and self._settings.location_resolver is not None` (líneas 249-250). **El resolver se llama UNA vez por `search()`**, no por page; el resultado se captura en el closure de `_make_fetch_one_page` (línea 261).
- **`_make_fetch_one_page(keywords, location, geo_id=None)`** (líneas 272-314) captura `geo_id` y lo pasa a `_build_url` en cada page. La URL se construye INSIDE el closure (línea 306).
- **Tests existentes**: `tests/unit/test_linkedin_scraper.py` tiene 6 tests que pinea la fórmula con/sin `geo_id` y con/sin paginación. Tests:
  1. `test_build_url_with_geo_id_uses_geoid_param` (geoId presente, location ausente)
  2. `test_build_url_with_geo_id_none_falls_back_to_location_param` (fallback)
  3. `test_build_url_pagination_uses_geoid_on_every_page` (start=0/25/50)
  4. `test_build_url_pagination_falls_back_to_location_on_every_page` (start=0/25/50)
  5. `test_build_url_empty_keywords_with_geo_id_still_uses_geoid` (keywords vacío)
  6. `test_build_url_special_characters_are_quoted` (URL encoding)

### 3.4 Protocol/Port (verificado en `application/ports.py:170-208`)

```python
class LocationResolverPort(Protocol):
    def resolve(self, location: str) -> int | None: ...
```

Único método. La firma retorna `int | None` (geoId LinkedIn). El docstring (líneas 181-186) menciona que el Protocol es "the seam; the future change is local to `infrastructure/location/`" — la arquitectura ya anticipa extensión.

### 3.5 Composition root (verificado en `presentation/app_factory.py`)

- Línea 185: `location_resolver = HardcodedLocationResolver()` construido una vez.
- Línea 255: wired a `LinkedInScraperSettings(location_resolver=location_resolver)`.
- Línea 522: `app.state.location_resolver = location_resolver` para que la ruta `/jobs` (`aggregator.py:169`) pueda resolver `location` sin instanciar el resolver per-request.
- Línea 607: misma instancia wired al chat filter (`FilterJobsByIntentUseCase`).
- **UNA instancia compartida** entre los 3 call sites (scraper settings + app.state + chat use case). El mismo objeto.

### 3.6 The `LinkedInParseError` semantic (context)

- LinkedIn's page-0 zero-cards semantic: **silent break** (no raise) — ver `_make_fetch_one_page` línea 285-302 + `paginated_search` helper.
- Indeed / InfoJobs raise `*ParseError` on page-0 zero-cards — comportamiento distinto, fuera de scope.

### 3.7 Engram context (resumido)

- **obs #302** (`fix-linkedin-geoid` archive): el resolver existe y está plumbed en el 2-stage chat path + el `/jobs` aggregator route. Solo NO está plumbed en el v1 single-source path (`/jobs/linkedin`); pero el `/jobs` path sí lo invoca (`aggregator.py:169`).
- **obs #322** (`backend-scraper-query-tuning` proposal §11 follow-up #2): explícitamente lista `backend-linkedin-location-fallback` como follow-up del merge #4. El naming y el alcance ya están pre-acordados.
- **obs #292** (the original gap): el gap era "LinkedIn usa `geoId=` no `location=`". Este change cierra el gap RESIDUAL para ciudades que NO están en el dict.

## 4. affected_areas

### 4.1 NEW files

- `backend/src/jobs_finder/infrastructure/location/_structured_mapping.py` (NEW) — el dict de triplets `_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]]` con entries para ciudades NO en el dict de `_mapping.py`. Formato: `key: (city, province, country)` en Title Case. Incluye al menos 8-10 ciudades (Antequera, Fuengirola, Marbella, Toledo, Salamanca, Cádiz, Granada, Gijón, León, etc.) — **el user confirma la lista exacta en proposal §3.2**. Datos de provincia/CCAA derivados de la Wikipedia / conocimiento del dominio.
- `backend/tests/unit/test_hardcoded_location_resolver.py` (EXTEND) — +12-16 scenarios cubriendo: `resolve_structured()` con cada entry del dict, alias normalization (NFC/casefold/strip/accents), alias-to-canonical recurse (e.g. `costa del sol → marbella`), `None` semantic (unknown city / empty / País Vasco / Canarias), `resolve()` y `resolve_structured()` son independientes (un city puede tener solo uno, solo el otro, o ambos).
- `backend/tests/unit/test_linkedin_scraper.py` (EXTEND) — +3-4 scenarios: `_build_url(geo_id=None, structured=("Antequera", "Andalucía", "Spain"))` → `?location=Antequera%2CAndaluc%C3%ADa%2CSpain`; con `geo_id` → prioriza `geoId=`; con `structured=None` → fallback legacy `?location=Antequera`; caracteres especiales (León, Gijón) URL-encoded correctamente.
- `backend/README.md` (MODIFY) — agregar nota en "LinkedIn manual verification" sobre el nuevo fallback estructurado + tabla de ciudades soportadas.

### 4.2 MODIFIED files

- `backend/src/jobs_finder/application/ports.py` — EXTEND `LocationResolverPort` con un segundo método `def resolve_structured(self, location: str) -> tuple[str, str, str] | None`. **Decisión arquitectónica en §5**.
- `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py` — ADD `resolve_structured(self, location: str) -> tuple[str, str, str] | None` que consulta `_STRUCTURED_MAPPING` con la MISMA normalización 4-step + alias chain (reuso de `_normalize` y `_ALIASES`). Empty string short-circuits a `None` sin warning. **El método `resolve()` no cambia** (backward-compat). El ctor agrega un kwarg `structured_mapping: Mapping[str, tuple[str, str, str]] | None = None` para tests.
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` — MODIFY `search()` (líneas 249-250) para que, después de `resolve(location)`, también llame `resolve_structured(location)`. El resultado se captura en el closure. MODIFY `_build_url` (líneas 316-356) para aceptar un nuevo kwarg `structured: tuple[str, str, str] | None = None`. La prioridad de URL building es: `geo_id` → `structured` → `location` (legacy fallback). MODIFY `_make_fetch_one_page` (líneas 272-314) para capturar `structured` y pasarlo a `_build_url` en cada page.
- `backend/src/jobs_finder/presentation/app_factory.py` — sin cambios estructurales; el `HardcodedLocationResolver` ya está wired y sus dos métodos están disponibles.

## 5. approaches

| Approach | Pros | Cons | Esfuerzo |
|---|---|---|---|
| **A. Extender `LocationResolverPort` con `resolve_structured()`** (RECOMENDADO) | Mismo Protocol = un solo test double (`FakeLocationResolver` en `tests/conftest.py`); la composición root no necesita re-wiring; type clarity per-source (cada método retorna el shape que su consumer necesita); mirrors el pattern del LLMClientPort (`complete` + `stream_complete`); la normalización es la misma, sin duplicación | El Protocol crece 1 método (cambio pequeño de spec); los test doubles existentes necesitan el segundo método (default `(None, None, None)`) | Bajo (~150-200 LOC prod + ~150-200 LOC tests) |
| B. Sibling resolver `StructuredLocationResolver` separado | Aislación total; sin tocar el Protocol existente | Dos clases, dos wirings, dos dicts; el LLMClientPort no usa este pattern; la normalización se duplica; la composición root tiene que construir y wire 2 instancias | Medio |
| C. Tagged union `def resolve(location) -> GeoId | Structured | Raw` | Un método, una firma, "shape explícito" en runtime | type abuse (el return es discriminated union; callers tienen que pattern-match); rompe el `geo_id: int | None` en `JobSearchCacheKey` 5to field; el 9-line `if isinstance(...)` se repite en cada call site (scraper, chat, route) | Alto |

## 6. recommendation

**Option A** (extender el Protocol con un segundo método). Razones:
1. **Type clarity per-source**: `resolve() -> int | None` es LinkedIn-specific (geoId); `resolve_structured() -> tuple[str, str, str] | None` es LinkedIn-specific (City, Province, Country triplet). Cada método retorna el shape exacto que su consumer necesita, sin tuple abuse ni discriminated unions.
2. **Mirrors `LLMClientPort` pattern**: ya tenemos `LLMClientPort.complete() + LLMClientPort.stream_complete()` (`application/ports.py:374-451`) con dos métodos en el mismo Protocol. El pattern está validado en el codebase.
3. **Backward compat**: `resolve()` queda intacto. Los 51+ unit tests existentes de `test_hardcoded_location_resolver.py` siguen GREEN. El `FakeLocationResolver` en `tests/conftest.py` agrega el segundo método con un default `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` (backward-compat sentinel).
4. **Composition root sin cambios**: el `HardcodedLocationResolver` ya está wired en 3 call sites (scraper settings, `app.state`, chat use case). Un solo objeto implementa ambos métodos; no hay re-wiring.
5. **Normalización reusada**: la 4-step chain (`_normalize`) se llama 2 veces (una por método), no hay duplicación.

**Sobre el dict de triplets**: la forma más limpia es un módulo separado `_structured_mapping.py` (10-20 entries) en vez de inflar `_mapping.py` con dos tipos de dict. El test file `test_hardcoded_location_resolver.py` se extiende con una nueva sección "structured lookup" que importa y testea `_STRUCTURED_MAPPING`. Mantener `_mapping.py` para `int` y `_structured_mapping.py` para `tuple[str, str, str]` separa los concerns y permite que un futuro maintainer reemplace uno sin tocar el otro.

**Sobre el formato del triplet**: `City,Province,Country` con Title Case (la URL real del usuario tiene `Antequera,Andalucía,Spain`; LinkedIn espera Title Case, no lowercase). El encoding lo hace `urllib.parse.quote` (igual que el path actual). Las tildes se mantienen (no se NFD-decomposen) — la URL del usuario tiene `%C3%ADa` (Andalucía), no `%69%CC%81` (NFD). El método `resolve_structured` retorna el Title Case y el `_build_url` lo URL-encoda con `urllib.parse.quote(..., safe=',')` o simplemente `quote` (las comas se encodean a `%2C` por defecto, que es lo que LinkedIn espera).

**Sobre la prioridad en `_build_url`**:
1. `geo_id is not None` → `?keywords=...&geoId=<n>&start=...` (highest priority — geoId es LinkedIn's preferred format, siempre exacto)
2. `geo_id is None` + `structured is not None` → `?keywords=...&location=<city>,<province>,<country>&start=...` (NEW — fuzzy match estructurado)
3. Ambos `None` → `?keywords=...&location=<raw_str>&start=...` (legacy fallback roto, no 500)

## 7. risks

1. **El formato `?location=City,Province,Country` puede NO funcionar para todas las ciudades** (M): el usuario confirmó `Antequera,Andalucía,Spain` con un example real, pero no hay garantía de que LinkedIn acepte el triplet para Toledo, Salamanca, o ciudades LATAM. **Mitigation**: el fallback legacy `?location=<raw>` sigue activo para los misses; un test LIVE gated `LLM_LIVE_TESTS=1` verifica que `Antequera,Andalucía,Spain` retorna resultados en Málaga/Andalucía; los tests unitarios solo pinnean la URL formula (no el comportamiento del SERP). Las ciudades con formato no verificado caen al legacy fallback sin degradación vs. hoy.

2. **Country en español vs. inglés** (M): la URL del usuario dice `Spain` (inglés), pero el frontend podría enviar `España` (español). **Decisión**: el dict hardcodea el country en INGLÉS (matching el example real del usuario) y se aplica un alias `españa → spain` + `espana → spain` (sin tilde) en la normalización. Si LinkedIn rechaza `Spain` en español, el usuario puede pedir cambio.

3. **Province naming con/sin tilde** (M): el example real usa `Andalucía` (con tilde). El dict hardcodea las tildes (`Andalucía`, `Cataluña`, `Comunidad Valenciana`); `_normalize` las preserva vía NFC. La URL-encoded output es `%C3%ADa` (NFC, el formato estándar web). **No risk** vs. el approach — el dict es el source of truth.

4. **El dict de triplets crece** (L): la propuesta inicial agrega 8-10 ciudades. Si el usuario quiere 30+, `_structured_mapping.py` se vuelve largo. **Mitigation**: separar en `_structured_mapping.py` mantiene el archivo enfocado; el límite práctico es ~30 entries (el dict de geoIds tiene 34, así que ya tenemos precedent para dicts grandes en hardcoded form). **No expandir** a un JSON file o DB (overkill para v1; mismo pattern que el dict de geoIds).

5. **Backward compat con ciudades NO en ningún dict** (L): ciudades como `Tokio`, `Berlin`, `Buenos Aires` (NOTA: BA ya está en `_CANONICAL_MAPPING` con geoId) NO tendrán `geoId` ni `structured` triplet. El fallback legacy `?location=Tokio` se aplica. **No regresión** vs. el comportamiento de hoy. El test `test_resolve_structured_unknown_city_returns_none` pin este caso explícitamente.

6. **`url_building priority` race condition** (L): si en el futuro el Protocol se extiende con un 3er método, la prioridad en `_build_url` tiene que revisarse. **Mitigation**: comment explícito en `_build_url` documentando la prioridad `geoId > structured > raw`; tests pinnean la prioridad con 4 scenarios.

7. **El v1 path no llama al resolver** (L): el `_execute_v1` en `FilterJobsByIntentUseCase` no invoca `location_resolver` (verificado en `filter_jobs_by_intent.py:267-277, 525-527, 660-662`). Este change NO modifica el v1 path; el chat filter 2-stage y el `/jobs` route ya invocan `resolve()`. Si el v1 path pasa `location="Antequera"`, el usuario NO recibe el beneficio. **Out of scope** (la integración del v1 con el resolver es un follow-up separado; el `backend-scraper-query-tuning` ya planeó esto como follow-up #1).

8. **Doble lookup en `search()`** (L): ahora `search()` hace 2 lookups: `resolve(location)` + `resolve_structured(location)`. Cada uno es un dict lookup O(aliases) ≈ <1µs. **No impact** en latencia.

9. **`FakeLocationResolver` en `tests/conftest.py` necesita el segundo método** (L): si el Protocol es estructural (no `@runtime_checkable`), un test double que solo implementa `resolve()` deja de satisfacer el Protocol. **Mitigation**: agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` al `FakeLocationResolver` (default `None` = no structured mapping = legacy fallback); los tests que SÍ quieren structured mapping inyectan un `HardcodedLocationResolver` real (como hace `test_chat_endpoint_2stage.py` con el resolver real).

10. **Compatibilidad con `backend-infojobs-provinces`** (paralelo) (L): ese change (obs #330) también extiende el Protocol con un segundo método `resolve_infojobs()`. Ambos cambios son ADITIVOS: agregar `resolve_structured` y `resolve_infojobs` al mismo Protocol en diferentes PRs es compatible mientras no haya colisión de nombres. **Mitigation**: el orchestrator debe mergear los cambios en orden alfabético o coordinar el merge; el conflict en `LocationResolverPort` se resuelve manualmente en el PR de merge. **No es un blocker** — es un risk operacional de PR sequencing.

## 8. open_questions for sdd-propose

1. **¿Qué ciudades entran en `_STRUCTURED_MAPPING`?** El usuario mencionó explícitamente: `Antequera, Fuengirola, Marbella, Tokío` (Tokio sin tilde es la grafía japonesa, no la española "Tokio"; pero el user escribió "Tokio" sin tilde — asumir Title Case español "Tokio"). **Recomendación**: la propuesta pregunta al user por la lista completa (propuesta: 8-10 ciudades: Antequera, Fuengirola, Marbella, Toledo, Salamanca, Cádiz, Granada, Gijón, León, Vigo). El dict es data, fácil de extender después.

2. **¿El triplet debe incluir también las ciudades YA en el dict de geoIds?** Por ejemplo, `Madrid → 103374081` ya existe en `_CANONICAL_MAPPING`. ¿Debe `resolve_structured("Madrid")` retornar `("Madrid", "Madrid", "Spain")`? **Recomendación**: NO — el `geoId` es superior (LinkIn prefiere geoId). Pero si una ciudad SÓLO tiene structured mapping (no geoId), se usa el structured. Esta es la semántica de prioridad de `_build_url`. **Confirmar con el user**.

3. **¿`resolve_structured` aplica al v1 path también?** El v1 path (`_execute_v1`) no llama al resolver. Si el user quiere que `POST /jobs/chat` con `INTENT_EXTRACTION_ENABLED=false` también use el structured fallback, hay que modificar el v1 path. **Recomendación**: NO en v1 — el v1 path es legacy; si el user quiere el beneficio, que habilite 2-stage. **Confirmar con el user**.

4. **¿`Remote` tiene structured triplet?** El `_CANONICAL_MAPPING` ya tiene `remote → 118424786`. ¿Tiene sentido un triplet `("Remote", "Remote", "Spain")`? **Recomendación**: NO — el geoId `118424786` es LinkedIn's "worldwide remote" y es superior al triplet. Si el geoId funciona, no necesitamos structured. **Confirmar con el user**.

5. **¿`Spain` (country-level) entra como fallback universal?** El `_CANONICAL_MAPPING` excluye `es → 103644278` (obs #293) por retornar resultados globalmente distribuidos. ¿Tiene sentido un triplet universal `("", "", "Spain")` como fallback? **Recomendación**: NO — sería el peor caso (filtra por country pero pierde city). El legacy `?location=<raw>` es preferible. **Confirmar con el user**.

6. **¿Cambiar el orden de prioridad en `_build_url`?** Hoy es `geoId` o `location=`. El nuevo orden es `geoId > structured > raw`. ¿El user prefiere otro orden? **Recomendación**: `geoId` siempre primero (LinkedIn's preferred). Si no hay geoId, structured. Si no hay structured, legacy raw. **Confirmar con el user**.

## 9. skill_resolution

`paths-injected` — el orchestrator pre-resolvió `sdd-explore/SKILL.md` + `_shared/SKILL.md` + `openspec-convention.md` + `persistence-contract.md` + `sdd-propose/SKILL.md` (en preflight). Cargados al inicio de este turno.

## 10. codebase_verification (real code, not guesses)

- `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py:40` — `class HardcodedLocationResolver(LocationResolverPort)`. VERIFIED.
- `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py:77` — `def resolve(self, location: str) -> int | None`. VERIFIED.
- `backend/src/jobs_finder/infrastructure/location/_mapping.py:40-79` — 34-entry `_CANONICAL_MAPPING` (módulo cuenta las categorías en el docstring). VERIFIED.
- `backend/src/jobs_finder/infrastructure/location/_mapping.py:84-90` — 5-entry `_ALIASES`. VERIFIED.
- `backend/src/jobs_finder/application/ports.py:170-208` — `LocationResolverPort(Protocol)` con un solo método `resolve()`. El docstring líneas 181-186 menciona explícitamente que el Protocol es el seam para extensiones futuras. VERIFIED.
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py:249-250` — `if geo_id is None and self._settings.location_resolver is not None: geo_id = self._settings.location_resolver.resolve(location)`. VERIFIED.
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py:316-356` — `_build_url(keywords, location, start, geo_id=None)` con la rama `if geo_id is not None: ... else: ...`. VERIFIED.
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py:272-314` — `_make_fetch_one_page(keywords, location, geo_id=None)` captura `geo_id` y lo pasa a `_build_url` en cada page. VERIFIED.
- `backend/src/jobs_finder/presentation/app_factory.py:185, 255, 522, 607` — `HardcodedLocationResolver()` instanciado una vez y wired a 3 call sites. VERIFIED.
- `backend/src/jobs_finder/presentation/routes/aggregator.py:169` — `linkedin_geo_id = request.app.state.location_resolver.resolve(query.location)`. VERIFIED.
- `backend/src/jobs_finder/application/usecases/filter_jobs_by_intent.py:267-277, 525-527, 660-662` — el resolver se invoca en el 2-stage path (líneas 525, 660) pero NO en el v1 path. VERIFIED.
- `backend/tests/unit/test_linkedin_scraper.py:67-170` — los 6 tests de URL formula existentes que pinea la prioridad `geoId` > `location=`. VERIFIED.
- `backend/tests/unit/test_hardcoded_location_resolver.py:383 LOC` — el patrón de tests (5 secciones: canonical happy-path, alias normalization, alias-to-canonical recurse, None semantic, ctor custom mapping). VERIFIED.

## 11. ready_for_proposal

**Yes.** La exploración está completa:
- El resolver actual y `_mapping.py` están verificados.
- El URL builder y la seam de `_make_fetch_one_page` están entendidos.
- El Protocol `LocationResolverPort` es el seam limpio para extender (1 método nuevo, no break).
- Las 3 options arquitectónicas están comparadas (Option A recomendada).
- Las 6 open questions están flagged para que el orchestrator confirme con el user antes de `sdd-propose`.
- Los 10 riesgos están documentados con mitigations.
- El dict de triplets es data — fácil de extender en una iteración futura.

**Workload forecast**: ~200-400 LOC (~150-200 prod + ~150-200 tests + ~50 docs). Por debajo del budget de 5000 líneas del orchestrator. **Single PR es suficiente** (no chained PR needed; el cambio es pequeño y aditivo).

**Next step**: el orchestrator puede lanzar `sdd-propose` para lock las 6 open questions, el file set final, y la capability taxonomy (`linkedin-structured-location-fallback`).
