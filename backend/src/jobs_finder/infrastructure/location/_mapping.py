"""Canonical geoId mapping (the 35 entries the resolver indexes into).

Sourced from `tests/fixtures/linkedin_geo_ids.csv` rows 2-44
(the 43 captured geoIds from the 2026-06-08 capture). The 8
country-level / unverified rows are EXCLUDED from this dict
so the resolver returns `None` for them (with a WARNING log):

    - row 13: `pais_vasco` → País Vasco (capture could not pin)
    - row 18: `canarias` → Canarias (capture could not pin)
    - row 32: `mx` → México (same reason)
    - row 35: `ar` → Argentina (region-level; ambiguous)
    - row 38: `co` → Colombia (region-level; ambiguous)
    - row 40: `cl` → Chile (region-level; ambiguous)
    - row 42: `pe` → Perú (worldwide fallback)
    - row 14: `aragon` → Aragón (CSV has it pinned to Zaragoza's
      geoId `106356396`; we exclude it because the canonical
      entry is the city, not the region — the dict below already
      contains `zaragoza` → 106356396).

NOTE: Spain country-level (`es` → geoId 103644278) IS included
(row 28) because the scheduler use case requires scraping all
of Spain, not just a specific city.

The dict keys are the NORMALIZED form (lowercased, accents
stripped, NFC composed). The 35 keys correspond to:
    - 8 Spanish cities (rows 2-9)
    - 16 Spanish autonomous communities (rows 10-12, 15-17,
      19-28, plus the `murcia` city which doubles as the
      region-level entry — see CSV row 21 `murcia_region` which
      is intentionally merged into the same `murcia` key
      because the city IS the region for the purposes of
      LinkedIn's geoId)
    - 9 LATAM cities (rows 30-31, 33, 34, 37, 40, 41, 43)
    - 1 remote entry (row 44, post CSV-quoting-fix)
    - 1 country-level entry (row 28: Spain)
"""

from __future__ import annotations

# The canonical mapping. Each value is the LinkedIn geoId
# captured on 2026-06-08. Add new cities here; the test suite
# pins the values via `test_canonical_lookup_returns_csv_pinned_geo_id`.
_CANONICAL_MAPPING: dict[str, int] = {
    # === Spanish cities (8) ===
    "madrid": 103374081,
    "barcelona": 105088894,
    "valencia": 105512687,
    "sevilla": 104893466,
    "zaragoza": 106356396,
    "malaga": 104401670,
    "murcia": 102253611,
    "bilbao": 101962740,
    # === Spanish autonomous communities (16) ===
    "comunidad de madrid": 103335767,
    "cataluna": 105646813,
    "comunidad valenciana": 100076887,
    "andalucia": 106151489,
    "galicia": 103189018,
    "castilla y leon": 104802667,
    "castilla la mancha": 100096545,
    "extremadura": 102727695,
    "asturias": 104351060,
    "cantabria": 106413664,
    "la rioja": 102952772,
    "navarra": 102688677,
    "illes balears": 101388828,
    "ceuta": 100110826,
    "melilla": 101887739,
    "region de murcia": 106901295,
    # === LATAM cities (9) ===
    "ciudad de mexico": 112558473,
    "guadalajara": 100870198,
    "monterrey": 104201579,
    "buenos aires": 90009870,
    "cordoba": 102399085,  # AR (the ES Córdoba shares the name; AR wins per CSV row 35)
    "bogota": 102361989,
    "medellin": 112085362,
    "santiago": 104555257,
    "lima": 101312395,
    # === Remote (1) ===
    "remote": 118424786,
    # === Country-level (1) ===
    # Spain country-level geoId. Previously excluded (worldwide fallback
    # returns globally-distributed results), but for the scheduler's
    # "scrape all Spain" use case this is the correct geoId.
    "espana": 103644278,
}

# Aliases: map alternate / abbreviated spellings to canonical keys.
# Each value is a key in `_CANONICAL_MAPPING` (the resolver
# re-normalizes the value before lookup). Add new aliases here.
_ALIASES: dict[str, str] = {
    # Common abbreviations
    "mad": "madrid",
    "bcn": "barcelona",
    "cdmx": "ciudad de mexico",
    "caba": "buenos aires",  # Ciudad Autónoma de Buenos Aires
    "df": "ciudad de mexico",  # Ciudad de México (old abbreviation)
    # Country-level aliases for Spain
    "spain": "espana",
    "es": "espana",
}
