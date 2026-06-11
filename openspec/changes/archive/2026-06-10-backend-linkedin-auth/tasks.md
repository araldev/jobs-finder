# Tasks: `backend-linkedin-auth`

> **Status**: `tasks` (ready for `sdd-apply` after orchestrator review of §13 Review Workload Forecast)
> **Base**: `017d6fa` (post `backend-infojobs-provinces` + `backend-scraper-query-tuning` merge, main; working tree clean per `git status -s`)
> **Mode**: `both` (OpenSpec filesystem + Engram)
> **Strict TDD**: ACTIVE — every scenario in the spec is a real test, written RED first
> **Spec**: Engram obs #355 (19 REQs: REQ-LA-COOKIE-001..004, REQ-LA-SCR-001..006, REQ-LA-CFG-001..004, REQ-LA-AWALL-001..006)
> **Design**: Engram obs #356
> **Proposal**: Engram obs #354
> **Exploration**: Engram obs #353

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~540 (range 500–600, per design §3 + §4 tax) |
| 400-line budget risk | Low (~108 LOC/commit avg, 5 commits) |
| Chained PRs recommended | No |
| Suggested split | single PR (5 conventional commits) |
| Delivery strategy | ask-on-risk |
| Chain strategy | size:exception (single PR) |
| Decision needed before apply | No (single PR approved at design; budget risk Low) |
| Chained PRs recommended | No |
| Chain strategy | size:exception |
| 400-line budget risk | Low |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| T-001 | Port Protocol + env adapter + test double in conftest | PR 1 commit 1 | Foundation: T-004 reads the Protocol; nothing else can be wired before this. |
| T-002 | `Settings.linkedin_li_at` field + 2 validators | PR 1 commit 2 | Independently testable; the field default is `None` so T-001/T-003 keep working. |
| T-003 | `is_auth_wall(soup)` pure function | PR 1 commit 3 | Pure parser, no scraper coupling; independent. |
| T-004 | `LinkedInScraperSettings.auth_cookie` kwarg + `search()` injection + closure `is_auth_wall` integration | PR 1 commit 4 | Depends on T-001 (Port) + T-003 (detector). Default `auth_cookie=None` preserves v1 behavior. |
| T-005 | Composition root wire + integration test + `README.md` + `.env.example` | PR 1 commit 5 | Final wiring + operator-facing docs. Closes the PR. |

## Resumen ejecutivo (work unit slicing)

El trabajo se parte en 5 work units secuenciales que respeta la disciplina **strict TDD** (RED → GREEN → refactor → full suite → mypy/ruff). Cada unit termina con un commit convencional. El forecast total es **~540 LOC** distribuidos en 5 commits (~108 LOC/commit promedio), bien dentro del budget de 400 líneas y del budget de review de 5000 líneas. La cadena de dependencias es estricta: T-001 (Protocol + adapter + test double, foundation) → T-002 (Settings field, parallel-friendly) → T-003 (pure parser, parallel-friendly) → T-004 (scraper uses Port + detector) → T-005 (composition root wire + integration + docs). El adapter `EnvLinkedInAuthCookieAdapter` se construye con `SecretStr | None` (no I/O) y es trivialmente fakeable con el `FakeLinkedInAuthCookiePort` companion que se introduce en T-001 (no espera a T-005). El "boot works at every step" rule se mantiene: T-001 deja el `auth_cookie` kwarg en el Protocol + adapter + test double pero NO toca el scraper; T-002 introduce el field con `default=None` (sin regresión); T-003 introduce la función pura `is_auth_wall` (sin caller aún); T-004 introduce el kwarg `auth_cookie=None` con default y el `add_cookies` solo cuando el port retorna valor (sin regresión v1); T-005 wire + docs (sin cambio de comportamiento). El presupuesto de 5000 líneas es generoso para este cambio; **single PR es suficiente — no chained PR needed**.

## Work units

### T-001: `LinkedInAuthCookiePort` Protocol + `EnvLinkedInAuthCookieAdapter` + `FakeLinkedInAuthCookiePort` test double

**Type**: feature + test-first
**Scope**:
- **RED tests first** en `backend/tests/unit/test_linkedin_auth_cookie.py` (NEW, ~120 LOC):
  - `test_port_protocol_structural_conformance`: `EnvLinkedInAuthCookieAdapter` y `FakeLinkedInAuthCookiePort` ambos satisfacen `LinkedInAuthCookiePort` typed (REQ-LA-COOKIE-001)
  - `test_adapter_returns_none_when_unset`: `EnvLinkedInAuthCookieAdapter(None).cookie() is None` (REQ-LA-COOKIE-002)
  - `test_adapter_returns_none_when_empty_secret`: `EnvLinkedInAuthCookieAdapter(SecretStr("")).cookie() is None` (REQ-LA-COOKIE-002)
  - `test_adapter_returns_secretstr_with_masked_repr`: `repr(adapter.cookie()) == "SecretStr('**********')"` (REQ-LA-COOKIE-003)
  - `test_adapter_returns_secretstr_at_minimum_length_8`: `SecretStr("12345678")` se retorna intacto (REQ-LA-COOKIE-003)
  - `test_settings_repr_masks_set_cookie`: `repr(LinkedInScraperSettings(..., auth_cookie=SecretStr("AQEAAAAQEAAA")))` contiene `"<set>"` y NO contiene `"AQEAAAAQEAAA"` (REQ-LA-COOKIE-004)
  - `test_settings_repr_masks_unset_cookie`: `repr(..., auth_cookie=None)` contiene `"<unset>"` (REQ-LA-COOKIE-004)
  - `test_settings_eq_hash_includes_auth_cookie`: dos settings con distinto cookie → `!=` y `hash()` distinto (REQ-LA-COOKIE-004)
  - `test_fake_double_conforms_to_protocol`: `port: LinkedInAuthCookiePort = fake` typed assignment pasa mypy --strict
