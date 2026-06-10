# Spec: `backend-linkedin-location-fallback`

> **Change**: `backend-linkedin-location-fallback` • **Base**: `f41aa90` (post `backend-scraper-query-tuning`) • **Strict TDD**: ACTIVE
> **Modo artifact**: `both` (OpenSpec filesystem + Engram) • **Resolutor**: extender `LocationResolverPort` con un segundo método `resolve_structured`.

## Purpose

El `HardcodedLocationResolver` (obs #302) traduce 34 strings canónicos a un `geoId` numérico de LinkedIn (vía `?geoId=<int>`). Para ciudades NO presentes en ese dict — `Antequera`, `Fuengirola`, `Marbella`, `Toledo`, etc. — el LinkedIn scraper cae al fallback legacy `?location=<raw_str>`, que LinkedIn silently ignora y retorna resultados sin filtro de ubicación (el gap residual del `backend-scraper-query-tuning`).

El usuario encontró una URL real de LinkedIn que muestra un tercer formato soportado: `?location=<city>,<province>,<country>` (ej. `location=Antequera%2CAndaluc%C3%ADa%2CSpain`). LinkedIn's fuzzy match funciona mejor con el triplet estructurado. Este cambio agrega un fallback intermedio `?location=City,Province,Country` para ciudades con triplet conocido pero sin geoId. El fallback legacy se preserva para ciudades sin NINGÚN mapping (no regresión). No hay cambio en el HTTP contract — el frontend sigue enviando `location=<raw>`; el resolver convierte internamente.

---

## Domain 1 — `location-resolver` (NEW main spec + delta)

> **Nota**: El spec principal `openspec/specs/location-resolver/spec.md` NO existe aún. Este cambio lo CREA. El bloque `## MODIFIED Requirements` que sigue se sincronizará al archivo principal en `sdd-archive` (la spec principal empieza con sólo lo que está en este delta; al archivar, este bloque se convierte en el spec principal completo).

### Purpose

Puerto `LocationResolverPort` que el composition root inyecta en el LinkedIn scraper, en el chat use case, y en `app.state`. En v1 expone un solo método `resolve(location) -> int | None` que retorna el `geoId` numérico de LinkedIn. Este delta agrega un segundo método `resolve_structured(location) -> tuple[str, str, str] | None` que retorna un triplet `(city, province, country)` en Title Case con tildes (NFC) para ciudades con mapping estructurado pero sin geoId.

### ADDED Requirements

### Requirement: `LocationResolverPort.resolve_structured`

El Protocol `LocationResolverPort` MUST declarar un segundo método:

```python
def resolve_structured(self, location: str) -> tuple[str, str, str] | None: ...
```

El método MUST retornar `tuple[str, str, str]` (3 strings: city, province, country en Title Case con tildes NFC) cuando el input normaliza a una ciudad con entry en `_STRUCTURED_MAPPING`. MUST retornar `None` en cualquier otro caso (ciudad desconocida, string vacío, input country-level tipo `"España"`, input CCAA-level tipo `"Andalucía"`). Los dos métodos son independientes: una ciudad puede tener solo `geoId` (ej. `Madrid`), solo `structured` (ej. `Antequera`), ambos, o ninguno (ej. `Tokio`).

#### Scenario: Protocol tiene AMBOS métodos declarados

- **GIVEN** el módulo `application/ports.py` se carga
- **WHEN** `inspect.getmembers(LocationResolverPort)` lista los métodos
- **THEN** la lista contiene `resolve` Y `resolve_structured` (ambos declarados explícitamente)
- **AND** `mypy --strict` no reporta `Definition of "__call__" in protocol "LocationResolverPort" is missing in some class` para `HardcodedLocationResolver` ni para `FakeLocationResolver`

#### Scenario: `HardcodedLocationResolver` implementa `resolve_structured`

- **GIVEN** `HardcodedLocationResolver()` se instancia sin args (usa el `_STRUCTURED_MAPPING` por defecto)
- **WHEN** se llama `resolver.resolve_structured("Antequera")`
- **THEN** retorna `("Antequera", "Andalucía", "Spain")` (Title Case con tildes NFC)
- **AND** el test `test_hardcoded_location_resolver.py::test_protocol_satisfied_by_hardcoded_resolver` pasa

#### Scenario: `FakeLocationResolver` (test double) implementa el segundo método con default `None`

- **GIVEN** `FakeLocationResolver()` se instancia en `tests/conftest.py`
- **WHEN** se llama `fake.resolve_structured("anything")`
- **THEN** retorna `None` (default)
- **AND** `mypy --strict` valida que `FakeLocationResolver` satisface el Protocol extendido
- **AND** los ~51 tests existentes que usan `FakeLocationResolver` siguen GREEN sin modificación

### Requirement: Normalización 4-step del input

`resolve_structured` MUST reusar la misma cadena de normalización 4-step que `resolve`: (1) NFC compose vía `unicodedata.normalize("NFC", ...)`, (2) `casefold()`, (3) `strip()`, (4) remove accents vía `unicodedata.normalize("NFD", x).encode("ascii", "ignore").decode("ascii")`. El lookup key es `normalized` (lowercase + sin tildes + sin espacios extra); el value retornado preserva Title Case + tildes NFC.

#### Scenario: input con tildes (NFD decompuesto) normaliza a NFC

- **GIVEN** el resolver aplica `unicodedata.normalize("NFC", ...)` como step 1
- **WHEN** se llama `resolve_structured("Ante\u0301ra")` (NFD: `Ante` + combining acute) — input poco probable pero posible
- **THEN** el lookup normaliza a `"antequera"` (lowercase + sin tildes) y retorna `("Antequera", "Andalucía", "Spain")`
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_nfd_normalized` pasa

#### Scenario: input en mayúsculas matchea el dict lowercase

- **GIVEN** el lookup key es `casefold()` del input normalizado
- **WHEN** se llama `resolve_structured("ANTEQUERA")`
- **THEN** el lookup key es `"antequera"`, matchea el dict, retorna `("Antequera", "Andalucía", "Spain")`
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_uppercase` pasa

#### Scenario: input con whitespace extra se trimea

- **GIVEN** el lookup key se trimea con `strip()`
- **WHEN** se llama `resolve_structured("  Antequera  ")`
- **THEN** el lookup key es `"antequera"`, retorna el triplet esperado
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_strip` pasa

#### Scenario: input sin tildes matchea el value con tildes

- **GIVEN** el step 4 remueve accents del lookup key pero el value del dict preserva tildes
- **WHEN** se llama `resolve_structured("Cadiz")` (input ASCII)
- **THEN** el lookup key es `"cadiz"`, matchea, retorna `("Cádiz", "Andalucía", "Spain")` (value con tilde)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_no_accent_input` pasa

### Requirement: Alias-to-canonical recurse

`resolve_structured` MUST respetar la misma lógica de `_ALIASES` que `resolve`: si el normalized input no está en el dict directo, intenta `canonical_key = self._aliases.get(normalized, normalized)` y busca el `canonical_key` en `_STRUCTURED_MAPPING`. Esto permite que un alias en español (ej. `"ante" → "antequera"`) resuelva al triplet completo.

#### Scenario: alias en `_ALIASES` se expande al canonical

- **GIVEN** `_ALIASES = {"ante": "antequera"}` (alias agregado en este change; debe existir)
- **WHEN** se llama `resolve_structured("ante")`
- **THEN** `canonical_key = "antequera"`, retorna `("Antequera", "Andalucía", "Spain")`
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_alias_recurse` pasa

#### Scenario: alias encadenado (alias → alias → canonical)

- **GIVEN** `_ALIASES = {"ante": "ante", "antequera_canonical": "antequera"}` (chain de 2 hops; hypothetical)
- **WHEN** se llama `resolve_structured("ante")` con un chain
- **THEN** el recurse itera hasta encontrar `"antequera"` en el dict, retorna el triplet
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_alias_chain` pasa (parametrized: chain 1-hop y 2-hop)

### Requirement: `None` semantic para inputs sin mapping

`resolve_structured` MUST retornar `None` (NO raise) en estos casos:
1. Input vacío (`""`).
2. Ciudad no presente en `_STRUCTURED_MAPPING` ni en `_ALIASES` (ej. `"Berlin"`, `"Tokio"`, `"Atlantis"`).
3. Input country-level (ej. `"España"`, `"Spain"`, `"Espana"`) — el dict es city-level.
4. Input CCAA-level (ej. `"Andalucía"`) — el dict es city-level, no region-level.
5. Input whitespace-only (ej. `"   "`).

#### Scenario: ciudad desconocida retorna `None`

- **GIVEN** `_STRUCTURED_MAPPING` no contiene `"berlin"`
- **WHEN** se llama `resolve_structured("Berlin")`
- **THEN** retorna `None` (sin warning — el log de warning aplica a scraper, no al resolver)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_unknown_city` pasa

#### Scenario: string vacío retorna `None` (defensivo)

- **GIVEN** el input es `""`
- **WHEN** se llama `resolve_structured("")`
- **THEN** retorna `None` (defensivo, antes de normalizar)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_empty` pasa

#### Scenario: input country-level retorna `None` (NO es city-level)

- **GIVEN** el input es `"España"`, `"Spain"`, o `"Espana"`
- **WHEN** se llama `resolve_structured` con cualquiera de los 3
- **THEN** retorna `None` (no es una ciudad, es un país; el dict es city-level)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_country_input` pasa (parametrized: 3 cases)

> **Decisión del spec author (resuelve nota del orchestrator)**: Para inputs country-level ("España", "Spain"), el resolver retorna `None`. NO retornamos `("Madrid", "Madrid", "Spain")` ni `("", "", "Spain")`. Razones: (a) el dict es city-level, un país es otra categoría; (b) retornar la capital sería heurística no documentada; (c) retornar `("", "", "Spain")` rompería el `quote()` downstream que requiere city no vacía. El fallback legacy `?location=España` (raw) es responsabilidad de LinkedIn, no del resolver.

#### Scenario: input CCAA-level retorna `None`

- **GIVEN** el input es `"Andalucía"` o `"Cataluña"`
- **WHEN** se llama `resolve_structured("Andalucía")`
- **THEN** retorna `None` (no es city-level, es CCAA)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_region_input` pasa

### Requirement: `HardcodedLocationResolver.__init__` acepta `structured_mapping`

El ctor MUST aceptar un nuevo kwarg `structured_mapping: Mapping[str, tuple[str, str, str]] | None = None`. Si se omite, usa el dict default importado de `_structured_mapping._STRUCTURED_MAPPING`. Esto MUST matchear el patrón del kwarg `mapping` existente.

#### Scenario: ctor sin args usa el dict default

- **GIVEN** `HardcodedLocationResolver()` se instancia
- **WHEN** se inspecciona `resolver._structured_mapping`
- **THEN** es el dict default importado de `_structured_mapping._STRUCTURED_MAPPING`
- **AND** contiene al menos 10 entries (las confirmadas en REQ-FB-003)

#### Scenario: ctor con `structured_mapping` custom lo usa

- **GIVEN** un dict custom `{"foo": ("Foo", "Bar", "Spain")}`
- **WHEN** se instancia `HardcodedLocationResolver(structured_mapping=custom_dict)`
- **THEN** `resolver._structured_mapping is custom_dict`
- **AND** `resolve_structured("foo")` retorna `("Foo", "Bar", "Spain")` (NO `"antequera"`)
- **AND** el test `test_hardcoded_location_resolver.py::test_ctor_custom_structured_mapping` pasa

#### Scenario: `mapping` y `structured_mapping` son independientes

- **GIVEN** dos dicts `m1` (geoIds) y `s1` (structured) separados
- **WHEN** se instancia `HardcodedLocationResolver(mapping=m1, structured_mapping=s1)`
- **THEN** cambiar `m1` post-construcción NO afecta `s1` (y viceversa) — cada uno es una referencia separada en `self`
- **AND** el test `test_hardcoded_location_resolver.py::test_mappings_independent` pasa

### Requirement: Indepencia entre `resolve()` y `resolve_structured()`

Los dos métodos MUST ser completamente independientes: una ciudad puede tener uno, otro, ambos, o ninguno. El `_CANONICAL_MAPPING` y `_STRUCTURED_MAPPING` son dicts separados.

#### Scenario: ciudad con AMBOS mappings usa `geoId` (priority upstream)

- **GIVEN** una ciudad está en `_CANONICAL_MAPPING` Y en `_STRUCTURED_MAPPING` (hipotético en v1 — no aplica, pero el contrato lo permite)
- **WHEN** se llama `resolve(city)` y `resolve_structured(city)` por separado
- **THEN** `resolve` retorna el `geoId` (int), `resolve_structured` retorna el triplet (tuple)
- **AND** la decisión de cuál usar la toma el CONSUMER (LinkedIn scraper), no el resolver
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_and_resolve_structured_independent` pasa (parametrized: 4 combinaciones — only-geoId, only-structured, both, none)

#### Scenario: ciudad con `geoId` NO duplica en structured

- **GIVEN** v1 tiene `Madrid` en `_CANONICAL_MAPPING` (geoId) pero NO en `_STRUCTURED_MAPPING`
- **WHEN** se inspecciona `_STRUCTURED_MAPPING`
- **THEN** `"madrid"` NO está presente (per Q2 del proposal: "NO. El geoId es LinkedIn's preferred format y siempre gana")
- **AND** el test `test_hardcoded_location_resolver.py::test_madrid_not_in_structured_mapping` pasa (lock-in de la decisión)

---

## Domain 2 — `linkedin-scraper` (NEW main spec + delta)

> **Nota**: El spec principal `openspec/specs/linkedin-scraper/spec.md` NO existe aún. Este cambio lo CREA. Al archivar, este bloque se convierte en el spec principal completo. (La numeración REQ-L-* vivirá en el archivo principal post-archive.)

### Purpose

El `LinkedInPlaywrightScraper` es el adapter de Playwright para el portal LinkedIn. Su responsabilidad es construir la URL de búsqueda, abrir un browser context, ejecutar el loop de paginación vía `paginated_search`, y parsear cada página a `list[Job]`. Este delta agrega una rama intermedia al URL builder: además de `geoId` (priority alta) y `location=<raw>` (priority baja), se agrega `location=<city>,<province>,<country>` (priority media) usando el nuevo `resolve_structured`.

### MODIFIED Requirements

> Workflow `MODIFIED`: copy-paste del full block desde la spec original y edit. Como NO existe spec original, el bloque `MODIFIED` contiene los REQ-L-* que aplican al URL building actual + las modificaciones. Al archivar, este bloque se materializa en el spec principal.

### Requirement: `_build_url` prioridad `geoId > structured > raw`

El método `_build_url` (privado) MUST aceptar dos kwargs nuevos: `geo_id: int | None = None` (existente) y `structured: tuple[str, str, str] | None = None` (NUEVO). La prioridad MUST ser:
1. **Si `geo_id is not None`**: `?keywords={k}&geoId={int}&start={s}` (existing — el más preciso).
2. **Si `structured is not None`**: `?keywords={k}&location={quote(city,province,country)}&start={s}` (NUEVO — triplet estructurado).
3. **Si ninguno**: `?keywords={k}&location={quote(raw)}&start={s}` (existing — legacy fallback).

El formato del structured location MUST ser `f"{city},{province},{country}"` (3 partes, comma-separated, Title Case con tildes NFC) y se URL-encodea con `urllib.parse.quote` (preserva la coma y la `í` como `%2C` y `%C3%AD`).

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

### Requirement: URL encoding con tildes (NFC)

El formato `?location=City,Province,Country` MUST URL-encodear las tildes como `%C3%AD` (NFC composed) y las comas como `%2C`. `urllib.parse.quote` por defecto encodea solo los chars no-`Luffy` (`/`, `,`, etc.), preservando caracteres Unicode como `í` que se codifican como UTF-8 multibyte.

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

### Requirement: `search()` consulta `resolve_structured` una vez

`search()` MUST llamar `resolver.resolve_structured(location)` exactamente UNA vez (no por página), y capturar el resultado en el closure de `_make_fetch_one_page`. Idem para `resolver.resolve(location)`. La URL se construye una vez y se reusa con `start` cambiando por página.

#### Scenario: ambos resolvers se llaman exactamente 1 vez

- **GIVEN** un `FakeLocationResolver` que cuenta llamadas
- **WHEN** `LinkedInPlaywrightScraper.search("react", "Antequera", 20)` ejecuta 3 páginas vía `paginated_search`
- **THEN** `fake.resolve.call_count == 1` Y `fake.resolve_structured.call_count == 1` (no 3)
- **AND** el test `test_linkedin_scraper.py::test_resolver_called_once_per_search` pasa

#### Scenario: `structured` se captura en el closure y se reusa

- **GIVEN** `structured=("Antequera", "Andalucía", "Spain")` se resuelve en `search()`
- **WHEN** el closure `_make_fetch_one_page` construye URLs para 3 páginas
- **THEN** las 3 URLs tienen la misma `location=...` y solo cambia `start=0/25/50`
- **AND** el test `test_linkedin_scraper.py::test_structured_closure_reused_across_pages` pasa

### Requirement: Backward compat con wiring sin resolver

Si el `LinkedInScraperSettings.location_resolver` es `None` (legacy wiring pre-`backend-scraper-query-tuning`), el scraper MUST seguir funcionando con el fallback legacy `?location=<raw>`. La rama `structured` se omite silenciosamente (NO raise, NO log spam).

#### Scenario: scraper sin resolver cae al legacy

- **GIVEN** `LinkedInScraperSettings(location_resolver=None)` (legacy)
- **WHEN** se llama `LinkedInPlaywrightScraper.search("react", "Antequera", 20)` (sin resolver en absoluto)
- **THEN** la URL usa `?location=Antequera` (legacy fallback intacto, no `?location=Antequera,...`)
- **AND** el test `test_linkedin_scraper.py::test_legacy_wiring_without_resolver` (existente, de `backend-scraper-query-tuning`) sigue GREEN
- **AND** el test `test_linkedin_scraper.py::test_no_resolver_skips_structured_silently` pasa (NUEVO, específico para este change)

#### Scenario: `resolve_structured` retorna `None` cae al legacy (resolver existe pero ciudad sin mapping)

- **GIVEN** `FakeLocationResolver` configurado con `resolve_structured.return_value = None` para `"Berlin"`
- **WHEN** se llama `search("react", "Berlin", 20)`
- **THEN** la URL usa `?location=Berlin` (legacy, no 500, no raise)
- **AND** el test `test_linkedin_scraper.py::test_resolve_structured_none_falls_to_legacy` pasa

---

## Domain 3 — `linkedin-structured-location-fallback` (NEW capability)

> **Nota**: Este es un spec de capability nueva (per proposal §3.1). Cubre los mappings concretos y el comportamiento observable desde la perspectiva del sistema, no del puerto.

### Purpose

El `_STRUCTURED_MAPPING` es el dict complementario al `_CANONICAL_MAPPING`: donde el primero retorna `int` (geoId), el segundo retorna `tuple[str, str, str]` (triplet). Ambos viven en `infrastructure/location/`. Esta capability define el contenido v1 del structured mapping y el contrato de mantenimiento.

### ADDED Requirements

### Requirement: `_STRUCTURED_MAPPING` v1 contiene 10 ciudades españolas

El dict `_STRUCTURED_MAPPING` (en `infrastructure/location/_structured_mapping.py`) MUST contener al menos las 10 ciudades confirmadas en la propuesta. Cada entry es `dict[normalized_key, tuple[city, province, country]]` donde las keys son lowercase + sin tildes (lookup) y los values son Title Case con tildes (output).

| Key (lookup) | Value `city` | Value `province` | Value `country` |
|---|---|---|---|
| `antequera` | `"Antequera"` | `"Andalucía"` | `"Spain"` |
| `fuengirola` | `"Fuengirola"` | `"Málaga"` | `"Spain"` |
| `marbella` | `"Marbella"` | `"Málaga"` | `"Spain"` |
| `toledo` | `"Toledo"` | `"Castilla-La Mancha"` | `"Spain"` |
| `salamanca` | `"Salamanca"` | `"Castilla y León"` | `"Spain"` |
| `cadiz` | `"Cádiz"` | `"Andalucía"` | `"Spain"` |
| `granada` | `"Granada"` | `"Andalucía"` | `"Spain"` |
| `gijon` | `"Gijón"` | `"Asturias"` | `"Spain"` |
| `leon` | `"León"` | `"Castilla y León"` | `"Spain"` |
| `vigo` | `"Vigo"` | `"Galicia"` | `"Spain"` |

#### Scenario: las 10 ciudades retornan triplet

- **GIVEN** el mapping default está cargado
- **WHEN** se itera `for key, expected in 10_test_cases:` y se llama `resolve_structured(key)`
- **THEN** cada uno retorna el triplet esperado (parametrized test, 10 cases)
- **AND** el test `test_hardcoded_location_resolver.py::test_all_10_cities_in_mapping` pasa (parametrized)

#### Scenario: `Madrid` NO está en el structured mapping (decision de la propuesta)

- **GIVEN** `Madrid` está en `_CANONICAL_MAPPING` (geoId) pero NO en `_STRUCTURED_MAPPING` (per Q2 de la propuesta: NO duplicar)
- **WHEN** se llama `resolve_structured("Madrid")`
- **THEN** retorna `None` (no es un fallo — `Madrid` usa el camino `geoId`)
- **AND** el test `test_hardcoded_location_resolver.py::test_madrid_not_in_structured_mapping` pasa

### Requirement: Solo `Antequera` es user-verified; los otros 9 son speculative

El módulo `_structured_mapping.py` MUST contener un comment inline distinguiendo las 10 entries:
- `"antequera"`: **VERIFIED** (LIVE test gated `LLM_LIVE_TESTS=1` lo confirma contra LinkedIn real — ver REQ-FB-007).
- Los 9 restantes (`fuengirola`, `marbella`, `toledo`, `salamanca`, `cadiz`, `granada`, `gijon`, `leon`, `vigo`): **SPECULATIVE** (province/country fueron inferidos de la división administrativa de España; la URL format `?location=City,Province,Country` puede NO funcionar para todas — el LIVE test las validará en una iteración posterior).

#### Scenario: comment inline marca VERIFIED vs SPECULATIVE

- **GIVEN** el archivo `_structured_mapping.py` se carga
- **WHEN** se lee el módulo
- **THEN** cada entry tiene un comment `# VERIFIED` o `# SPECULATIVE` inline
- **AND** el test `test_hardcoded_location_resolver.py::test_mapping_has_verified_comments` pasa (asserts via `ast` parse o `inspect.getsource`)

### Requirement: Country en inglés (`"Spain"`) + alias español

El `country` en todos los triplets MUST ser `"Spain"` (inglés, matching la URL real capturada por el usuario). Si el frontend o el chat use case envía `"España"` o `"Espana"`, el resolver (vía `_ALIASES`) MUST normalizarlo a `"spain"` antes del lookup en `_STRUCTURED_MAPPING`. PERO: como el dict es city-level, un input country-level retorna `None` (ver scenario anterior); el alias aplica para el input que combina city + country, no para input country-only.

#### Scenario: alias `españa` mapea a `spain` en `_ALIASES`

- **GIVEN** `_ALIASES = {"españa": "spain", "espana": "spain"}` (alias chain)
- **WHEN** se llama `resolve_structured("España")` (country-only input)
- **THEN** retorna `None` (no es city-level)
- **AND** el test `test_hardcoded_location_resolver.py::test_country_alias_returns_none_for_country_input` pasa

#### Scenario: triplet value es siempre `"Spain"` (inglés)

- **GIVEN** los 10 triplets del mapping
- **WHEN** se inspecciona `triplet[2]` (el country)
- **THEN** es exactamente `"Spain"` (Title Case, inglés, sin tilde) en los 10
- **AND** el test `test_hardcoded_location_resolver.py::test_country_value_is_english_spain` pasa (parametrized: 10 cases)

### Requirement: Province accent preservation (canonical Title Case con tildes)

Las provinces en el value MUST preservar tildes: `"Andalucía"` (con `í`), `"Castilla y León"` (con `ó`), `"Castilla-La Mancha"` (con `-` entre palabras), `"Galicia"` (sin tildes), etc. El `_normalize` las remueve del lookup key pero el value las preserva.

#### Scenario: `Andalucía` se preserva en el output

- **GIVEN** el input `"andalucia"` (sin tilde)
- **WHEN** se llama `resolve_structured("andalucia")`
- **THEN** retorna `("Antequera", "Andalucía", "Spain")` (value con tilde, no `Andalucia` sin tilde)
- **AND** el test `test_hardcoded_location_resolver.py::test_province_accent_preserved_andalucia` pasa

#### Scenario: `Castilla y León` con espacio y tilde se preserva

- **GIVEN** el input `"castilla y leon"` (sin tildes)
- **WHEN** se llama `resolve_structured("castilla y leon")`
- **THEN** retorna `("Salamanca", "Castilla y León", "Spain")` (value con espacio y `ó`)
- **AND** el test `test_hardcoded_location_resolver.py::test_province_multiword_preserved` pasa

#### Scenario: `Castilla-La Mancha` con guion se preserva

- **GIVEN** el input `"toledo"`
- **WHEN** se llama `resolve_structured("toledo")`
- **THEN** retorna `("Toledo", "Castilla-La Mancha", "Spain")` (province con guion)
- **AND** el test `test_hardcoded_location_resolver.py::test_province_hyphen_preserved` pasa

### Requirement: LIVE test gated `LLM_LIVE_TESTS=1` (no CI)

Un test de integración LIVE en `tests/integration/test_linkedin_live.py` MUST validar que la URL `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain` retorna ofertas en Antequera/Málaga/Andalucía contra LinkedIn real. MUST estar gated por env var `LLM_LIVE_TESTS=1` (no en CI per AGENTS.md rule #1).

#### Scenario: LIVE test gated skipped en CI

- **GIVEN** `LLM_LIVE_TESTS` no está seteado (default CI)
- **WHEN** `pytest` corre sin env var
- **THEN** el LIVE test se SKIP (no se ejecuta contra LinkedIn)
- **AND** el test `test_linkedin_live.py::test_live_antequera_structured_url_returns_andalucia_jobs` reporta `SKIPPED`

#### Scenario: LIVE test gated runs cuando se habilita

- **GIVEN** `LLM_LIVE_TESTS=1` y network disponible
- **WHEN** `pytest tests/integration/test_linkedin_live.py` corre
- **THEN** el test hace una request real a LinkedIn con la URL estructurada
- **AND** verifica que ≥1 de los primeros 5 resultados contiene `"Antequera"`, `"Málaga"`, o `"Andalucía"` en el location (assertion flexible — LinkedIn puede devolver la city exacta o la province o el country)

### Requirement: Full test coverage (Strict TDD, ~20+ nuevos tests)

Todos los nuevos tests MUST ser test-first (RED → GREEN → REFACTOR). Distribución estimada:

| Archivo | Tests nuevos | Cobertura |
|---|---|---|
| `tests/unit/test_hardcoded_location_resolver.py` | ~15 | 10 ciudades (parametrized), alias normalization (4 invariants), alias recurse (2), `None` semantic (5), ctor override (3), independence (2) |
| `tests/unit/test_linkedin_scraper.py` | ~7 | URL priority (3 branches × 2 = 6 con parametrized), URL encoding con tildes (3 cities: Cádiz, León, Antequera), resolver called once (1), no-op compat (2) |
| `tests/integration/test_chat_endpoint_2stage.py` | ~1 | End-to-end `intent.location="Antequera"` → URL contains `location=Antequera%2CAndaluc%C3%ADa%2CSpain` |
| `tests/integration/test_linkedin_live.py` | ~1 | LIVE test gated `LLM_LIVE_TESTS=1` (opcional) |
| **Total** | **~24** | |

#### Scenario: full test suite pasa

- **GIVEN** el change está implementado
- **WHEN** `cd backend && uv run pytest` corre
- **THEN** los 1,142 baseline tests siguen GREEN + ~24 nuevos tests pasan = **~1,166 passed / 13 skipped**
- **AND** `cd backend && uv run mypy --strict` está clean (Protocol extendido satisfecho por todas las impls)
- **AND** `cd backend && uv run ruff check` está clean
- **AND** `cd backend && uv run ruff format --check` está clean
- **AND** el comando consolidado `cd backend && bash scripts/check.sh` pasa los 4 gates

---

## Out of scope

- Agregar más ciudades al `_STRUCTURED_MAPPING` (user puede extender en un PR follow-up; mismo pattern que `_CANONICAL_MAPPING`).
- Ciudades no españolas (`Tokio`, `Berlin`, etc.) — el fallback legacy `?location=<raw>` las cubre; agregar triplets es trivial en un follow-up.
- Cambiar la firma o comportamiento de `resolve(location) -> int | None` — se mantiene intacta.
- Modificar el v1 chat-filter path (`_execute_v1`) — el v1 path no llama al resolver; modificarlo es un follow-up separado.
- Modificar el `filter_infojobs_results` o agregar `sinceDate=ANY` / `sortBy=RELEVANCE` al URL de InfoJobs — esos son el cambio paralelo `backend-infojobs-provinces` (obs #330).
- Mover el dict a JSON file o DB — mismo pattern hardcoded que `_CANONICAL_MAPPING`.
- Auto-detectar country desde el input — siempre hardcoded en el dict.

## Open questions

**None — todas las decisiones se resolvieron en la fase `sdd-propose` + las 3 confirmaciones del user (Q5/Q6/Q7)**.

## Acceptance criteria

- [ ] Todos los REQ-* (este spec) están cubiertos por tests passing.
- [ ] ~24 nuevos tests pasan; los 1,142 baseline tests siguen GREEN.
- [ ] `mypy --strict` clean; `ruff check` clean; `ruff format --check` clean.
- [ ] `cd backend && bash scripts/check.sh` pasa los 4 gates.
- [ ] **Manual smoke test**: `curl "http://localhost:8000/jobs?q=react&location=Antequera&limit=20"` retorna MÁS ofertas de Antequera/Málaga/Andalucía y MENOS noise de otras ciudades (vs. el behavior actual pre-change).
- [ ] **v1 backwards-compat**: `curl "...&location=Berlin"` sigue retornando resultados (legacy `?location=Berlin`); `curl "...&location=Tokio"` idem. NO regresión.
- [ ] **LIVE test gated `LLM_LIVE_TESTS=1`** valida el structured format end-to-end contra LinkedIn real (skipped en CI).
- [ ] La 8 ciudades del `_CANONICAL_MAPPING` (Madrid, Barcelona, Valencia, Sevilla, Zaragoza, Málaga, Murcia, Bilbao) SIGUEN usando `?geoId=<int>` (priority `geoId > structured`).
- [ ] 3 quality gates verdes en el PR (pytest + mypy + ruff) y `bash scripts/check.sh` local.
- [ ] `sdd-verify` PASS con 0 critical findings.

## Next step

Listo para `sdd-design` (orquestador). El `sdd-design` phase va a:
1. Decidir la estructura interna del módulo `_structured_mapping.py` (data + tests paramétricos).
2. Decidir el shape exacto del ctor de `HardcodedLocationResolver` (compat con kwargs `mapping` y `structured_mapping`).
3. Decidir cómo `paginated_search` recibe `structured` (kwarg explícito vs. dict de params).
4. Producir el `design.md` con diagramas de secuencia para el flow `search()` → `resolver.resolve()` + `resolver.resolve_structured()` → `_build_url` con la prioridad `geoId > structured > raw`.
