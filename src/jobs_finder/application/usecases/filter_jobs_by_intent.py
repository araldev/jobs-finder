"""Chat-filter use case (T-013 of `ai-chat-filter`, refactored in T-008 of `chat-filter-2stage`).

Spec: REQ-LLM-003 (strict-subset ID validation), REQ-CHAT-001
(orchestration), REQ-CHAT-INT-001..005 (2-stage flow control).

`FilterJobsByIntentUseCase` is the 3-stage chat-filter orchestrator
with the 2-stage LLM flow:

  Stage 1 (NEW in `chat-filter-2stage`): the use case calls
    `intent_extractor.extract(message=...)` to extract a
    structured `Intent` (q, location, experience_years, remote,
    employment_type, confidence, notes). The use case then
    reads `intent.confidence`:
      - High confidence (>= `intent_extraction_confidence_threshold`):
        dispatch to `_execute_2stage(...)` — stage 2 uses the
        extracted `q` / `location` for a directed aggregator
        scrape with `limit=intent_max_results` (per-source cap
        higher than the v1 `limit=20`); stage 3 is the same
        v1 LLM filter. `used_fallback=False`.
      - Low confidence (< threshold): dispatch to
        `_execute_v1(...)` — the v1 single-stage flow
        (aggregator with `q=""`, `location=""`, `limit=20`,
        then stage-3 LLM filter). `used_fallback=True`.
      - Stage-1 LLMResponseParseError (after retry exhaustion):
        the use case catches it and dispatches to
        `_execute_v1(...)` with `used_fallback=True`
        (REQ-CHAT-INT-004).

  Stage 2 (NEW): directed aggregator scrape using the
    extracted `q` / `location` and `limit=intent_max_results`.
    Reuses the existing `SearchAllSourcesUseCase` aggregator
    (per-source cache + per-source error isolation).

  Stage 3 (UNCHANGED from v1): the v1 LLM filter. The use case
    builds the 5-key LLM-facing dict per job, calls the LLM
    with the Spanish `SYSTEM_PROMPT` and a JSON-serialized
    user message, parses the response, validates
    `matching_ids` to a STRICT SUBSET of the input ids, logs a
    WARNING per dropped (hallucinated) id, and returns the
    filtered jobs in the AGGREGATOR'S order (not the LLM's).

Backward compat (REQ-CHAT-INT-005): the v1 single-stage
behavior is preserved when:
  - `intent_extraction_enabled=False` (the master switch)
  - `intent_extractor is None` (composition root bypass)
  - The extracted `Intent.confidence < threshold`
  - Stage-1 parse error (after retry exhaustion)
In all of those cases the use case dispatches to
`_execute_v1(...)` with `used_fallback=True`. The v1 logic is
verbatim — no recursion with `_execute_2stage(...)`, no
shared state.

The use case depends ONLY on the application's
`IntentExtractorPort` and `LLMClientPort` Protocols — never
on the concrete `IntentExtractor` or `MiniMaxLLMClient`. The
composition root (`presentation/app_factory.build_app`)
injects the concrete implementations at construction time
(T-009); tests inject `FakeIntentExtractor` and
`FakeLLMClient` (Protocol-conforming test doubles).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import (
    Intent,
    IntentExtractorPort,
    LLMClientPort,
    LocationResolverPort,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.llm._parser import LLMSelection, parse_llm_response
from jobs_finder.infrastructure.llm._prompt import SYSTEM_PROMPT, build_user_message
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

_logger = logging.getLogger(__name__)


# Spanish short-circuit message. Surfaces to the user when the
# aggregator returns 0 jobs — the LLM is never called in that case
# (REQ-LLM-003 5th scenario). The string is a module-level constant
# (not a kwarg) because the wording is part of the spec's user-
# facing contract and a future change should land with a test
# update, not a config knob.
_EMPTY_RESULT_EXPLANATION = "No se encontraron ofertas que coincidan con tu búsqueda."


@dataclass(frozen=True, slots=True)
class FilteredJobsResult:
    """The structured result of the chat-filter use case.

    Mirrors the `Job` value-object style: `frozen=True, slots=True`.
    The route (T-014) maps this to the `ChatResponse` Pydantic
    schema for the API response.

    Attributes:
        jobs: The filtered `Job` instances, in the aggregator's
            order (NOT the LLM's). Empty when the LLM returned no
            matching ids OR when the aggregator was empty
            (short-circuit). Each `Job` is a fully-formed domain
            value object — the route's `to_response(...)` helper
            converts it to `JobResponse` for the API.
        explanation: The Spanish explanation from the LLM
            (always present, even when the list is empty —
            REQ-LLM-004 invariant). For the short-circuit path,
            this is the `"no se encontraron ofertas"` constant.
        total_considered: `len(aggregator.jobs)` — the number of
            jobs the LLM saw. Used by the route / caller to compute
            "X of Y matched".
        total_matched: `len(filtered)` — the number of jobs in
            `self.jobs`. Equals `len(aggregator.jobs)` minus the
            number of dropped ids.
        used_fallback: `True` when the v1 single-stage path ran
            (low confidence, stage-1 parse failure,
            `intent_extraction_enabled=False`, or no
            `intent_extractor` injected). `False` when the
            2-stage path ran. The route serializes this in
            the `ChatResponse` so the client can tell which
            path served the request (REQ-CHAT-INT-004). Default
            `True` is the safe default: a use case constructed
            with the v1-only kwargs (no `intent_extractor`) is
            semantically the v1 behavior.
    """

    jobs: Sequence[Job]
    explanation: str
    total_considered: int
    total_matched: int
    used_fallback: bool = True


class FilterJobsByIntentUseCase:
    """Orchestrate the 3-stage chat-filter flow with the 2-stage LLM option.

    The constructor is keyword-only to make the call site read
    like a spec:
      `FilterJobsByIntentUseCase(aggregator=..., llm=..., intent_extractor=...)`

    Args:
        aggregator: The existing `SearchAllSourcesUseCase` instance.
            The chat-filter use case reuses the same per-source
            cache + per-source error isolation as the `/jobs`
            aggregator route, so a chat call within the 60s cache
            window reuses the per-source results (REQ-CHAT-003:
            no separate LLM cache).
        llm: Any `LLMClientPort`. The use case depends on the
            Protocol only; the concrete `MiniMaxLLMClient` is
            injected at composition-root time.
        parser: The defensive parser. Defaults to
            `parse_llm_response` from `infrastructure.llm._parser`.
            The parameter is keyword-only with a default so a
            test can inject a parser that returns a canned
            `LLMSelection`.
        intent_extractor: Optional `IntentExtractorPort`. When
            `None` (the default), the use case runs the v1
            single-stage path (`_execute_v1(...)` with
            `used_fallback=True`). When provided AND
            `intent_extraction_enabled=True`, the use case
            dispatches based on the extracted `Intent.confidence`
            (REQ-CHAT-INT-004). The Protocol is the seam — the
            use case never depends on the concrete
            `IntentExtractor` class.
        intent_extraction_enabled: Master switch for the 2-stage
            flow. Defaults to `True`. Set to `False` to revert
            to v1 behavior (the kill switch — REQ-CHAT-INT-005).
        intent_extraction_confidence_threshold: Below this
            confidence, the use case falls back to v1
            (REQ-CHAT-INT-004). Defaults to `0.7`.
        intent_max_results: Per-source cap for the stage-2
            aggregator scrape. Defaults to `100` (higher than
            the v1 `limit=20` to give the LLM more recall).
            The v1 path always uses `_V1_DEFAULT_LIMIT = 20`
            regardless of this setting.
    """

    def __init__(
        self,
        *,
        aggregator: SearchAllSourcesUseCase,
        llm: LLMClientPort,
        parser: Callable[[str], LLMSelection] = parse_llm_response,
        intent_extractor: IntentExtractorPort | None = None,
        intent_extraction_enabled: bool = True,
        intent_extraction_confidence_threshold: float = 0.7,
        intent_max_results: int = 100,
        location_resolver: LocationResolverPort | None = None,
    ) -> None:
        """..."""
        self._aggregator = aggregator
        self._llm = llm
        self._parser = parser
        self._intent_extractor = intent_extractor
        self._intent_extraction_enabled = intent_extraction_enabled
        self._intent_extraction_confidence_threshold = intent_extraction_confidence_threshold
        self._intent_max_results = intent_max_results
        self._location_resolver = location_resolver

    async def execute(
        self,
        *,
        message: str,
        q: str,
        location: str,
        limit: int,
        sources: Sequence[str] | None = None,
    ) -> FilteredJobsResult:
        """Run the chat-filter flow and return the filtered jobs.

        The public `execute(...)` dispatches between the 2-stage
        path and the v1 path based on the construction-time
        flags:

        1. If `intent_extraction_enabled` is `True` AND
           `intent_extractor is not None`: call
           `intent = await intent_extractor.extract(message=message)`.
           - If the extractor raises `LLMResponseParseError`
             (after retry exhaustion), dispatch to
             `_execute_v1(...)` with `used_fallback=True`
             (REQ-CHAT-INT-004).
           - If `intent.confidence < intent_extraction_confidence_threshold`,
             dispatch to `_execute_v1(...)` with
             `used_fallback=True`.
           - Otherwise, dispatch to
             `_execute_2stage(message, intent, resolved_sources)`
             with `used_fallback=False`.
        2. Otherwise: dispatch to `_execute_v1(...)` with
           `used_fallback=True` (the v1 single-stage path).

        Args:
            message: The user's natural-language intent (e.g.
                "ingeniero < 2 años en Málaga"). Pre-normalized by
                the route (NFC + casefold + strip, per REQ-CHAT-001).
            q: The aggregator's `keywords`. The chat endpoint passes
                `""` in v1 (the message IS the intent); a future
                caller can pre-fill `q` to benefit from the
                aggregator cache. The 2-stage path IGNORES this
                argument in favor of `intent.q`.
            location: The aggregator's `location`. Same v1
                convention as `q`. The 2-stage path IGNORES this
                argument in favor of `intent.location`.
            limit: The aggregator's `limit` (job cap per source).
                The 2-stage path IGNORES this argument in favor of
                `intent_max_results`. The v1 path IGNORES this
                argument in favor of `_V1_DEFAULT_LIMIT = 20` so
                the per-source cache key is byte-identical to
                pre-2-stage behavior.
            sources: The aggregator's `sources` filter. `None`
                means all 3 sources. Forwarded to both paths.

        Returns:
            A `FilteredJobsResult` with the matched jobs in the
            aggregator's order, the LLM's Spanish explanation,
            the `total_considered` / `total_matched` counts, and
            the `used_fallback` flag.

        Raises:
            LLMUnavailableError: on 5xx, timeout, 429, or MiniMax
                error codes 1002/1013 (after retry exhaustion) and
                1004/1008/1001 (no retry). Propagated unchanged.
            LLMResponseParseError: when the stage-3 parser cannot
                extract a JSON object. Propagated unchanged. The
                route maps this to 422.
            JobSearchError: any per-source error from the aggregator
                that is NOT isolated to a single source. Propagated
                unchanged.
        """
        # Resolve `sources` once; both paths consume it.
        if sources is None:
            resolved_sources: list[str] = ["linkedin", "indeed", "infojobs"]
        else:
            resolved_sources = list(sources)

        # Stage 1: extract intent (only when the 2-stage flow is
        # active). The intent's `confidence` drives the dispatch.
        intent: Intent | None = None
        if self._intent_extraction_enabled and self._intent_extractor is not None:
            try:
                intent = await self._intent_extractor.extract(message=message)
            except LLMResponseParseError as e:
                # Stage-1 parse failure after retry exhaustion.
                # Fall back to v1 (REQ-CHAT-INT-004). Log a WARNING
                # so ops can see the fallback in container logs.
                _logger.warning(
                    "Stage-1 intent extraction failed after retry exhaustion: %s. "
                    "Falling back to v1 single-stage path.",
                    e,
                )
                return await self._execute_v1(
                    message=message,
                    q=q,
                    location=location,
                    limit=limit,
                    resolved_sources=resolved_sources,
                    used_fallback=True,
                )

        # Confidence gate: low-confidence intent → v1 fallback.
        if intent is not None and intent.confidence < self._intent_extraction_confidence_threshold:
            _logger.info(
                "Stage-1 intent confidence %.2f below threshold %.2f. "
                "Falling back to v1 single-stage path.",
                intent.confidence,
                self._intent_extraction_confidence_threshold,
            )
            return await self._execute_v1(
                message=message,
                q=q,
                location=location,
                limit=limit,
                resolved_sources=resolved_sources,
                used_fallback=True,
            )

        # High confidence (or 2-stage disabled) → 2-stage path.
        # `intent` is guaranteed to be non-None here when
        # `intent_extraction_enabled` and the extractor was
        # invoked; mypy --strict can't prove that, so the
        # `is not None` guard is explicit.
        if intent is not None:
            return await self._execute_2stage(
                message=message,
                intent=intent,
                resolved_sources=resolved_sources,
                used_fallback=False,
            )

        # 2-stage flow disabled (or no extractor) → v1 path.
        return await self._execute_v1(
            message=message,
            q=q,
            location=location,
            limit=limit,
            resolved_sources=resolved_sources,
            used_fallback=True,
        )

    # ------------------------------------------------------------------
    # 2-stage path (NEW in T-008): directed aggregator + v1 stage-3 LLM.
    # ------------------------------------------------------------------

    async def _execute_2stage(
        self,
        *,
        message: str,
        intent: Intent,
        resolved_sources: list[str],
        used_fallback: bool,
    ) -> FilteredJobsResult:
        """Run the 2-stage path: directed aggregator + v1 stage-3 LLM.

        Stage 2 calls the aggregator with the extracted
        `q` / `location` (the `intent.q or ""` /
        `intent.location or ""` fallback preserves the v1
        "empty string is a wildcard" contract) and a higher
        per-source cap (`self._intent_max_results`,
        typically 100, vs the v1 `limit=20`).

        Stage 3 is the same v1 LLM filter (strict-subset
        ID validation, hallucination WARNINGs, aggregator
        order). The `_run_stage3(...)` helper is shared
        between the 2 paths so the stage-3 logic is NOT
        duplicated.

        Args:
            message: The original user message (for the LLM
                context).
            intent: The extracted `Intent` (the 7-field
                structured output from stage 1).
            resolved_sources: The pre-resolved `sources` list
                (the use case converted `None` to the
                3-source list).
            used_fallback: `False` for the 2-stage path
                (the dispatcher sets this explicitly so the
                dataclass field is unambiguous).

        Returns:
            A `FilteredJobsResult` with the matched jobs in
            the aggregator's order, the LLM's Spanish
            explanation, the counts, and `used_fallback=False`.
        """
        stage2_q = intent.q if intent.q is not None else ""
        stage2_location = intent.location if intent.location is not None else ""
        # Resolve the `intent.location` to a LinkedIn `geoId` so the
        # LinkedIn scraper can build `?geoId=<n>` (REQ-LOC-GEO-001).
        # The resolver is called ONLY in the 2-stage path AND ONLY
        # when `intent.location is not None` (the v1 path passes
        # `location=""` and there's nothing to resolve). The
        # resolver is a Protocol-conforming in-process dict lookup;
        # a future `HybridLocationResolver` (geocoding API
        # fallback) is a drop-in replacement.
        #
        # Resilience: a resolver exception is caught (a WARNING
        # is logged) and the path proceeds with
        # `linkedin_geo_id=None` (the LinkedIn scraper falls
        # back to the broken `?location=` path — a strict
        # improvement over today's 100%-broken behavior). The
        # exception is NOT propagated to the route; the chat
        # filter is still functional; only the LinkedIn
        # location filter is degraded.
        linkedin_geo_id: int | None = None
        if intent.location is not None and self._location_resolver is not None:
            try:
                linkedin_geo_id = self._location_resolver.resolve(intent.location)
            except Exception as exc:  # noqa: BLE001
                # Resolver exception: log a WARNING and proceed with
                # `linkedin_geo_id=None`. The use case does NOT
                # propagate the exception (the chat filter is still
                # functional; only the LinkedIn location filter is
                # degraded). The LinkedIn scraper falls back to the
                # broken `?location=` path.
                _logger.warning(
                    "Location resolver raised for %r; "
                    "falling back to linkedin_geo_id=None (LinkedIn scraper will use "
                    "broken ?location= path). Cause: %s",
                    intent.location,
                    exc,
                )
                linkedin_geo_id = None
            else:
                if linkedin_geo_id is None:
                    # Resolver miss: log a WARNING so ops can spot
                    # stale geographic intent and re-run the capture
                    # script. The `HardcodedLocationResolver` itself
                    # also logs a WARNING on a miss; the use case
                    # logs a second one with the use-case context
                    # (the `intent.location` string + the path
                    # forward). This double-log is intentional — the
                    # resolver's log is the "miss" signal; the
                    # use-case's log is the "fallback to broken
                    # `?location=`" signal.
                    _logger.warning(
                        "Location resolver returned None for %r; "
                        "falling back to linkedin_geo_id=None (LinkedIn scraper will "
                        "use broken ?location= path).",
                        intent.location,
                    )
        aggregated = await self._aggregator.search(
            keywords=stage2_q,
            location=stage2_location,
            limit=self._intent_max_results,
            sources=resolved_sources,
            linkedin_geo_id=linkedin_geo_id,
        )
        flat_jobs: list[Job] = [agg.job for agg in aggregated.jobs]
        return await self._run_stage3(
            message=message,
            flat_jobs=flat_jobs,
            used_fallback=used_fallback,
        )

    # ------------------------------------------------------------------
    # v1 single-stage path (PRESERVED VERBATIM from pre-2-stage).
    # The aggregator gets `q=""`, `location=""`, `limit=20` regardless
    # of what the caller passed. This keeps the per-source cache
    # keys byte-identical to the pre-T-008 behavior so a v1 caller
    # benefits from existing cache hits.
    # ------------------------------------------------------------------

    async def _execute_v1(
        self,
        *,
        message: str,
        q: str,
        location: str,
        limit: int,
        resolved_sources: list[str],
        used_fallback: bool,
    ) -> FilteredJobsResult:
        """Run the v1 single-stage path: aggregator with the
        caller's `q`/`location`/`limit` + stage-3 LLM filter.

        The v1 logic is VERBATIM from the pre-T-008 use case:
        the aggregator's `search()` is called with whatever
        `q` / `location` / `limit` the caller passed to
        `execute(...)`. The v1 chat endpoint passes
        `q=""`, `location=""`, `limit=20` (per the existing
        `test_filter_use_case.py::test_execute_forwards_q_location_limit_to_aggregator`
        test that asserts the use case FORWARDS those kwargs
        unchanged), but the use case is a thin pass-through
        — a future caller can pre-fill `q` to benefit from
        the aggregator cache.

        Args:
            message: The original user message.
            q: The aggregator's `keywords` (forwarded from
                the caller's `execute(...)`).
            location: The aggregator's `location` (forwarded
                from the caller's `execute(...)`).
            limit: The aggregator's `limit` (forwarded from
                the caller's `execute(...)`).
            resolved_sources: The pre-resolved `sources` list.
            used_fallback: `True` for the v1 path.

        Returns:
            A `FilteredJobsResult` with the matched jobs in
            the aggregator's order, the LLM's Spanish
            explanation, the counts, and `used_fallback=True`.
        """
        aggregated = await self._aggregator.search(
            keywords=q,
            location=location,
            limit=limit,
            sources=resolved_sources,
        )
        flat_jobs: list[Job] = [agg.job for agg in aggregated.jobs]
        return await self._run_stage3(
            message=message,
            flat_jobs=flat_jobs,
            used_fallback=used_fallback,
        )

    # ------------------------------------------------------------------
    # Stage 3 (UNCHANGED from v1): the LLM filter. Shared between
    # `_execute_2stage(...)` and `_execute_v1(...)` so the logic
    # is NOT duplicated. The strict-subset ID validation, the
    # hallucination WARNINGs, the aggregator order, and the
    # short-circuit on empty input are all preserved verbatim.
    # ------------------------------------------------------------------

    async def _run_stage3(
        self,
        *,
        message: str,
        flat_jobs: list[Job],
        used_fallback: bool,
    ) -> FilteredJobsResult:
        """Run the stage-3 LLM filter on the aggregated jobs.

        The flow:
          1. Short-circuit on empty `flat_jobs` (the LLM is
             NEVER called when no jobs are available; the
             response carries the Spanish
             "no se encontraron ofertas" explanation —
             REQ-LLM-003 5th scenario).
          2. Build the 5-key LLM-facing dict per job.
          3. Call the LLM with the Spanish `SYSTEM_PROMPT`
             and a JSON-serialized user message.
          4. Parse the response with `self._parser`.
          5. Validate `matching_ids` to a STRICT SUBSET of
             the input ids; log a WARNING per dropped
             (hallucinated) id.
          6. Build the filtered list in the AGGREGATOR'S
             order (not the LLM's).

        Args:
            message: The original user message.
            flat_jobs: The aggregator's flat list of `Job`
                instances.
            used_fallback: The fallback flag to attach to
                the result (set by the dispatcher).

        Returns:
            A `FilteredJobsResult` with the matched jobs in
            the aggregator's order, the LLM's Spanish
            explanation, the counts, and the `used_fallback`
            flag.
        """
        total_considered = len(flat_jobs)

        # Short-circuit: an empty aggregator result NEVER reaches
        # the LLM. The Spanish explanation is surfaced to the user
        # so the response is sensible (REQ-LLM-003 5th scenario).
        if not flat_jobs:
            return FilteredJobsResult(
                jobs=[],
                explanation=_EMPTY_RESULT_EXPLANATION,
                total_considered=0,
                total_matched=0,
                used_fallback=used_fallback,
            )

        # Build the 5-key LLM-facing dict per job. `dataclasses.asdict`
        # includes all 7 fields of `Job` (id, title, company,
        # location, url, posted_at, description); the LLM prompt
        # builder `_prompt._job_to_dict` projects down to the 5
        # filter-relevant keys (id, title, company, location,
        # description), so the extra fields are dropped at the
        # user-message boundary (the prompt-builder is the
        # single source of truth for what the LLM sees).
        jobs_dicts = [dataclasses.asdict(j) for j in flat_jobs]
        raw_response = await self._llm.complete(
            system=SYSTEM_PROMPT,
            user=build_user_message(message, jobs_dicts),
        )
        selection = self._parser(raw_response)

        # REQ-LLM-003: STRICT SUBSET validation. The LLM might
        # return an id that is NOT in the input list (a
        # "hallucination"). Drop those ids, log a WARNING per
        # dropped id, and build the filtered list in the
        # AGGREGATOR'S order (NOT the LLM's order — the LLM's
        # order is meaningless once we re-key by the input list).
        # Building the result by walking `flat_jobs` (the aggregator
        # order) and filtering by `valid_matching_ids` (a `set`
        # lookup) preserves the aggregator's order naturally.
        valid_ids: set[str] = {j.id for j in flat_jobs}
        valid_matching_ids: set[str] = set()
        for mid in selection.matching_ids:
            if mid in valid_ids:
                valid_matching_ids.add(mid)
            else:
                _logger.warning(
                    "LLM hallucinated id: %s not in input (input had %d ids)",
                    mid,
                    len(valid_ids),
                )
        filtered = [j for j in flat_jobs if j.id in valid_matching_ids]

        return FilteredJobsResult(
            jobs=filtered,
            explanation=selection.explanation,
            total_considered=total_considered,
            total_matched=len(filtered),
            used_fallback=used_fallback,
        )


__all__ = [
    "FilteredJobsResult",
    "FilterJobsByIntentUseCase",
    "_EMPTY_RESULT_EXPLANATION",
]
