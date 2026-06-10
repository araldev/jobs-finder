"""`HardcodedLocationResolver` — the v1 implementation of `LocationResolverPort`.

Spec: REQ-LOC-GEO-001.

The resolver translates a free-form `intent.location` string (e.g.
`"Madrid"`, `"Cataluña"`, `"cdmx"`) into a numeric LinkedIn
`geoId` (e.g. `103374081`). The previous (broken) behavior was
to pass the string verbatim as `?location=Madrid` — which
LinkedIn's public search silently ignores.

The alias normalization chain is:
    1. `unicodedata.normalize("NFC", s).casefold().strip()`
    2. NFD-decompose + drop `Mn` (combining accent) marks
    3. Alias-to-canonical recurse via `_ALIASES`
    4. Flat dict lookup in `_CANONICAL_MAPPING`
    5. Returns `None` + WARNING log on unknown / country-level /
       País Vasco / Canarias / empty inputs.

The ctor accepts an optional `mapping` kwarg (defaulting to the
34-entry `_CANONICAL_MAPPING`) so tests can inject a minimal
dict. The custom mapping is a pure OVERRIDE (the default is
replaced, not merged) — this is the seam for the future
`HybridLocationResolver` (a follow-up change that adds a
geocoding API fallback).
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Mapping

from jobs_finder.application.ports import LocationResolverPort

from ._infojobs_mapping import _INFOJOBS_MAPPING
from ._mapping import _ALIASES, _CANONICAL_MAPPING
from ._structured_mapping import _STRUCTURED_MAPPING

_logger = logging.getLogger(__name__)


class HardcodedLocationResolver(LocationResolverPort):
    """In-process dict-based location resolver. The v1 implementation.

    The class is the implementation of the structural
    `LocationResolverPort` Protocol (mypy --strict enforces the
    conformance at type-check time). The Protocol is NOT
    `@runtime_checkable`; this is the same pattern used by
    `JobSearchPort`, `LLMClientPort`, `IntentExtractorPort`, etc.

    The class implements TWO methods on the Protocol:
        - `resolve(location) -> int | None`: the v1 LinkedIn
          path. Returns the LinkedIn geoId for a free-form
          `location` string.
        - `resolve_infojobs(location) -> tuple[int | None, int | None]`:
          the v1 InfoJobs path. Returns a `(province_id,
          country_id)` tuple that the InfoJobs scraper
          consumes to build `?provinceIds=<id>&countryIds=<id>`
          query params.

    The two methods read from INDEPENDENT dicts
    (`_CANONICAL_MAPPING` for LinkedIn; `_INFOJOBS_MAPPING` for
    InfoJobs) because the two ID namespaces have distinct
    sources of truth. The composition root wires ONE
    `HardcodedLocationResolver` instance into BOTH
    `LinkedInScraperSettings` and `InfoJobsScraperSettings`
    (per the `app_factory.build_app()` wire-up).

    The ctor accepts an optional `mapping` kwarg (LinkedIn) and
    an optional `infojobs_mapping` kwarg (InfoJobs) so tests
    can inject minimal dicts. The default mappings are the
    34-entry `_CANONICAL_MAPPING` (LinkedIn) and the 9-entry
    `_INFOJOBS_MAPPING` (InfoJobs). Passing a custom mapping
    REPLACES the default (does NOT merge).
    """

    def __init__(
        self,
        *,
        mapping: Mapping[str, int] | None = None,
        aliases: Mapping[str, str] | None = None,
        infojobs_mapping: Mapping[str, tuple[int | None, int]] | None = None,
        structured_mapping: Mapping[str, tuple[str, str, str]] | None = None,
    ) -> None:
        """Build a resolver over the given `mapping` (default: 34-entry dict).

        Args:
            mapping: The canonical LinkedIn mapping (NORMALIZED
                form → geoId). When `None` (the default), the
                34-entry `_CANONICAL_MAPPING` is used. The
                custom mapping REPLACES the default (does NOT
                merge).
            aliases: The alias mapping (NORMALIZED form →
                canonical key). When `None` (the default), the
                5-entry `_ALIASES` is used.
            infojobs_mapping: The canonical InfoJobs mapping
                (NORMALIZED form → `(province_id, country_id)`).
                When `None` (the default), the 9-entry
                `_INFOJOBS_MAPPING` is used. The custom mapping
                REPLACES the default (does NOT merge) — same
                override semantics as `mapping`. Added in
                `backend-infojobs-provinces` (REQ-PROV-001).
            structured_mapping: The structured triplet mapping
                (NORMALIZED form → `(city, province, country)`
                tuple in Title Case with tildes NFC). When
                `None` (the default), the 10-entry
                `_STRUCTURED_MAPPING` is used. Added in
                `backend-linkedin-location-fallback`
                (REQ-STR-LOC-001). The custom mapping
                REPLACES the default (does NOT merge).
        """
        self._mapping: Mapping[str, int] = mapping if mapping is not None else _CANONICAL_MAPPING
        self._aliases: Mapping[str, str] = aliases if aliases is not None else _ALIASES
        self._infojobs_mapping: Mapping[str, tuple[int | None, int]] = (
            infojobs_mapping if infojobs_mapping is not None else _INFOJOBS_MAPPING
        )
        self._structured_mapping: Mapping[str, tuple[str, str, str]] = (
            structured_mapping if structured_mapping is not None else _STRUCTURED_MAPPING
        )

    def resolve(self, location: str) -> int | None:
        """Translate `location` (a free-form string) into a LinkedIn `geoId`.

        The alias normalization chain:
            1. `unicodedata.normalize("NFC", s).casefold().strip()`
            2. NFD-decompose + drop `Mn` (combining accent) marks
            3. Alias-to-canonical recurse via `_ALIASES`
            4. Flat dict lookup in `_CANONICAL_MAPPING`
            5. Returns `None` + WARNING log on miss.

        Args:
            location: The free-form location string (e.g.
                `"Madrid"`, `"Cataluña"`, `"cdmx"`). May be
                empty (the v1 chat-filter path passes
                `location=""`); an empty string short-circuits
                to `None` WITHOUT a warning (the canonical
                "no location specified" sentinel).

        Returns:
            The LinkedIn `geoId` (a `int`) on a successful
            match, OR `None` on a miss (unknown / country-
            level / País Vasco / Canarias / empty). A WARNING
            is logged on every miss except the empty-string
            path.
        """
        # Short-circuit: empty string is the canonical "no
        # location" sentinel. We do NOT log a WARNING here —
        # an empty string is a legitimate input (the v1 path
        # passes `""` to the aggregator), not an "unknown
        # location" signal.
        if not location:
            return None

        normalized = self._normalize(location)

        # Alias-to-canonical recurse (1 step — aliases point
        # directly to a canonical key, NOT to another alias).
        # Mirrors `linkedin_geo_ids.md` §"Resolution strategy":
        # "The fallback chain is **flat** (no transitive
        # aliasing) for simplicity."
        canonical_key = self._aliases.get(normalized, normalized)

        if canonical_key in self._mapping:
            return self._mapping[canonical_key]

        # Unknown / country-level / País Vasco / Canarias.
        # Log a WARNING with the input string so ops can spot
        # stale geographic intent and re-run the capture script.
        _logger.warning(
            "HardcodedLocationResolver: could not resolve location %r to a LinkedIn geoId. "
            "Falling back to ?location=<str> (broken but does not 500).",
            location,
        )
        return None

    def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
        """Translate `location` (a free-form string) into an InfoJobs `(province_id, country_id)`.

        The alias normalization chain is the same 4-step
        chain that `resolve()` uses (NFC + casefold + strip +
        NFD-drop Mn). The dict is the 9-entry
        `_INFOJOBS_MAPPING` from `_infojobs_mapping.py`.

        Args:
            location: The free-form location string (e.g.
                `"Málaga"`, `"Madrid"`, `"Remote"`,
                `"teletrabajo"`). May be empty (the
                aggregator passes `""`); an empty string
                short-circuits to `(None, None)` WITHOUT
                a warning log (the canonical "no location
                specified" sentinel).

        Returns:
            A `(province_id, country_id)` tuple. The
            `(None, None)` sentinel means "unmapped" —
            the InfoJobs scraper then falls back to the
            v1 `?l=<str>` path. The 4 documented cases
            (`(int, int)`, `(None, int)`, `(int, None)`,
            `(None, None)`) are all returned by this
            method; the v1 dict only ever populates the
            first two. A WARNING is logged on every
            `(None, None)` miss EXCEPT the empty-string
            path (same convention as `resolve()`).
        """
        # Short-circuit: empty string is the canonical
        # "no location" sentinel (same as `resolve()`).
        # We do NOT log a WARNING here — an empty string
        # is a legitimate input, not an "unknown city"
        # signal.
        if not location:
            return (None, None)

        normalized = self._normalize(location)

        if normalized in self._infojobs_mapping:
            return self._infojobs_mapping[normalized]

        # Unknown / unmapped city. Log a WARNING with
        # the input string so ops can spot stale
        # geographic intent and re-run the capture
        # script (or add a new entry to the dict).
        # The InfoJobs scraper falls back to the v1
        # `?l=<str>` URL formula (graceful degradation,
        # no 500).
        _logger.warning(
            "HardcodedLocationResolver: could not resolve location %r to an InfoJobs "
            "(province_id, country_id). Falling back to ?l=<str> (graceful, no 500).",
            location,
        )
        return (None, None)

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:
        """Translate `location` into a structured `(city, province, country)` triplet.

        Spec: `backend-linkedin-location-fallback`
        REQ-STR-LOC-001. The structured counterpart to
        `resolve()`: for cities with an entry in
        `_STRUCTURED_MAPPING`, return the triplet. For
        everything else (unknown / country-level / CCAA-
        level / empty), return `None`.

        The same 4-step normalization chain as `resolve()`
        is used (NFC + casefold + strip + remove accents).
        The same `_ALIASES` mapping is shared — a custom
        alias like `"ante" → "antequera"` recurses through
        `_structured_mapping` the same way it recurses
        through `_mapping`.

        Country-level inputs (`"España"`, `"Spain"`) and
        CCAA-level inputs (`"Andalucía"`) return `None` — the
        dict is city-level; country / CCAA is a different
        category and the spec author decided to return
        `None` rather than heuristically map. The LinkedIn
        scraper falls back to the legacy `?location=<raw>`
        path (the v1 broken-but-doesn't-500 path).

        Args:
            location: The free-form location string. May be
                empty (the v1 chat-filter path passes
                `location=""`); an empty string short-circuits
                to `None` (the canonical "no location specified"
                sentinel — same as `resolve()`).

        Returns:
            A 3-tuple `(city, province, country)` in Title
            Case with tildes (NFC) on a successful match, OR
            `None` on a miss. No WARNING log is emitted
            (different semantic from `resolve()`: the
            structured path is an OPT-IN alternative URL
            shape, not a fallback for the geoId path).
        """
        # Short-circuit: empty string is the canonical "no
        # location" sentinel. Same semantic as `resolve()` —
        # no log, just a quick return.
        if not location:
            return None

        normalized = self._normalize(location)

        # Alias-to-canonical recurse (1 step — aliases point
        # directly to a canonical key, NOT to another alias).
        # Same contract as `resolve()`.
        canonical_key = self._aliases.get(normalized, normalized)

        # Direct dict lookup; miss returns `None` (no log).
        # The dict is city-level; country / CCAA inputs are
        # intentionally NOT in the dict per the spec author's
        # decision — they return `None` and the scraper falls
        # back to the legacy `?location=<raw>` path.
        return self._structured_mapping.get(canonical_key)

    @staticmethod
    def _normalize(location: str) -> str:
        """Normalize the input: NFC + casefold + strip + remove accents.

        The 4-step chain handles the 4 normalization invariants
        pinned by the spec:
            - NFC normalizes composed/decomposed Unicode
              (`"Málaga"` vs `"Málaga"`).
            - `casefold` handles `"MADRID"` and `"madrid"`
              identically.
            - `strip` handles leading/trailing whitespace.
            - NFD-decompose + drop `Mn` (combining accent)
              marks handles `"México"` / `"Mexico"` /
              `"MEXICO"` identically.
        """
        # Step 1: NFC + casefold + strip.
        step1 = unicodedata.normalize("NFC", location).casefold().strip()
        # Step 2: NFD-decompose + drop combining marks.
        nfd = unicodedata.normalize("NFD", step1)
        return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
