"""LinkedIn-specific infrastructure: hardcoded location resolver.

Depends on `application/ports` and `domain/`. Must not import
`presentation/`.

The `HardcodedLocationResolver` is the v1 implementation of the
`LocationResolverPort` Protocol. It translates a free-form
`intent.location` string (e.g. `"Madrid"`, `"Cataluña"`, `"cdmx"`)
into a numeric LinkedIn `geoId` (e.g. `103374081`) that the
LinkedIn scraper can use in the `?geoId=<id>` URL parameter.

The 34-entry canonical dict is derived from
`tests/fixtures/linkedin_geo_ids.csv` rows 2-44 (43 captured
geoIds minus 9 country-level / unverified rows that intentionally
return `None`; see `_CANONICAL_MAPPING` below).

The alias normalization chain is:
    1. `unicodedata.normalize("NFC", s).casefold().strip()`
       (NFC normalizes composed/decomposed Unicode; `casefold`
       handles "MADRID" and "madrid" identically; `strip` handles
       leading/trailing whitespace).
    2. NFD-decompose + drop `Mn` (combining accent) marks
       (handles `"México"` / `"Mexico"` / `"MEXICO"` identically).
    3. Alias-to-canonical recurse via `_ALIASES` (e.g. `cdmx` →
       `ciudad de mexico` → `112558473`).
    4. Flat dict lookup in `_CANONICAL_MAPPING`.
    5. Returns `None` + WARNING log on unknown / country-level /
       País Vasco / Canarias / empty inputs.
"""
