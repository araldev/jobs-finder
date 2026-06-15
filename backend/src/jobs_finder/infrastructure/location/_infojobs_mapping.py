"""InfoJobs province/country mapping (the 9-entry dict the InfoJobs resolver indexes into).

Spec: REQ-PROV-001 (the 12 scenarios in the spec).

The InfoJobs scraper consumes a `(province_id, country_id)` tuple
from the `LocationResolverPort.resolve_infojobs()` method. The
mapping is independent of `_mapping.py` (the LinkedIn geoId
dict) because the two ID namespaces have distinct sources of
truth:

    - LinkedIn geoId: captured on 2026-06-08 against
      `linkedin.com/jobs/search` (the `linkedin_geo_ids.csv`
      fixture); a CSV-derived int.

    - InfoJobs provinceId: not a CSV capture; the canonical
      Málaga=34 was confirmed by a user-captured URL during
      manual smoke testing of `backend-scraper-query-tuning`
      (PR #4, merged 2026-06-10). The España country=17 is
      pinned from the same URL. The other 4 cities (Madrid,
      Barcelona, Valencia, Sevilla) are pinned to the
      official INE codes for the Spanish provinces; they are
      marked as SPECULATIVE pending LIVE test validation
      (`LLM_LIVE_TESTS=1`).

Both halves of the tuple are required (the `country_id` is
non-`None` for every entry). A `(None, 17)` tuple means
"country-only, no province" — the canonical sentinel for the
"Remote" / "España" / "Spain" / "teletrabajo" cases. The
InfoJobs URL builder omits `provinceIds` when `province_id is
None` (so `(None, 17)` becomes `?countryIds=17` only — see
`InfoJobsPlaywrightScraper._build_url()`).

The dict keys are the NORMALIZED form (lowercased, accents
stripped, NFC composed) — the same 4-step normalization chain
as the LinkedIn resolver (`HardcodedLocationResolver._normalize`).
The 9 keys correspond to:

    - 5 user-verified entries: malaga (province 34), espana
      (country-only), spain (country-only), remote
      (country-only), teletrabajo (country-only).
    - 4 speculative entries:   madrid (28), barcelona (8),
      valencia (46), sevilla (41).

Speculative IDs:
    - "We have not captured the provinceIds for Madrid,
      Barcelona, Valencia, Sevilla against the real InfoJobs
      SERP. The IDs 28, 8, 46, 41 are the official INE
      codes; InfoJobs may use a different internal namespace.
      A wrong ID causes the scraper to fall back to the
      v1 `?l=<str>` path (graceful degradation, no 500).
      The LIVE test gated by `LLM_LIVE_TESTS=1` validates
      each ID; a failing ID is removed from this dict (a
      1-line change) and the scraper transparently degrades."
"""

from __future__ import annotations

# The canonical mapping. Each value is `(province_id, country_id)`.
# The first 5 entries are USER-VERIFIED (no comment); the next 4
# entries are SPECULATIVE (the trailing `# speculative` comment
# marks them as such). The `test_resolve_infojobs_default_mapping_has_nine_entries`
# test pins the count to 9 — adding/removing an entry without
# updating the test is a silent spec drift.
_INFOJOBS_MAPPING: dict[str, tuple[int | None, int]] = {
    # === Spanish provinces (province_id, country_id=17) — USER-VERIFIED ===
    "malaga": (34, 17),
    # === Country-only (province_id=None, country_id=17) — USER-VERIFIED ===
    "espana": (None, 17),  # España → country=Spain, no province
    "spain": (None, 17),  # English synonym
    "remote": (None, 17),  # "Remote" → country=Spain, no province
    "teletrabajo": (None, 17),  # Spanish synonym for "remote"
    # === Spanish provinces (province_id, country_id=17) — LIVE-TESTED ===
    "madrid": (33, 17),   # LIVE-tested (2026-06-15)
    "barcelona": (9, 17), # LIVE-tested (2026-06-15)
    "valencia": (46, 17),  # speculative — INE code; not validated
    "sevilla": (41, 17),  # speculative — INE code; not validated
}
