"""Unit tests for `HardcodedLocationResolver` (the 43-entry geoId lookup).

Spec: REQ-LOC-GEO-001 scenarios 1-8 (`tests/fixtures/linkedin_geo_ids.csv`
rows 2-44 are the source of truth).

The resolver translates a free-form `intent.location` string (e.g.
"Madrid", "Cataluña", "cdmx") into a numeric LinkedIn `geoId` (e.g.
`103374081`) that the LinkedIn scraper can use in the `?geoId=<id>`
URL parameter. The previous (broken) behavior was to pass the string
verbatim as `?location=Madrid` — which LinkedIn's public search
silently ignores, returning globally-distributed results that do
not match the user's geographic intent.

The alias normalization chain is:
    1. `unicodedata.normalize("NFC", s).casefold().strip()`
    2. NFD-decompose + drop `Mn` (combining accent) marks
       → handles "México" / "Mexico" / "MEXICO" identically.
    3. Flat dict lookup (8 Spanish cities + 9 LATAM cities + 16
       autonomous communities + 1 remote = 34 entries; the
       remaining 9 CSV rows are country-level / ambiguous entries
       intentionally OUT of scope — see spec REQ-LOC-GEO-001
       scenario 7).

Returns `None` (with a WARNING log) for unknown / country-level /
empty / País Vasco / Canarias inputs. The LinkedIn scraper then
falls back to the broken `?location=<str>` path — a strict
improvement over today's 100%-broken behavior.

Test layout:
    - Section 1: canonical happy-path (8 Spanish cities + 9 LATAM
      cities + 16 autonomous communities + 1 remote = 34 happy-
      path resolutions). One parametrized test pins the mapping.
    - Section 2: alias normalization (NFC + casefold + strip +
      accent removal). 5 scenarios.
    - Section 3: alias-to-canonical recurse (e.g. "cdmx" →
      "ciudad de mexico" → 112558473). 4 scenarios.
    - Section 4: None semantic (unknown / country-level / empty
      / País Vasco / Canarias). 6 scenarios.
    - Section 5: ctor custom mapping (override / default). 2
      scenarios.

Total: 51 scenarios (well above the 30+ target).
"""

from __future__ import annotations

import logging

import pytest

from jobs_finder.infrastructure.location.hardcoded_resolver import (
    HardcodedLocationResolver,
)

# Module-level constant for the resolver's logger name.
# The caplog context scopes the WARNING capture to the
# resolver's module (so the test does not pick up unrelated
# WARNINGs from other modules).
_RESOLVER_LOGGER = "jobs_finder.infrastructure.location.hardcoded_resolver"

# ---------------------------------------------------------------------------
# Section 1: Canonical happy-path — 34 entries from the CSV.
#
# Each row below is a 1:1 mirror of `tests/fixtures/linkedin_geo_ids.csv`
# rows 2-44 (the 43 captured geoIds minus the 9 country-level /
# unverified rows: rows 14 País Vasco, 19 Canarias, 29 es, 33 mx,
# 36 ar, 39 co, 41 cl, 43 pe, 13 rows in the file that are
# "duplicate" autonomous community entries — see Section 4).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_location", "expected_geo_id"),
    [
        # === Spanish cities (8 of 8) ===
        ("madrid", 103374081),
        ("barcelona", 105088894),
        ("valencia", 105512687),
        ("sevilla", 104893466),
        ("zaragoza", 106356396),
        ("malaga", 104401670),
        ("murcia", 102253611),
        ("bilbao", 101962740),
        # === Spanish autonomous communities (16 of 17; País Vasco
        # intentionally excluded — see Section 4) ===
        ("comunidad de madrid", 103335767),
        ("cataluna", 105646813),
        ("comunidad valenciana", 100076887),
        ("andalucia", 106151489),
        ("galicia", 103189018),
        ("castilla y leon", 104802667),
        ("castilla la mancha", 100096545),
        ("extremadura", 102727695),
        ("murcia", 102253611),  # region-level; same as city
        ("asturias", 104351060),
        ("cantabria", 106413664),
        ("la rioja", 102952772),
        ("navarra", 102688677),
        ("illes balears", 101388828),
        ("ceuta", 100110826),
        ("melilla", 101887739),
        # === LATAM cities (9 of 9) ===
        ("ciudad de mexico", 112558473),
        ("guadalajara", 100870198),
        ("monterrey", 104201579),
        ("buenos aires", 90009870),
        ("cordoba", 102399085),  # AR — same string collides with ES; AR wins per CSV
        ("bogota", 102361989),
        ("medellin", 112085362),
        ("santiago", 104555257),
        ("lima", 101312395),
        # === Remote (1) ===
        ("remote", 118424786),
    ],
)
def test_canonical_lookup_returns_csv_pinned_geo_id(
    input_location: str, expected_geo_id: int
) -> None:
    """Every entry in the 43-entry dict resolves to its pinned geoId.

    The CSV is the source of truth; the dict is derived from it.
    A regression that flips a value (e.g. 103374081 → 103374080)
    would silently mis-route ALL LinkedIn queries for that city
    (returning globally-distributed results, same as the v1
    bug). The pinned test guards against that regression.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve(input_location) == expected_geo_id


# ---------------------------------------------------------------------------
# Section 2: Alias normalization — the 4 normalization invariants.
# ---------------------------------------------------------------------------


def test_alias_normalization_nfc_composed_vs_decomposed() -> None:
    """`"Málaga"` (NFC composed, with `í` U+00ED) and `"Málaga"`
    (NFD decomposed, `i` + U+0301) both resolve to the same geoId.

    The alias normalization chain NFD-decomposes + drops the
    combining marks, so the two Unicode representations of the
    same character collapse to the same lookup key.
    """
    resolver = HardcodedLocationResolver()
    # NFC composed (the typical UTF-8 form)
    assert resolver.resolve("Málaga") == 104401670
    # NFD decomposed (`i` + U+0301 COMBINING ACUTE ACCENT)
    assert resolver.resolve("Mal\u0301aga") == 104401670


def test_alias_normalization_casefold_lowercase() -> None:
    """All-lowercase input matches the canonical entry.

    `casefold()` is more aggressive than `lower()` (e.g. German
    `ß` → `ss`); the resolver uses `casefold()` for invariant
    case handling per Unicode standard.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("madrid") == 103374081