- Modificar `backend/src/jobs_finder/application/ports.py` (MODIFY, +12 LOC):
  - Agregar `from pydantic import SecretStr` (ya importado en otros archivos; verificar primero)
  - Agregar `class LinkedInAuthCookiePort(Protocol)` con un único método `def cookie(self) -> SecretStr | None: ...` después de `NoOpRateLimiter` (~L642)
- Crear `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` (NEW, ~30 LOC):
  - `class EnvLinkedInAuthCookieAdapter` con `__slots__ = ("_cookie",)`, ctor `(self, cookie: SecretStr | None)`, método `cookie() -> SecretStr | None` que retorna el valor sin loggear
  - `__init__.py` del package `linkedin/` SIN CAMBIOS (per AGENTS.md rule #4; el adapter se importa desde el path completo del módulo)
- Modificar `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (MODIFY, +5 LOC, parte de T-001 para ship el test double + Protocol together):
  - `LinkedInScraperSettings.__slots__`: agregar `"auth_cookie"` en la lista
  - `__init__`: agregar kwarg keyword-only `auth_cookie: LinkedInAuthCookiePort | None = None` y `self.auth_cookie = auth_cookie`
  - `__repr__`: incluir `auth_cookie=<set>` / `auth_cookie=<unset>` (masked, nunca el value)
  - `__eq__`/`__hash__`: incluir `auth_cookie` en la comparación y el hash
- Modificar `backend/tests/conftest.py` (MODIFY, +12 LOC):
  - Agregar `class FakeLinkedInAuthCookiePort` companion con `__init__(self, cookie: SecretStr | None = None)`, `__slots__ = ("_cookie",)`, método `cookie() -> SecretStr | None` que retorna el value
  - Default `None` (anonymous scraper v1 behavior)
- Confirmar RED (`uv run pytest tests/unit/test_linkedin_auth_cookie.py -v` falla con ImportError/AttributeError), implementar hasta GREEN, correr `uv run pytest` (suite completa, debe seguir verde), `uv run mypy --strict`, `uv run ruff check`, `uv run ruff format --check`

**Files**:
- `backend/src/jobs_finder/application/ports.py` (MODIFY — +`LinkedInAuthCookiePort` Protocol + import `SecretStr`)
- `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` (NEW — `EnvLinkedInAuthCookieAdapter`)
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (MODIFY — settings kwarg/repr/eq/hash)
- `backend/tests/conftest.py` (MODIFY — `FakeLinkedInAuthCookiePort` companion)
- `backend/tests/unit/test_linkedin_auth_cookie.py` (NEW — 8 tests)

**Acceptance**:
- 8+ tests pasan
- `LinkedInAuthCookiePort` existe en `application/ports.py` con exactamente 1 método
- `EnvLinkedInAuthCookieAdapter` y `FakeLinkedInAuthCookiePort` satisfacen `LinkedInAuthCookiePort` (mypy --strict verified)
- `LinkedInScraperSettings.__repr__` con `auth_cookie=SecretStr("AQEAAAAQEAAA")` contiene `"<set>"` y NO contiene `"AQEAAAAQEAAA"`
- `LinkedInScraperSettings.__eq__`/`__hash__` incluye `auth_cookie`
- Full suite (1,142+ tests) sigue verde — la scraper NO usa el kwarg aún (T-004 lo plumb); el default `auth_cookie=None` preserva v1 behavior
- Mypy --strict limpio
- Ruff limpio
- **Cero valores reales de `li_at` en cualquier archivo committeado** (el único valor sintético es `"AQEAAAAQEAAA"`)

**RED test sample** (`test_linkedin_auth_cookie.py::test_adapter_returns_secretstr_with_masked_repr`):
```python
def test_adapter_returns_secretstr_with_masked_repr() -> None:
    from pydantic import SecretStr
    from jobs_finder.infrastructure.linkedin.auth_cookie import (
        EnvLinkedInAuthCookieAdapter,
    )
    adapter = EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))
    result = adapter.cookie()
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "AQEAAAAQEAAA"
    assert repr(result) == "SecretStr('**********')"  # masked, not the raw
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py`):
```python
from pydantic import SecretStr

class EnvLinkedInAuthCookieAdapter:
    """Reads `li_at` from `Settings.linkedin_li_at` (no I/O at runtime)."""
    __slots__ = ("_cookie",)
    def __init__(self, cookie: SecretStr | None) -> None:
        self._cookie = cookie
    def cookie(self) -> SecretStr | None:
        return self._cookie
