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
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import (
    Intent,
    IntentExtractorPort,
    JobRepositoryPort,
    LLMClientPort,
    LocationResolverPort,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.llm._parser import (
    LLMSelection,
    StreamEventParser,
    parse_llm_response,
)
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


# ---------------------------------------------------------------------------
# Streaming event dataclasses (T-006 of `chat-streaming`)
#
# The streaming endpoint (`POST /jobs/chat/stream`) emits 3 kinds
# of events in this exact order:
#   - `StreamEventMeta` (zero or one, 2-stage path only)
#   - `StreamEventText` (one or more, per LLM token)
#   - `StreamEventDone` (exactly one, terminal)
#
# The 3 dataclasses are `frozen=True, slots=True` (mirrors the
# project's value-object style) so consumers cannot mutate the
# events. The `StreamEvent` union type (defined below) is the
# return type of `stream_execute(...)` for downstream consumers
# (the route's SSE generator, the integration tests).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StreamEventMeta:
    """The stage-1 `Intent` emitted as the FIRST event (2-stage path only).

    REQ-META-001: the meta event is OPTIONAL (the v1 path
    emits no `meta`) and MUST precede the first `text`
    event. The `intent` field is the EXACT `Intent` the
    `IntentExtractor` returned — the route serializes it
    verbatim (no fabrication, no defaults).
    """

    intent: Intent


@dataclass(frozen=True, slots=True)
class StreamEventText:
    """A single LLM token emitted as a `text` event.

    The `delta` field is the verbatim string the LLM
    emitted (NOT a re-derivation). The route serializes
    it as `event: text\\ndata: {"delta": <delta>}\\n\\n`.
    """

    delta: str


@dataclass(frozen=True, slots=True)
class StreamEventDone:
    """The terminal `done` event carrying the filtered jobs + counts.

    REQ-SSE-001 3rd scenario: the `done` event MUST
    contain the same fields as v1 `ChatResponse`
    (`jobs`, `explanation`, `total_considered`,
    `total_matched`, `used_fallback`) PLUS the SSE-only
    `request_id` (the route injects it; the use case
    does NOT set it). The `jobs` list is in the
    AGGREGATOR's order (NOT the LLM's emission order).
    """

    jobs: Sequence[Job]
    explanation: str
    total_considered: int
    total_matched: int
    used_fallback: bool
    request_id: str = ""


# The discriminated union for `stream_execute` callers. Python
# 3.12+ has a native `type` syntax; the 3.10-compatible
# `Union[...]` keeps mypy --strict happy on all supported
# versions. Consumers `isinstance`-discriminate to map each
# event to its SSE wire shape.
StreamEvent = StreamEventMeta | StreamEventText | StreamEventDone


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
            repository query. Defaults to `20` (matching the
            scheduler's fresh results). The v1 path always uses
            `_V1_DEFAULT_LIMIT = 20` regardless of this setting.
        job_repository: `JobRepositoryPort` for DB-only job lookup.
            The chat endpoint NEVER calls the live scrapers — it
            queries this repository (populated by the scheduler).
            If `None`, the use case raises `RuntimeError` (no
            aggregator fallback exists by design).
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
        job_repository: JobRepositoryPort | None = None,
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
        self._job_repository = job_repository

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
    # Streaming sibling (NEW in T-006 of `chat-streaming`):
    # `stream_execute(...) -> AsyncIterator[StreamEvent]`.
    #
    # The streaming path is the SIBLING of `execute(...)`: it
    # shares the v1 dispatch + validation (stage 1 + stage 2
    # + the short-circuit on empty aggregator) but emits
    # `StreamEvent*` dataclasses instead of returning a single
    # `FilteredJobsResult`. The `stream_complete` call lives in
    # the new `_run_stage3_streaming(...)` helper. The v1
    # `_run_stage3(...)` helper and `execute(...)` are
    # UNCHANGED per REQ-BACKWARDS-COMPAT-001.
    # ------------------------------------------------------------------

    async def stream_execute(  # noqa: PLR0912
        self,
        *,
        message: str,
        q: str,
        location: str,
        limit: int,
        sources: Sequence[str] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream-execute the chat-filter flow, yielding `StreamEvent*` per token.

        The 3-stage flow mirrors `execute(...)` but yields
        events in real time:

          1. (2-stage only) `StreamEventMeta(intent)` — the
             stage-1 `Intent`. Omitted when 2-stage is
             disabled (`intent_extraction_enabled=False` or
             no `intent_extractor`).
          2. Aggregator `search(...)` — silent (no event
             yielded). The route's keepalive covers the
             wait (see REQ-SSE-002).
          3. (LLM) `StreamEventText(delta)` × N — one per
             LLM token, in the LLM's emission order. The
             `StreamEventParser` accumulates the chunks
             in the background for end-of-stream
             re-parsing.
          4. (Terminal) `StreamEventDone(jobs, ...)` —
             carries the matched jobs in the
             AGGREGATOR's order + the LLM's
             explanation + the counts. The `request_id`
             field is set by the route (the use case
             leaves it empty).

        On the empty-aggregator short-circuit, exactly
        ONE `StreamEventDone` is yielded (the
        "no se encontraron ofertas" payload); the LLM
        is never called.

        Args:
            message: The user's message (pre-normalized by
                the route; the use case does NOT re-normalize).
            q / location / limit: Forwarded to the
                aggregator (the v1 semantics).
            sources: The aggregator's `sources` filter
                (`None` means all 3 sources).

        Yields:
            `StreamEventMeta` (zero or one), then
            `StreamEventText` × N (one per LLM token), then
            `StreamEventDone` (exactly one, terminal).

        Raises:
            Does NOT raise domain exceptions. The route's
            SSE generator catches them and maps to SSE
            `event: error`. The use case yields the
            normal happy-path events only.
        """
        # Resolve `sources` once; the 2 paths share it.
        if sources is None:
            resolved_sources: list[str] = ["linkedin", "indeed", "infojobs"]
        else:
            resolved_sources = list(sources)

        # Stage 1: extract intent (only when the 2-stage flow
        # is active). The intent's `confidence` drives the
        # dispatch AND the `meta` event.
        intent: Intent | None = None
        used_fallback = True  # default for v1 path
        if self._intent_extraction_enabled and self._intent_extractor is not None:
            try:
                intent = await self._intent_extractor.extract(message=message)
            except LLMResponseParseError:
                # Stage-1 parse failure → v1 fallback (no meta).
                intent = None

        # Confidence gate: low-confidence intent → v1 fallback
        # (no meta event).
        if intent is not None and intent.confidence < self._intent_extraction_confidence_threshold:
            intent = None  # v1 path: no meta

        # Stage 2: repository query (cached jobs from scheduler).
        # The chat endpoint NEVER calls the live scrapers — it
        # queries the SQLite-backed repository populated by the
        # scheduler. The DB is the single source of jobs.
        if self._job_repository is None:
            raise RuntimeError(
                "FilterJobsByIntentUseCase: stream_execute requires "
                "job_repository (DB) — no aggregator fallback exists. "
                "Wire job_repository in app_factory.build_app()."
            )
        if intent is not None:
            stage2_q = intent.q if intent.q is not None else ""
            stage2_location = intent.location if intent.location is not None else ""
            used_fallback = False
            # Emit the `meta` event FIRST (2-stage path).
            yield StreamEventMeta(intent=intent)
            flat_jobs = await self._job_repository.search_jobs_history(
                keywords=stage2_q,
                location=stage2_location,
                sources=resolved_sources,
                limit=self._intent_max_results,
            )
        else:
            flat_jobs = await self._job_repository.search_jobs_history(
                keywords=q,
                location=location,
                sources=resolved_sources,
                limit=limit,
            )

        # Empty-aggregator short-circuit: emit a single `done`
        # and return. The LLM is NEVER called.
        if not flat_jobs:
            yield StreamEventDone(
                jobs=[],
                explanation=_EMPTY_RESULT_EXPLANATION,
                total_considered=0,
                total_matched=0,
                used_fallback=used_fallback,
            )
            return

        # Stage 3: the LLM stream. Build the same 5-key
        # LLM-facing dicts per job that `_run_stage3` uses;
        # call `stream_complete` (instead of `complete`);
        # feed each chunk into a `StreamEventParser` and yield
        # the verbatim `text` events; finalize the parser at
        # the end; yield `done` with the strict-subset
        # matched jobs in the AGGREGATOR's order.
        jobs_dicts = [dataclasses.asdict(j) for j in flat_jobs]
        parser = StreamEventParser()
        async for chunk in self._llm.stream_complete(
            system=SYSTEM_PROMPT,
            user=build_user_message(message, jobs_dicts),
        ):
            for text in parser.feed(chunk):
                yield StreamEventText(delta=text)

        # Re-parse the accumulated buffer; drop hallucinated
        # ids (defense in depth — the parser already logs a
        # WARNING per drop).
        valid_ids: set[str] = {j.id for j in flat_jobs}
        # Let `LLMResponseParseError` propagate from this
        # generator. The route's producer wraps the
        # `stream_execute` call in a `try / except
        # BaseException` and maps the exception to the
        # `event: error` SSE frame with the `llm_parse`
        # machine code (REQ-ERROR-MAPPING-001).
        selection = parser.finalize(valid_ids)

        # Build the filtered list in the AGGREGATOR's order.
        # If the LLM produced no valid selection (thinking consumed all
        # tokens), fall back to returning all aggregator jobs.
        if not selection.matching_ids:
            filtered = list(flat_jobs)
            used_fallback = True
        else:
            filtered = [j for j in flat_jobs if j.id in set(selection.matching_ids)]
        yield StreamEventDone(
            jobs=filtered,
            explanation=selection.explanation,
            total_considered=len(flat_jobs),
            total_matched=len(filtered),
            used_fallback=used_fallback,
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
        """Run the 2-stage path: DB query (from intent) + v1 stage-3 LLM.

        Stage 2 queries the `job_repository` (the SQLite-backed
        cache populated by the scheduler) using the extracted
        `intent.q` and `intent.location`. The repository NEVER
        hits the live scrapers — it serves cached jobs only.

        Stage 3 is the same v1 LLM filter (strict-subset ID
        validation, hallucination WARNINGs, repo order).
        The `_run_stage3(...)` helper is shared between the
        2 paths so the stage-3 logic is NOT duplicated.

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
            the repository's order, the LLM's Spanish
            explanation, the counts, and `used_fallback=False`.

        Raises:
            RuntimeError: if `self._job_repository is None` —
                the chat endpoint requires the DB and refuses to
                call the live scrapers.
        """
        if self._job_repository is None:
            raise RuntimeError(
                "FilterJobsByIntentUseCase: _execute_2stage requires "
                "job_repository (DB) — no aggregator fallback exists. "
                "Wire job_repository in app_factory.build_app()."
            )

        stage2_q = intent.q if intent.q is not None else ""
        stage2_location = intent.location if intent.location is not None else ""
        flat_jobs: list[Job] = await self._job_repository.search_jobs_history(
            keywords=stage2_q,
            location=stage2_location,
            sources=resolved_sources,
            limit=self._intent_max_results,
        )
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
        """Run the v1 single-stage path: DB query + stage-3 LLM filter.

        The v1 chat endpoint passes `q=""`, `location=""`,
        `limit=20` — the DB query with empty keyword/location
        matches all jobs (the empty-string wildcard contract).

        Args:
            message: The original user message.
            q: The DB query's `keywords` (forwarded from
                the caller's `execute(...)`).
            location: The DB query's `location` (forwarded
                from the caller's `execute(...)`).
            limit: The DB query's `limit` (forwarded from
                the caller's `execute(...)`).
            resolved_sources: The pre-resolved `sources` list.
            used_fallback: `True` for the v1 path.

        Returns:
            A `FilteredJobsResult` with the matched jobs in
            the repository's order, the LLM's Spanish
            explanation, the counts, and `used_fallback=True`.

        Raises:
            RuntimeError: if `self._job_repository is None` —
                the chat endpoint requires the DB and refuses to
                call the live scrapers.
        """
        if self._job_repository is None:
            raise RuntimeError(
                "FilterJobsByIntentUseCase: _execute_v1 requires "
                "job_repository (DB) — no aggregator fallback exists. "
                "Wire job_repository in app_factory.build_app()."
            )

        flat_jobs: list[Job] = await self._job_repository.search_jobs_history(
            keywords=q,
            location=location,
            sources=resolved_sources,
            limit=limit,
        )
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