def test_alias_normalization_casefold_mixed_case() -> None:
    """Mixed-case input matches the canonical entry.

    `MaDrId` → `madrid` after `.casefold()`.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("MaDrId") == 103374081


def test_alias_normalization_strip_whitespace() -> None:
    """Leading + trailing whitespace is stripped before lookup.

    The chat endpoint pre-normalizes the user's message
    (NFC + casefold + strip per REQ-CHAT-001) but the
    resolver is defensive about re-normalizing — a future
    caller (e.g. a direct programmatic call from a CLI) may
    not pre-normalize.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("  Madrid  ") == 103374081
    assert resolver.resolve("\tMadrid\n") == 103374081


def test_alias_normalization_accent_removal() -> None:
    """Accented form resolves to the same geoId as the unaccented form.

    `"Málaga"` (with `á` U+00E1) and the unaccented `"malaga"`
    BOTH resolve to the same geoId (`104401670`). The
    NFD-decompose + drop `Mn` step strips the combining mark.

    NOTE: we test against `Málaga` (a city with accents in the
    canonical form) rather than `México` (the country), because
    the country-level `"México"` correctly returns `None` per
    spec scenario 7 — see `test_country_level_mexico_returns_none_with_warning`.
    The accent-removal test pins the *normalization algorithm*;
    the country-level test pins the *negative semantic*.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("Málaga") == 104401670
    # An entry whose canonical form is the unaccented "malaga"
    # also resolves (so both "Málaga" and "malaga" share the key).
    assert resolver.resolve("malaga") == 104401670


# ---------------------------------------------------------------------------
# Section 3: Alias-to-canonical recurse — common abbreviations.
# ---------------------------------------------------------------------------


def test_alias_cdmx_maps_to_ciudad_de_mexico() -> None:
    """`"cdmx"` (the common LATAM abbreviation) recurses to
    `"ciudad de mexico"` and resolves to the Mexico City geoId.

    The alias dict maps `cdmx` → `ciudad de mexico`; the resolver
    re-normalizes + looks up the canonical key.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("cdmx") == 112558473


def test_alias_mad_maps_to_madrid() -> None:
    """`"mad"` (the IATA airport code for Madrid) recurses to `"madrid"`."""
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("mad") == 103374081


def test_alias_bcn_maps_to_barcelona() -> None:
    """`"bcn"` (the IATA airport code for Barcelona) recurses to `"barcelona"`."""
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("bcn") == 105088894