```

**Commit subject**: `feat(linkedin-auth): add LinkedInAuthCookiePort + EnvAdapter + test double`

**Rollback**: `git revert <commit-sha>` — el Protocol + adapter + test double + settings kwarg son aditivos; no hay scraper que los use aún, no hay regresión.

---

### T-002: `Settings.linkedin_li_at: SecretStr | None` field + 2 validators

**Type**: feature + test-first
**Scope**:
- **RED tests first** en `backend/tests/unit/test_linkedin_config.py` (NEW, ~70 LOC):
  - `test_settings_reads_linkedin_li_at_from_env`: monkeypatch `LINKEDIN_LI_AT=AQEAAAAQEAAA` → `Settings().linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"` (REQ-LA-CFG-001)
  - `test_settings_linkedin_li_at_defaults_to_none`: sin env var → `Settings().linkedin_li_at is None` (REQ-LA-CFG-001)
  - `test_settings_linkedin_li_at_programmatic_construction`: `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")).linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"` (REQ-LA-CFG-001)
  - `test_settings_rejects_short_li_at_3_chars`: `Settings(linkedin_li_at=SecretStr("abc"))` raises `pydantic.ValidationError` con `"must be at least 8 characters"` + `"got 3"` (REQ-LA-CFG-002)
  - `test_settings_rejects_short_li_at_7_chars`: 7 chars también raises (boundary `<8`, NO `≤8`) (REQ-LA-CFG-002)
  - `test_settings_accepts_minimum_length_8`: 8 chars exactos pasa (boundary inclusive) (REQ-LA-CFG-002)
  - `test_settings_accepts_none_li_at`: `Settings(linkedin_li_at=None).linkedin_li_at is None` (REQ-LA-CFG-003)
  - `test_settings_normalizes_empty_secret_to_none`: `Settings(linkedin_li_at=SecretStr("")).linkedin_li_at is None` (REQ-LA-CFG-003)
  - `test_settings_normalizes_empty_string_to_none`: `Settings(linkedin_li_at="").linkedin_li_at is None` (REQ-LA-CFG-003)
  - `test_settings_repr_does_not_leak_cookie_value`: `repr(Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")))` NO contiene `"AQEAAAAQEAAA"` (REQ-LA-CFG-004)
- Modificar `backend/src/jobs_finder/infrastructure/config.py` (MODIFY, +25 LOC):
  - Agregar el field `linkedin_li_at: SecretStr | None = Field(default=None, validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at"))` DESPUÉS de `linkedin_inter_page_delay_seconds` (~L292)
  - Agregar 2 `field_validator`s (mismo bloque LinkedIn): `_normalize_empty_li_at(mode="before")` y `_reject_short_li_at(mode="after")` (signatures en design §2.4)
- Confirmar RED → GREEN → full suite → mypy/ruff

**Files**:
- `backend/src/jobs_finder/infrastructure/config.py` (MODIFY — +field + 2 validators)
- `backend/tests/unit/test_linkedin_config.py` (NEW — 10 tests)

**Acceptance**:
- 10+ tests pasan
- `Settings()` sin env var tiene `linkedin_li_at is None`
- `Settings(linkedin_li_at=SecretStr("abc"))` raises `ValidationError` con mensaje específico
- `Settings(linkedin_li_at=SecretStr("12345678"))` (8 chars) pasa
- Mypy --strict limpio
- **Ningún valor real de `li_at` en `test_linkedin_config.py`** (sólo `"AQEAAAAQEAAA"` como sentinel)

**RED test sample** (`test_linkedin_config.py::test_settings_rejects_short_li_at_3_chars`):
```python
def test_settings_rejects_short_li_at_3_chars(monkeypatch) -> None:
    import pytest
    from pydantic import SecretStr, ValidationError
    monkeypatch.setenv("LINKEDIN_LI_AT", "abc")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    msg = str(exc_info.value)
    assert "must be at least 8 characters" in msg
    assert "got 3" in msg
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/config.py`):
```python
linkedin_li_at: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at"),
)

@field_validator("linkedin_li_at", mode="before")
@classmethod
def _normalize_empty_li_at(cls, v: SecretStr | str | None) -> SecretStr | None:
    if v is None: return None
    if isinstance(v, SecretStr): return v if v.get_secret_value() else None
    if isinstance(v, str): return SecretStr(v) if v else None
    return v

@field_validator("linkedin_li_at", mode="after")
@classmethod
def _reject_short_li_at(cls, v: SecretStr | None) -> SecretStr | None:
    if v is None: return None
    if len(v.get_secret_value()) < 8:
        raise ValueError(
            f"LINKEDIN_LI_AT must be at least 8 characters (got {len(v.get_secret_value())}); "
            "check for typos or unset the variable to run the scraper anonymously."
        )
    return v
```

**Commit subject**: `feat(linkedin-auth): add Settings.linkedin_li_at field + 2 validators`

**Rollback**: `git revert <commit-sha>` — el field es `default=None`, el scraper NO lo lee aún (T-004 lo consume); no hay regresión.

---

### T-003: `is_auth_wall(soup)` pure function en `parsers.py`

