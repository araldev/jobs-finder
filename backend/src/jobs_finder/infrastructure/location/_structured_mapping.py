"""Structured location mapping (the 10-entry triplet lookup the resolver indexes into).

Spec: `backend-linkedin-location-fallback` REQ-STR-LOC-001.

This module is the structured-location counterpart to
`_mapping.py`. The v1 `HardcodedLocationResolver` translates a
free-form `intent.location` string into a LinkedIn `geoId`
(via `_CANONICAL_MAPPING`); for cities NOT in that dict, the
LinkedIn scraper falls back to `?location=<raw_str>`, which
LinkedIn silently ignores. The user captured a real LinkedIn
URL showing a third supported format:
`?location=<city>,<province>,<country>`. LinkedIn's fuzzy
match handles the structured form better than the raw string.

This dict provides the triplet `(city, province, country)` in
Title Case with tildes (NFC) for 10 Spanish cities that the
v1 dict does not have a `geoId` for. Of the 10:

    - 1 VERIFIED: antequera → the LIVE test gated
      `LLM_LIVE_TESTS=1` confirms `?location=Antequera,
      Andalucía, Spain` returns real Antequera / Málaga /
      Andalucía jobs.
    - 9 SPECULATIVE: province + country were inferred from
      the city's well-known province + Spain as the country.
      The same LIVE test will validate (or invalidate) these
      in a follow-up change. A failed entry is a 1-line
      removal from this dict — the resolver returns `None` for
      misses and the scraper falls back to the legacy path.

The dict keys are the NORMALIZED form (lowercased, accents
stripped, NFC composed) — same convention as
`_CANONICAL_MAPPING`. The values are Title Case with tildes
preserved (NFC) — the canonical display form.
"""

from __future__ import annotations

# The structured mapping. Each value is a 3-tuple
# `(city, province, country)` in Title Case with tildes (NFC).
# Add new cities here; the test suite pins the values via
# `test_resolve_structured_all_10_cities`.
_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]] = {
    # === VERIFIED (1) ===
    # The user captured `?location=Antequera,Andalucía,Spain` and the
    # LIVE test (gated `LLM_LIVE_TESTS=1`) confirms the URL returns
    # real Antequera / Málaga / Andalucía jobs. See
    # `tests/integration/test_linkedin_live.py` for the live probe.
    "antequera": ("Antequera", "Andalucía", "Spain"),  # VERIFIED
    # === SPECULATIVE (9) ===
    # Province + country inferred from the city's well-known province
    # + Spain. Pending LIVE test validation.
    "fuengirola": ("Fuengirola", "Málaga", "Spain"),  # SPECULATIVE
    "marbella": ("Marbella", "Málaga", "Spain"),  # SPECULATIVE
    "toledo": ("Toledo", "Castilla-La Mancha", "Spain"),  # SPECULATIVE
    "salamanca": ("Salamanca", "Castilla y León", "Spain"),  # SPECULATIVE
    "cadiz": ("Cádiz", "Andalucía", "Spain"),  # SPECULATIVE
    "granada": ("Granada", "Andalucía", "Spain"),  # SPECULATIVE
    "gijon": ("Gijón", "Asturias", "Spain"),  # SPECULATIVE
    "leon": ("León", "Castilla y León", "Spain"),  # SPECULATIVE
    "vigo": ("Vigo", "Galicia", "Spain"),  # SPECULATIVE
}