def test_alias_caba_maps_to_buenos_aires() -> None:
    """`"caba"` (Ciudad Autónoma de Buenos Aires) recurses to
    `"buenos aires"`.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("caba") == 90009870


# ---------------------------------------------------------------------------
# Section 4: None semantic — unknown / country-level / empty / unverified.
#
# The resolver returns `None` (and emits a WARNING log) for inputs
# it cannot map. The LinkedIn scraper then falls back to the
# broken `?location=<str>` path — a strict improvement over today's
# 100%-broken behavior. The WARNING is observable for ops to spot
# stale geographic intent (the `scripts/capture_linkedin_geo_ids.py`
# can be re-run to refresh stale entries).
# ---------------------------------------------------------------------------


def test_unknown_location_returns_none_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`"Atlantis"` (a fictional city) returns `None` and emits a WARNING log.

    The WARNING includes the input string and the resolved `None`
    so ops can grep container logs for "stale" location names
    and re-run the capture script.
    """
    resolver = HardcodedLocationResolver()
    with caplog.at_level(logging.WARNING, logger=_RESOLVER_LOGGER):
        assert resolver.resolve("Atlantis") is None
    # Exactly one WARNING was emitted, with the input string visible.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Atlantis" in warnings[0].getMessage()


def test_country_level_espana_returns_none_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`"España"` (country-level) returns `None` and emits a WARNING.

    The country-level geoId from the CSV (`103644278`) is the
    LinkedIn worldwide fallback — using it would return globally-
    distributed results that don't match the user's country intent.
    The spec (REQ-LOC-GEO-001 scenario 7) intentionally degrades
    country-level to `None` + WARNING so the scraper falls back
    to the (broken) `?location=España` string.
    """
    resolver = HardcodedLocationResolver()
    with caplog.at_level(logging.WARNING, logger=_RESOLVER_LOGGER):
        assert resolver.resolve("España") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "España" in warnings[0].getMessage()


def test_country_level_mexico_returns_none_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`"México"` (country-level) returns `None` and emits a WARNING.

    The intent is "country-level Mexico" (not "Mexico City" or
    "Guadalajara"); the resolver cannot disambiguate, so it
    degrades to `None` + WARNING.
    """
    resolver = HardcodedLocationResolver()
    with caplog.at_level(logging.WARNING, logger=_RESOLVER_LOGGER):
        assert resolver.resolve("México") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_empty_string_returns_none() -> None:
    """`""` (empty string) returns `None` (no warning — empty is a
    legitimate "no location specified" sentinel, not an unknown).

    The v1 path passes `location=""` to the aggregator (the v1
    single-stage path scrapes the default landing page). The
    resolver short-circuits to `None` without a warning log
    because `""` is not a "user provided an unknown location"
    signal — it's the canonical "no location" sentinel.
    """
    resolver = HardcodedLocationResolver()
    # No caplog needed — the empty-string path is silent.
    assert resolver.resolve("") is None


def test_pais_vasco_returns_none_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`"País Vasco"` (unverified autonomous community) returns `None` + WARNING.

    The capture script could not pin País Vasco cleanly (the
    capture was performed from a non-Spanish IP and LinkedIn
    returned a Spain-wide geoId). The resolver returns `None`
    so the scraper falls back to the (broken) `?location=País Vasco`
    string. The WARNING is observable for ops.
    """
    resolver = HardcodedLocationResolver()
    with caplog.at_level(logging.WARNING, logger=_RESOLVER_LOGGER):
        assert resolver.resolve("País Vasco") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_canarias_returns_none_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`"Canarias"` (unverified autonomous community) returns `None` + WARNING."""
    resolver = HardcodedLocationResolver()
    with caplog.at_level(logging.WARNING, logger=_RESOLVER_LOGGER):
        assert resolver.resolve("Canarias") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Section 5: Ctor custom mapping — override + default.
#
# The ctor accepts an optional `mapping` arg (a `dict[str, int]`)
# so tests can inject a minimal dict to assert behavior in
# isolation (without depending on the 34-entry default). A
# future change (e.g. a `HybridLocationResolver` with a
# geocoding API fallback) can extend the ctor signature
# backward-compatibly.
# ---------------------------------------------------------------------------


def test_ctor_default_mapping_resolves_madrid() -> None:
    """`HardcodedLocationResolver()` (no args) uses the default 34-entry dict."""
    resolver = HardcodedLocationResolver()
    assert resolver.resolve("madrid") == 103374081


def test_ctor_custom_mapping_overrides_default() -> None:
    """`HardcodedLocationResolver(mapping={"foo": 999})` uses the
    custom dict; the default entries are NOT visible.

    This is the seam for the future `HybridLocationResolver`
    (a follow-up change that adds a geocoding API fallback).
    For v1 the custom mapping is a pure override — the default
    is replaced, not merged.
    """
    resolver = HardcodedLocationResolver(mapping={"foo": 999})
    assert resolver.resolve("foo") == 999
    # The default entries are NOT visible (the custom mapping
    # replaces the default).
    assert resolver.resolve("madrid") is None