**Type**: feature + test-first
**Scope**:
- **RED tests first** en `backend/tests/unit/test_linkedin_auth_wall.py` (NEW, ~50 LOC):
  - `test_is_auth_wall_signature`: `inspect.signature(is_auth_wall) == "(soup: BeautifulSoup) -> bool"` (REQ-LA-AWALL-001)
  - `test_is_auth_wall_is_pure_no_mutation`: `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` retorna True Y el `soup.prettify()` antes/después es idéntico (REQ-LA-AWALL-001)
  - `test_is_auth_wall_true_for_block_page_fixture`: `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML)) is True` (REQ-LA-AWALL-002)
  - `test_is_auth_wall_false_for_healthy_serp`: `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML)) is False` (REQ-LA-AWALL-003)
  - `test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class`: HTML fragment con `body.auth-wall` + 1 card → `False` (cards win) (REQ-LA-AWALL-004)
- Modificar `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (MODIFY, +12 LOC):
  - Agregar `def is_auth_wall(soup: BeautifulSoup) -> bool:` DESPUÉS de `is_block_page` (~L242)
  - Implementación: `soup.select_one("body.auth-wall, .auth-wall")` → check `select("div[data-entity-urn]")` (cards win) → return True si hay signal Y no hay cards
- Confirmar RED → GREEN → full suite → mypy/ruff

**Files**:
- `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (MODIFY — +`is_auth_wall` pure function)
- `backend/tests/unit/test_linkedin_auth_wall.py` (NEW — 5 tests)

**Acceptance**:
- 5+ tests pasan
- `is_auth_wall` vive en `parsers.py` junto a `is_block_page`
- Función pura: no I/O, no `await`, no logging, no mutación del input
- Full suite (1,142+ tests) sigue verde — el scraper NO llama `is_auth_wall` aún (T-004 lo invoca)
- Mypy --strict limpio

**RED test sample** (`test_linkedin_auth_wall.py::test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class`):
```python
def test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class() -> None:
    from bs4 import BeautifulSoup
    from jobs_finder.infrastructure.linkedin.parsers import is_auth_wall
    html = (
        '<body class="auth-wall">'
        '<div data-entity-urn="urn:li:jobPosting:1"></div>'
        '</body>'
    )
    soup = BeautifulSoup(html, "html.parser")
    assert is_auth_wall(soup) is False  # cards win
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/linkedin/parsers.py`):
```python
def is_auth_wall(soup: BeautifulSoup) -> bool:
    auth_wall_signal = soup.select_one("body.auth-wall, .auth-wall")
    if auth_wall_signal is None:
        return False
    if soup.select("div[data-entity-urn]"):
        return False   # cards win — false positive suppressed
    return True
```

**Commit subject**: `feat(linkedin-auth): add is_auth_wall defensive detector to parsers`

**Rollback**: `git revert <commit-sha>` — la función es additive; sin callers aún, no hay regresión.

---

### T-004: `LinkedInPlaywrightScraper.search()` cookie injection + closure `is_auth_wall` integration

**Type**: feature + test-first
**Scope**:
- **RED tests first** en `backend/tests/unit/test_linkedin_scraper.py` (EXTEND, +90 LOC, 5 tests):
  - `test_search_reads_cookie_from_injected_port_not_env`: scraper con `auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("SYNTHETIC_FROM_PORT"))` + env var `LINKEDIN_LI_AT=REAL_ENV_VALUE` → la cookie que llega a `FakeContext.add_cookies` es `"SYNTHETIC_FROM_PORT"`, NO `"REAL_ENV_VALUE"` (REQ-LA-SCR-001)
  - `test_add_cookies_called_with_correct_shape`: `FakeBrowser.add_cookies_calls[0][0] == [{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]` (golden assertion) (REQ-LA-SCR-002 + REQ-LA-SCR-004)
  - `test_no_add_cookies_call_when_auth_cookie_none`: scraper con `auth_cookie=None` → `FakeContext.add_cookies` NUNCA se llama (REQ-LA-SCR-003)
  - `test_add_cookies_called_once_per_search`: 1 call a `search()` con `limit=50` (2 pages) → `len(add_cookies_calls) == 1` (NO per page) (REQ-LA-SCR-006)
  - `test_add_cookies_called_once_per_search_for_multiple_searches`: 2 calls a `search()` → `len(add_cookies_calls) == 2` (REQ-LA-SCR-006)
  - `test_search_does_not_log_cookie_value`: `caplog` set a DEBUG → ningún log record contiene `"AQEAAAAQEAAA"` (REQ-LA-SCR-005)
  - `test_closure_warns_on_auth_wall_zero_cards`: `BLOCK_PAGE_HTML` (auth wall + 0 cards) → WARNING con prefijo `"LinkedIn SERP appears auth-walled despite cookie injection"` + `search()` retorna `[]` (REQ-LA-AWALL-005/006)
  - `test_closure_does_not_warn_when_cards_present_with_auth_wall_class`: HTML con auth wall + 3 cards → NO WARNING (cards win) (REQ-LA-AWALL-005)
  - `test_closure_returns_empty_list_on_auth_wall_no_raise`: scraper con cookie + auth wall page → retorna `[]`, NO raises (REQ-LA-AWALL-006)
