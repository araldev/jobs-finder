"""Chat-filter use case (T-013 of `ai-chat-filter`).

Spec: REQ-LLM-003 (strict-subset ID validation), REQ-CHAT-001
(orchestration).

The use case is the 3-stage chat-filter orchestrator:
  1. Delegate to the existing `SearchAllSourcesUseCase` aggregator
     (reuses the per-source cache + per-source error isolation).
  2. Short-circuit on an empty aggregator result — the LLM is
     NEVER called when no jobs are available; the response carries
     a Spanish "no se encontraron ofertas" explanation so the user
     sees a sensible answer.
  3. Build the 5-key LLM-facing dict per job, call the LLM with
     the Spanish `SYSTEM_PROMPT` (from `_prompt`) and a
     JSON-serialized user message (from `build_user_message`),
     parse the response with `parse_llm_response`, validate
     `matching_ids` to a STRICT SUBSET of the input ids, log a
     `WARNING` per dropped (hallucinated) id, and return the
     filtered jobs in the AGGREGATOR'S order (not the LLM's).

The use case depends ONLY on the application's `LLMClientPort`
Protocol — never on the concrete `MiniMaxLLMClient`. The chat
route (T-014) injects the LLM client at composition-root time;
tests inject a `FakeLLMClient` that conforms to the Protocol
structurally.

The dependency rule is `application -> domain <- infrastructure`.
The use case imports `LLMClientPort` from `application.ports`
(application layer) and the prompt / parser from
`infrastructure.llm._prompt` / `infrastructure.llm._parser`
(infrastructure layer). The latter is a known concession — the
prompt text and the defensive parser are pure functions with no
side effects and no upstream coupling, and the use case's
dependency is on the FUNCTION, not on the infrastructure module's
lifecycle. The infrastructure LLM CLIENT itself remains behind the
`LLMClientPort` Protocol.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import LLMClientPort
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.llm._parser import LLMSelection, parse_llm_response
from jobs_finder.infrastructure.llm._prompt import SYSTEM_PROMPT, build_user_message

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
    """

    jobs: Sequence[Job]
    explanation: str
    total_considered: int
    total_matched: int


class FilterJobsByIntentUseCase:
    """Orchestrate the 3-stage chat-filter flow.

    The constructor is keyword-only to make the call site read
    like a spec:
      `FilterJobsByIntentUseCase(aggregator=..., llm=...)`

    Args:
        aggregator: The existing `SearchAllSourcesUseCase` instance.
            The chat-filter use case reuses the same per-source
            cache + per-source error isolation as the `/jobs`
            aggregator route, so a chat call within the 60s cache
            window reuses the per-source results (REQ-CHAT-003:
            no separate LLM cache).
        llm: Any `LLMClientPort`. The use case depends on the
            Protocol only; the concrete `MiniMaxLLMClient` is
            injected at composition-root time (T-016).
        parser: The defensive parser. Defaults to
            `parse_llm_response` from `infrastructure.llm._parser`.
            The parameter is keyword-only with a default so a
            test can inject a parser that returns a canned
            `LLMSelection` (the unit tests use a `FakeLLMClient`
            that already short-circuits the parser by returning
            the right JSON string; the parser is still exercised
            end-to-end in the integration test, T-017).
    """

    def __init__(
        self,
        *,
        aggregator: SearchAllSourcesUseCase,
        llm: LLMClientPort,
        parser: Callable[[str], LLMSelection] = parse_llm_response,
    ) -> None:
        self._aggregator = aggregator
        self._llm = llm
        self._parser = parser

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

        Args:
            message: The user's natural-language intent (e.g.
                "ingeniero < 2 años en Málaga"). Pre-normalized by
                the route (NFC + casefold + strip, per REQ-CHAT-001).
            q: The aggregator's `keywords`. The chat endpoint passes
                `""` in v1 (the message IS the intent); a future
                caller can pre-fill `q` to benefit from the
                aggregator cache.
            location: The aggregator's `location`. Same v1
                convention as `q`.
            limit: The aggregator's `limit` (job cap per source).
            sources: The aggregator's `sources` filter. `None`
                means all 3 sources.

        Returns:
            A `FilteredJobsResult` with the matched jobs in the
            aggregator's order, the LLM's Spanish explanation,
            and the `total_considered` / `total_matched` counts.

        Raises:
            LLMUnavailableError: on 5xx, timeout, 429, or MiniMax
                error codes 1002/1013 (after retry exhaustion) and
                1004/1008/1001 (no retry). Propagated unchanged.
            LLMResponseParseError: when the parser cannot extract
                a JSON object. Propagated unchanged. The route
                maps this to 422.
            JobSearchError: any per-source error from the aggregator
                that is NOT isolated to a single source. Propagated
                unchanged.
        """
        # The aggregator's `search()` expects `sources: list[str]`
        # (never `None`); when the chat caller passes `None` we
        # forward all 3 sources. A non-None `Sequence` is converted
        # to a list so the aggregator's type contract is honored.
        if sources is None:
            resolved_sources: list[str] = ["linkedin", "indeed", "infojobs"]
        else:
            resolved_sources = list(sources)
        aggregated = await self._aggregator.search(
            keywords=q,
            location=location,
            limit=limit,
            sources=resolved_sources,
        )
        # The aggregator flattens the per-source results into
        # `list[AggregatedJob]` (each carrying a `sources: list[str]`
        # and the canonical `Job`). The chat filter operates on
        # the canonical `Job`; the per-source membership is not
        # surfaced to the LLM (it filters on title / company /
        # location / description only).
        flat_jobs: list[Job] = [agg.job for agg in aggregated.jobs]
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
        )


__all__ = [
    "FilteredJobsResult",
    "FilterJobsByIntentUseCase",
    "_EMPTY_RESULT_EXPLANATION",
]