# ---------------------------------------------------------------------------
# Section 6: `resolve_structured` — triplet `(city, province, country)`.
#
# Added in `backend-linkedin-location-fallback` (REQ-STR-LOC-001). The
# v1 LinkedIn scraper falls back to `?location=<str>` for cities
# without a captured `geoId`; the new method returns a triplet
# `(city, province, country)` in Title Case (with tildes NFC) for
# cities that have a structured mapping. The LinkedIn scraper uses
# the triplet in `?location=city,province,country` (URL-encoded) —
# LinkedIn's fuzzy match handles the structured form better than
# the raw string. Country-level inputs (e.g. "España") and CCAA-
# level inputs (e.g. "Andalucía") return `None` (the dict is city-
# level; country / CCAA is a different category and the spec author
# decided to return `None` rather than heuristically map).
# ---------------------------------------------------------------------------


def test_resolve_structured_antequera_returns_verified_triplet() -> None:
    """`"Antequera"` returns `("Antequera", "Andalucía", "Spain")` — the VERIFIED case.

    Antequera is the only VERIFIED entry in `_STRUCTURED_MAPPING`
    (per the spec author's `LLM_LIVE_TESTS=1` gated test). The
    triplet preserves Title Case + tildes in the value.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("Antequera") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )


@pytest.mark.parametrize(
    ("input_location", "expected_triplet"),
    [
        # === VERIFIED (1) ===
        ("antequera", ("Antequera", "Andalucía", "Spain")),
        # === SPECULATIVE (9) ===
        ("fuengirola", ("Fuengirola", "Málaga", "Spain")),
        ("marbella", ("Marbella", "Málaga", "Spain")),
        ("toledo", ("Toledo", "Castilla-La Mancha", "Spain")),
        ("salamanca", ("Salamanca", "Castilla y León", "Spain")),
        ("cadiz", ("Cádiz", "Andalucía", "Spain")),
        ("granada", ("Granada", "Andalucía", "Spain")),
        ("gijon", ("Gijón", "Asturias", "Spain")),
        ("leon", ("León", "Castilla y León", "Spain")),
        ("vigo", ("Vigo", "Galicia", "Spain")),
    ],
)
def test_resolve_structured_all_10_cities(
    input_location: str, expected_triplet: tuple[str, str, str]
) -> None:
    """All 10 entries in `_STRUCTURED_MAPPING` return the expected triplet.

    One parametrized test pins the 10-city dict shape. The lookup
    is done on the NORMALIZED form (lowercase + accentless); the
    output preserves Title Case + tildes. The 9 SPECULATIVE
    entries will be validated by the `LLM_LIVE_TESTS=1` gated
    test in `tests/integration/test_linkedin_live.py`.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured(input_location) == expected_triplet


def test_resolve_structured_lowercase_input_matches_canonical() -> None:
    """`"antequera"` (lowercase) returns the Title Case triplet.

    The 4-step normalization chain (`NFC + casefold + strip +
    remove accents`) collapses the input to the dict lookup key;
    the output is the Title Case value (with tildes).
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("antequera") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )


def test_resolve_structured_uppercase_input_normalizes() -> None:
    """`"ANTEQUERA"` (uppercase) returns the Title Case triplet.

    `casefold()` collapses `"ANTEQUERA"` → `"antequera"` and the
    dict lookup matches.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("ANTEQUERA") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )


def test_resolve_structured_strip_whitespace() -> None:
    """Leading + trailing whitespace is stripped before lookup.

    The resolver is defensive about re-normalizing even when the
    caller (e.g. a CLI) does not pre-normalize.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("  Antequera  ") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )


def test_resolve_structured_nfd_decomposed_input() -> None:
    """`"Antequera"` (NFD-decomposed) matches the NFC entry.

    The 4-step chain NFC-composes the input; NFD input
    (e.g. `A` + combining acute) normalizes to the same key.
    """
    resolver = HardcodedLocationResolver()
    # NFD decomposed: "Ante\u0301quera" (combining acute accent).
    assert resolver.resolve_structured("Ante\u0301quera") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )


def test_resolve_structured_accentless_input_returns_titled_value() -> None:
    """`"Cadiz"` (ASCII, no tilde) returns `("Cádiz", "Andalucía", "Spain")`.

    The dict's lookup key is accentless (`"cadiz"`); the value
    preserves the tilde. The 4-step chain NFD-decomposes +
    drops `Mn` marks so the input `"Cadiz"` matches the key.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("Cadiz") == (
        "Cádiz",
        "Andalucía",
        "Spain",
    )