- Extender `FakeBrowser`/`FakeContext` local en `test_linkedin_scraper.py` con `add_cookies_calls: list[list[dict]]` que registra `kwargs["cookies"]` (ver patrón de `test_indeed_scraper.py:108-122`)
- Modificar `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (MODIFY, +13 LOC, 2 changes):
  - **search() injection** (después de `new_context()` ~L274):
    - `cookie = self._settings.auth_cookie.cookie() if self._settings.auth_cookie is not None else None`
    - `if cookie is not None: await ctx.add_cookies([{... 6 fields ...}])` + `_logger.debug("LinkedIn auth cookie injected (length=%d)", len(cookie.get_secret_value()))`
  - **Closure integration** (en `fetch_one_page` ~L343):
    - DESPUÉS de `is_block_page(soup)` check, AGREGAR `if is_auth_wall(soup): _logger.warning("LinkedIn SERP appears auth-walled despite cookie injection; cookie may be expired. Returning 0 jobs from this page (degraded).")` ANTES de `_parse_cards`
- Confirmar RED → GREEN → full suite → mypy/ruff

**Files**:
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (MODIFY — `search()` injection + closure `is_auth_wall` call)
- `backend/tests/unit/test_linkedin_scraper.py` (EXTEND — +9 tests, +FakeBrowser.add_cookies_calls)

**Acceptance**:
- 9+ tests pasan
- `ctx.add_cookies` se llama UNA vez por `search()` con la shape exacta (golden assertion)
- `ctx.add_cookies` se llama SOLO cuando `auth_cookie.cookie()` retorna no-None
- El closure emite WARNING con prefijo exacto cuando `is_auth_wall(soup)` returns True
- `caplog` no contiene `"AQEAAAAQEAAA"` en ningún log record durante `search()`
- Full suite (1,142+ tests) sigue verde — el `auth_cookie` default es `None`, preserva v1 behavior
- Mypy --strict limpio
- Ruff limpio
- **Cero valores reales de `li_at` en `test_linkedin_scraper.py`**

**RED test sample** (`test_linkedin_scraper.py::test_add_cookies_called_with_correct_shape`):
```python
async def test_add_cookies_called_with_correct_shape() -> None:
    from pydantic import SecretStr
    from jobs_finder.infrastructure.linkedin.auth_cookie import (
        EnvLinkedInAuthCookieAdapter,
    )
    from jobs_finder.infrastructure.linkedin.scraper import (
        LinkedInPlaywrightScraper,
        LinkedInScraperSettings,
    )
    # ... build FakePage + FakeBrowser + scraper with auth_cookie ...
    scraper, fake_browser = _make_scraper_with(
        page, auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))
    )
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
    assert fake_browser.contexts[0].add_cookies_calls == [[
        {"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com",
         "path": "/", "httpOnly": True, "secure": True}
    ]]
```

**GREEN impl sketch** (`backend/src/jobs_finder/infrastructure/linkedin/scraper.py`):
```python
ctx = await self._browser.new_context(
    user_agent=self._settings.user_agent,
    viewport=VIEWPORT,
)
cookie = (
    self._settings.auth_cookie.cookie()
    if self._settings.auth_cookie is not None else None
)
if cookie is not None:
    await ctx.add_cookies([{
        "name": "li_at", "value": cookie.get_secret_value(),
        "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True,
    }])
    _logger.debug("LinkedIn auth cookie injected (length=%d)", len(cookie.get_secret_value()))
try:
    page = await ctx.new_page()
    # ... existing paginated_search ...
```

**Commit subject**: `feat(linkedin-scraper): inject li_at cookie in search() + warn on auth_wall`

**Rollback**: `git revert <commit-sha>` — el `auth_cookie=None` default preserva v1; la integración `is_auth_wall` solo agrega un WARNING (no-op cuando retorna False).

---

### T-005: Composition root wire + integration test + `README.md` + `.env.example`

**Type**: feature + docs
**Scope**:
- **RED tests first** en `backend/tests/integration/test_linkedin_auth_cookie.py` (NEW, ~60 LOC):
  - `test_startup_warning_when_cookie_absent`: `Settings()` sin `LINKEDIN_LI_AT` env var + `caplog` set a WARNING + `build_app()` → exactly 1 WARNING con msg `"LinkedIn scraper running without auth cookie; SERP will hit the auth wall and return a reduced list"` (REQ-LA-SCR-003)
  - `test_wired_app_uses_env_cookie_when_set`: monkeypatch `LINKEDIN_LI_AT=AQEAAAAQEAAA` + `build_app()` + assert que el scraper resultante tiene `auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))` (REQ-LA-SCR-001)
  - `test_no_startup_warning_when_cookie_set`: monkeypatch `LINKEDIN_LI_AT=AQEAAAAQEAAA` + `build_app()` → NO WARNING (REQ-LA-SCR-003)
- Modificar `backend/src/jobs_finder/presentation/app_factory.py` (MODIFY, +12 LOC):
  - Importar `EnvLinkedInAuthCookieAdapter` desde `jobs_finder.infrastructure.linkedin.auth_cookie`
  - En el bloque `if use_case is None:` (~L239), ANTES del `LinkedInPlaywrightScraper(...)` ctor:
    - `auth_cookie_port = EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)`
    - `if effective_settings.linkedin_li_at is None: _logger.warning("LinkedIn scraper running without auth cookie; SERP will hit the auth wall and return a reduced list")`
  - Agregar `auth_cookie=auth_cookie_port` kwarg al `LinkedInScraperSettings(...)` (~L252)
- Modificar `backend/.env.example` (MODIFY, +6 LOC):
  - Agregar línea `LINKEDIN_LI_AT=` (empty) al final del bloque LinkedIn existente (líneas 22-51)
  - Comentario explicativo: `# Set to your own li_at session cookie (NEVER commit the real value) — see backend/README.md "LinkedIn auth cookie (optional)" section. Leave empty to run the scraper anonymously (v1 behavior).`
