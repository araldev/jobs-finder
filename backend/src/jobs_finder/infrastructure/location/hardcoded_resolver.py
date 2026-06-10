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

    The ctor accepts an optional `mapping` kwarg so tests can
    inject a minimal dict (and a future `HybridLocationResolver`
    can compose this class with a geocoding API fallback). The
    default mapping is the 34-entry `_CANONICAL_MAPPING` from
    `_mapping.py`; passing a custom `mapping` REPLACES the
    default (does NOT merge).
    """

    def __init__(
        self,
        *,
        mapping: Mapping[str, int] | None = None,
        aliases: Mapping[str, str] | None = None,
        structured_mapping: Mapping[str, tuple[str, str, str]] | None = None,
    ) -> None:
        """Build a resolver over the given `mapping` (default: 34-entry dict).

        Args:
            mapping: The canonical mapping (NORMALIZED form →
                geoId). When `None` (the default), the 34-entry
                `_CANONICAL_MAPPING` is used. The custom mapping
                REPLACES the default (does NOT merge).
            aliases: The alias mapping (NORMALIZED form →
                canonical key). When `None` (the default), the
                5-entry `_ALIASES` is used.
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