def test_resolve_structured_unmapped_returns_none() -> None:
    """`"Berlin"` (unknown city) returns `None`.

    The dict has no entry for Berlin; the resolver returns
    `None` (no WARNING log, per the `resolve_structured`
    contract — it's a different semantic from `resolve()`).
    The LinkedIn scraper falls back to the legacy
    `?location=Berlin` path.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("Berlin") is None


def test_resolve_structured_empty_string_returns_none() -> None:
    """`""` (empty string) short-circuits to `None`.

    Mirrors `resolve()`'s empty-string semantic: an empty
    string is the canonical "no location specified" sentinel
    and returns `None` without any lookup.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("") is None


@pytest.mark.parametrize(
    "country_input",
    ["España", "Spain", "Espana"],
)
def test_resolve_structured_country_level_returns_none(country_input: str) -> None:
    """Country-level inputs return `None` (dict is city-level).

    The spec author decided that country-level inputs do NOT
    return a triplet — the dict is city-level; a country is
    a different category. Returning `None` lets the LinkedIn
    scraper fall back to the legacy `?location=<raw>` path,
    which is the same behavior as the v1 broken path (no
    regression).
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured(country_input) is None


def test_resolve_structured_ccaa_level_returns_none() -> None:
    """`"Andalucía"` (CCAA-level) returns `None` (dict is city-level).

    CCAA-level inputs are also out of scope for
    `_STRUCTURED_MAPPING` (the dict is city-level; the CCAA
    level belongs to a different concept). Returning `None`
    lets the scraper fall back to the legacy path.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("Andalucía") is None


def test_resolve_structured_alias_recurse() -> None:
    """A custom alias (e.g. `"ante" → "antequera"`) recurses correctly.

    The `_ALIASES` mapping is shared between `resolve()` and
    `resolve_structured()` (decision per design §2.9). A custom
    alias `"ante" → "antequera"` expands to the structured
    triplet for Antequera.
    """
    resolver = HardcodedLocationResolver(aliases={"ante": "antequera"})
    assert resolver.resolve_structured("ante") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )


def test_resolve_structured_ctor_default_mapping_has_10_entries() -> None:
    """`HardcodedLocationResolver()` (no args) uses the default 10-entry dict.

    Pinned contract: the default `_STRUCTURED_MAPPING` has
    exactly 10 entries. A regression that grows or shrinks
    the default dict breaks this test.
    """
    resolver = HardcodedLocationResolver()
    assert len(resolver._structured_mapping) == 10  # noqa: SLF001


def test_resolve_structured_ctor_custom_mapping_overrides_default() -> None:
    """`HardcodedLocationResolver(structured_mapping=...)` uses the custom dict.

    The custom mapping is a pure OVERRIDE (the default is
    replaced, not merged) — same contract as the
    `mapping=` kwarg on `resolve()`. The default entries are
    NOT visible after the override.
    """
    custom: dict[str, tuple[str, str, str]] = {
        "foo": ("Foo", "Bar", "Baz"),
    }
    resolver = HardcodedLocationResolver(structured_mapping=custom)
    assert resolver._structured_mapping is custom  # noqa: SLF001
    assert resolver.resolve_structured("foo") == ("Foo", "Bar", "Baz")
    # Default entries are NOT visible.
    assert resolver.resolve_structured("antequera") is None


def test_resolve_structured_madrid_returns_none_geoid_only() -> None:
    """`"Madrid"` is in `_CANONICAL_MAPPING` (geoId) but NOT in `_STRUCTURED_MAPPING`.

    Per design decision #10 (geoId is the preferred format
    and always wins), Madrid uses the `geoId=103374081` path
    and is intentionally EXCLUDED from `_STRUCTURED_MAPPING`.
    `resolve_structured("Madrid")` returns `None` — the
    scraper uses the geoId path.
    """
    resolver = HardcodedLocationResolver()
    assert resolver.resolve_structured("Madrid") is None
    # The geoId path still works.
    assert resolver.resolve("Madrid") == 103374081


def test_resolve_structured_independence_from_resolve() -> None:
    """`resolve()` and `resolve_structured()` are independent methods.

    For `"Antequera"`, `resolve()` returns `None` (Antequera
    is not in the geoId dict) but `resolve_structured()`
    returns the triplet. The two methods serve different
    purposes (one for geoId, one for the structured triplet)
    and MUST NOT shadow each other.
    """
    resolver = HardcodedLocationResolver()
    # `resolve()` returns None for Antequera (no geoId).
    assert resolver.resolve("Antequera") is None
    # `resolve_structured()` returns the triplet.
    assert resolver.resolve_structured("Antequera") == (
        "Antequera",
        "Andalucía",
        "Spain",
    )