- Modificar `backend/README.md` (MODIFY, +35 LOC):
  - Nueva sección `### LinkedIn auth cookie (optional)` DESPUÉS de las subsecciones LinkedIn-related existentes en la sección "Manual verification"
  - Contenido: cómo setear la env var (shell + `.env`), curl example con `LINKEDIN_LI_AT`, comportamiento esperado (stream completo, sin auth wall), FAQ "qué pasa si mi cookie expira?" (link al detector `is_auth_wall` WARNING), legal notice link
- **RED tests for docs** en `backend/tests/unit/test_linkedin_auth_cookie.py` (o nuevo `test_linkedin_auth_docs.py`):
  - `test_env_example_documents_linkedin_li_at`: grep `backend/.env.example` por `LINKEDIN_LI_AT=`
  - `test_readme_documents_linkedin_auth_cookie_subsection`: grep `backend/README.md` por `LinkedIn auth cookie (optional)`
- Correr `cd backend && bash scripts/check.sh` final: ruff + mypy + pytest all GREEN
- Este es el **último commit** del PR ("wiring complete + operator docs")

**Files**:
- `backend/src/jobs_finder/presentation/app_factory.py` (MODIFY — wire + startup WARNING)
- `backend/.env.example` (MODIFY — +placeholder line + comment)
- `backend/README.md` (MODIFY — new subsection)
- `backend/tests/integration/test_linkedin_auth_cookie.py` (NEW — 3 integration tests)
- `backend/tests/unit/test_linkedin_auth_cookie.py` (EXTEND — +2 doc tests, optional)

**Acceptance**:
- 3+ integration tests pasan
- 2+ doc tests pasan (grep)
- `build_app()` con `LINKEDIN_LI_AT` unset emite 1 WARNING con texto exacto
- `build_app()` con `LINKEDIN_LI_AT=AQEAAAAQEAAA` set NO emite WARNING
- `backend/.env.example` incluye la línea `LINKEDIN_LI_AT=` con nota de seguridad
- `backend/README.md` incluye la nueva subsección
- Full suite (1,142+ existentes + 27+ nuevos) verde
- Mypy --strict limpio
- Ruff limpio
- Conventional commit: `feat(composition): wire LinkedIn auth cookie + operator docs`

**RED test sample** (`tests/integration/test_linkedin_auth_cookie.py::test_startup_warning_when_cookie_absent`):
```python
def test_startup_warning_when_cookie_absent(caplog) -> None:
    import logging
    from jobs_finder.presentation.app_factory import build_app
    caplog.set_level(logging.WARNING)
    app = build_app()  # no LINKEDIN_LI_AT in env
    matching = [r for r in caplog.records
                if "LinkedIn scraper running without auth cookie" in r.getMessage()]
    assert len(matching) == 1  # exactly ONE startup warning
```

**GREEN impl sketch** (`backend/src/jobs_finder/presentation/app_factory.py`):
```python
from jobs_finder.infrastructure.linkedin.auth_cookie import (
    EnvLinkedInAuthCookieAdapter,
)
# ... inside build_app(), in the `if use_case is None:` block ...
auth_cookie_port = EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)
if effective_settings.linkedin_li_at is None:
    _logger.warning(
        "LinkedIn scraper running without auth cookie; "
        "SERP will hit the auth wall and return a reduced list"
    )
scraper = LinkedInPlaywrightScraper(
    throttle=...,
    settings=LinkedInScraperSettings(
        # ... existing kwargs ...
        auth_cookie=auth_cookie_port,
    ),
)
```

**Commit subject**: `feat(composition): wire LinkedIn auth cookie + operator docs`

**Rollback**: `git revert <commit-sha>` — el adapter ctor con `SecretStr | None` siempre funciona; sin `auth_cookie=` kwarg, el scraper corre anónimo (v1 behavior). Docs revert es independiente.

---

## Work unit ordering (dependency graph)

```
T-001 ─────────────────────┐
   (Protocol + Adapter)   │
                          ▼
T-002 ─────► (T-004) ◄── T-003
(Settings)              (is_auth_wall pure)
                ▲
                │
                │ (T-004 reads Protocol + detector)
                │
                ▼
T-005 (composition wire + integration + docs)
   depends on T-001 (adapter), T-002 (Settings field), T-004 (scraper uses it)
```

- **T-001 primero**: el Protocol + adapter + test double son la fundación. Sin ellos, T-004 no puede usar el kwarg `auth_cookie` con mypy --strict clean, y T-005 no puede inyectar el adapter.
- **T-002 depende de T-001 (implícitamente)**: T-002 introduce `Settings.linkedin_li_at` que T-005 consume. T-002 también agrega un campo al `Settings` model, que es estable independientemente del scraper.
- **T-003 independiente** en términos de código: pure function, no toca el scraper. Puede ir antes o después de T-002; se posiciona después para que el "tipo de cambio" sea: T-001 (Protocol/adapter) → T-002 (Settings) → T-003 (parser) → T-004 (scraper) → T-005 (wire/docs).
- **T-004 depende de T-001 + T-003**: el scraper usa el Protocol (T-001) y el detector (T-003). Default `auth_cookie=None` preserva v1 behavior.
- **T-005 último**: wire en composition root + integration test + operator docs. Cierra el PR.

## PR slice recommendation

- **Estrategia**: `single-pr` (5 commits convencionales)
- **Review burden**: ~540 LOC total, ~108 LOC/commit promedio → bien dentro del budget de 400 líneas y del budget de 5000 líneas
- **Orden de commits = orden de T-NNN**:
  1. `feat(linkedin-auth): add LinkedInAuthCookiePort + EnvAdapter + test double` (T-001, ~165 LOC: ports.py +12, auth_cookie.py +30, scraper.py +5, conftest.py +12, test_linkedin_auth_cookie.py +120)
  2. `feat(linkedin-auth): add Settings.linkedin_li_at field + 2 validators` (T-002, ~95 LOC: config.py +25, test_linkedin_config.py +70)
  3. `feat(linkedin-auth): add is_auth_wall defensive detector to parsers` (T-003, ~62 LOC: parsers.py +12, test_linkedin_auth_wall.py +50)
  4. `feat(linkedin-scraper): inject li_at cookie in search() + warn on auth_wall` (T-004, ~103 LOC: scraper.py +13, test_linkedin_scraper.py +90)
  5. `feat(composition): wire LinkedIn auth cookie + operator docs` (T-005, ~115 LOC: app_factory.py +12, .env.example +6, README.md +35, test_linkedin_auth_cookie.py integration +60, doc tests +2)
- **Single rollback unit**: revert del merge commit. Sin DB state, sin migraciones, sin env var required at runtime (default `None` = v1 anonymous).
- **Mínimo-size de cada commit**: T-001 + T-002 pueden mergear en uno solo si la review surface de 260 LOC es incómoda; los 3 commits T-003/T-004/T-005 son independientes y pueden partirse.

## Strict TDD discipline (per `_shared/strict-tdd.md`)

Para CADA task T-NNN, el executor DEBE:

1. **RED**: escribir los tests listados PRIMERO. Confirmar que fallan con `cd backend && uv run pytest <test_file>::<test_name> -x` (exit non-zero).
2. **GREEN**: implementar el cambio mínimo que hace pasar los tests. Confirmar con el mismo comando (exit zero).
3. **No regression**: correr `cd backend && uv run pytest` (suite completa, debe seguir verde).
4. **Type/lint**: `cd backend && uv run mypy --strict && uv run ruff check && uv run ruff format --check` (debe estar limpio).
5. **Commit**: conventional commits SIN `Co-Authored-By` ni atribución AI.
   - Features: `feat(<scope>): <subject>` (scope = `linkedin-auth` para T-001/T-002/T-003, `linkedin-scraper` para T-004, `composition` para T-005)
   - Tests: `test(<scope>): <subject>` (si se commitea por separado)
   - Docs: `docs(<scope>): <subject>` (si se commitea por separado)

## Pre-apply checklist

- [x] 5 tasks identificados con acceptance criteria claros
- [x] Dependency order documentado (T-001 → T-002/T-003 → T-004 → T-005)
- [x] Single PR recomendado (~540 LOC < 400-line budget per commit avg, < 5000-line review budget)
- [x] Cero cambios fuera de `backend/` (modifica `backend/.env.example` y `backend/README.md`, no toca `openspec/specs/` ni `frontend/`)
- [x] `backend/README.md` actualizado (T-005) + `backend/.env.example` extendido (T-005)
- [x] Strict TDD discipline por task (RED → GREEN → suite → mypy/ruff)
- [x] El "boot works at every step" rule se mantiene: T-001/T-002/T-003 son aditivos, T-004 default `auth_cookie=None` preserva v1, T-005 wire + docs
- [x] Cero valores reales de `li_at` en cualquier archivo committeado (sólo `"AQEAAAAQEAAA"` como sentinel)
- [x] El adapter ctor toma `SecretStr | None` (valor), NO `Settings` (T-001 + diseño §2.3)
- [x] El `is_auth_wall` no es el mismo que `is_block_page` (semántica distinta; conviven)
- [x] `__init__.py` files del package `linkedin/` SIN CAMBIOS (AGENTS.md rule #4)
- [x] `LinkedInAuthCookie` value object NO se introduce (diseño §2.2 lo removió; el Protocol retorna `SecretStr | None` directo)

## Files affected (resumen)

| File | Action | LOC est. |
|---|---|---|
| `backend/src/jobs_finder/application/ports.py` | MODIFY: +`LinkedInAuthCookiePort` Protocol + import `SecretStr` | +12 |
| `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` | NEW: `EnvLinkedInAuthCookieAdapter` | +30 |
| `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` | MODIFY: settings kwarg + repr/eq/hash (T-001) + search() injection + closure `is_auth_wall` (T-004) | +18, -2 |
| `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` | MODIFY: +`is_auth_wall` pure function | +12 |
| `backend/src/jobs_finder/infrastructure/config.py` | MODIFY: +`linkedin_li_at` field + 2 validators | +25 |
| `backend/src/jobs_finder/presentation/app_factory.py` | MODIFY: wire + startup WARNING | +12 |
| `backend/.env.example` | MODIFY: +placeholder line + security comment | +6 |
| `backend/README.md` | MODIFY: new "LinkedIn auth cookie (optional)" subsection | +35 |
| `backend/tests/conftest.py` | MODIFY: +`FakeLinkedInAuthCookiePort` companion | +12 |
| `backend/tests/unit/test_linkedin_auth_cookie.py` | NEW: 8 tests (T-001) + 2 doc tests (T-005) | +120 |
| `backend/tests/unit/test_linkedin_config.py` | NEW: 10 tests | +70 |
| `backend/tests/unit/test_linkedin_auth_wall.py` | NEW: 5 tests | +50 |
| `backend/tests/unit/test_linkedin_scraper.py` | MODIFY: +9 tests + FakeBrowser.add_cookies_calls | +90 |
| `backend/tests/integration/test_linkedin_auth_cookie.py` | NEW: 3 integration tests | +60 |
| **TOTAL** | | **~542** |

## Coordination notes

- El cambio paralelo `backend-infojobs-provinces` ya está archivado (HEAD `017d6fa`); no hay colisión de settings (infojobs usa `infojobs_*`-prefixed fields; este change usa `linkedin_li_at`).
- El `FakeJobSearchPort` en `conftest.py:70-119` NO necesita cambios — `LinkedInAuthCookiePort` es un Protocol nuevo e independiente (no extiende el `JobSearchPort`).
- El `app` fixture en `conftest.py:180-218` NO necesita cambios — el `auth_cookie` kwarg default es `None`, los 3 use cases siguen funcionando sin cookie.
- El cache key (`JobSearchCacheKey`) NO incluye la cookie — la cookie es side-effect state, no input. El cache hit preserva el resultado de la primera query (que puede o no haber sido con cookie).
- El test `test_closure_does_not_warn_when_cards_present_with_auth_wall_class` es el regression check para el "cards win" rule (REQ-LA-AWALL-004); este test es crítico porque detecta la falsa-positiva más común (LinkedIn renderiza `class="auth-wall"` en SERPs healthy como markup defensivo).

## Risks (carry-forward + apply-phase risks)

| # | Risk | Mitigation |
|---|------|------------|
| 1 | `li_at` cookie real leak al repo (AGENTS.md rule #7) | T-001/T-002 usan `"AQEAAAAQEAAA"` sintético; T-005 deja `LINKEDIN_LI_AT=` empty en `.env.example`; `__repr__` masks en `LinkedInScraperSettings`; `SecretStr` type |
| 2 | Test doble no conforma al Protocol → mypy --strict fail | T-001 incluye `test_fake_double_conforms_to_protocol` + `mypy --strict` en cada quality gate |
| 3 | El closure de `_make_fetch_one_page` se rompe con un T-004 reorder | T-004 mantiene `is_block_page` check intacto y agrega `is_auth_wall` ANTES de `_parse_cards`; `paginated_search` helper NO se toca |
| 4 | `.env.example` accidentalmente commitea un valor real | T-005 incluye `test_env_example_documents_linkedin_li_at` que greps la presencia de `LINKEDIN_LI_AT=` (NO el valor) |
| 5 | `add_cookies` API change en Playwright | T-004 incluye `test_add_cookies_called_with_correct_shape` (golden assertion) que falla en cualquier drift |
| 6 | El scraper corre async; los tests con `FakeBrowser` deben cerrar el `async with scraper` block | T-004 sigue el patrón de `test_indeed_scraper.py` (que ya usa `async with scraper` + `browser_factory` injection) |
| 7 | `LinkedInScraperSettings.__eq__`/`__hash__` cambio (T-001) rompe tests existentes que comparan settings | El `auth_cookie` kwarg default es `None`; dos `LinkedInScraperSettings(...)` sin `auth_cookie=` kwarg tienen `auth_cookie=None` y son `==`; tests existentes no se rompen |
| 8 | `Settings.linkedin_li_at` field rompe tests existentes de Settings | T-002 default es `None`; los 1,142+ tests existentes que construyen `Settings()` no pasan `linkedin_li_at=`, obtienen `None`; no hay regresión |
| 9 | Cookie expirada produce resultados degradados sin operator awareness | T-003 + T-004 + T-005 (composition wire con startup WARNING) cubren los 3 angles: el detector loggea WARNING, el README lo explica, el startup WARNING al build lo anuncia |
| 10 | `__init__.py` files del package `linkedin/` se modifican accidentalmente | T-001 explícitamente excluye: "El `__init__.py` del package `linkedin/` SIN CAMBIOS (per AGENTS.md rule #4)" |
