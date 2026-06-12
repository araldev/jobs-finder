"""Unit tests for the `ChatStream*Event` Pydantic schemas (T-007 of `chat-streaming`).

Spec: REQ-SSE-001 + REQ-META-001.

The 3 schemas are the wire-format Pydantic models for the
SSE `data:` payloads emitted by `POST /jobs/chat/stream`:

  - `ChatStreamTextEvent` (the `event: text` payload):
    `{"delta": "<chunk>"}`. The `delta` is the verbatim
    LLM token (a `str`, NOT `Optional` — the use case
    never yields an empty delta per the parser's policy).
  - `ChatStreamMetaEvent` (the `event: meta` payload,
    2-stage path only): `{"intent": <Intent JSON>}`.
    The `intent` is the EXACT `Intent` the
    `IntentExtractor` returned — no fabrication, no
    defaults.
  - `ChatStreamDoneEvent` (the `event: done` payload,
    terminal): the v1 `ChatResponse` shape + a
    `request_id` field. The `jobs` list is the same
    `JobResponse` shape used by `/jobs`, `/jobs/linkedin`,
    `/jobs/indeed`, `/jobs/infojobs` so the UI can reuse
    its per-job renderers.

The 3 round-trip tests below pin the JSON shape: a model
serialized with `model_dump_json()` + parsed back with
`model_validate_json()` MUST produce an equal model.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from jobs_finder.application.ports import Intent
from jobs_finder.domain.job import Job
from jobs_finder.presentation.schemas import (
    ChatStreamDoneEvent,
    ChatStreamMetaEvent,
    ChatStreamTextEvent,
)

# ---------------------------------------------------------------------------
# ChatStreamTextEvent
# ---------------------------------------------------------------------------


def test_chat_stream_text_event_round_trip() -> None:
    """`ChatStreamTextEvent(delta="hello")` round-trips through JSON.

    The wire format is `{"delta": "hello"}` — a single
    string field. The route's `_serialize_event` builds
    the SSE `data:` payload via
    `model.model_dump_json()`; the integration tests
    assert the wire bytes are `data: {"delta": "hello"}\n\n`.
    """
    event = ChatStreamTextEvent(delta="hello")
    raw = event.model_dump_json()
    # The wire format is exactly `{"delta":"hello"}`.
    assert json.loads(raw) == {"delta": "hello"}
    # Round-trip: parse the same JSON back; result MUST equal the original.
    parsed = ChatStreamTextEvent.model_validate_json(raw)
    assert parsed == event
    # And the parsed value is structurally identical.
    assert parsed.delta == "hello"


def test_chat_stream_text_event_handles_unicode_and_special_chars() -> None:
    """The text event preserves unicode (Spanish accents, emojis, etc.) verbatim.

    The chat filter is Spanish; a real model's output can
    contain accents, `ñ`, and emojis. Pydantic's
    `model_dump_json` MUST NOT mangle them (a regression
    to `str.encode("ascii")` would corrupt the user-
    facing text).
    """
    event = ChatStreamTextEvent(delta="Málaga — ¡hola! 🎉")
    raw = event.model_dump_json()
    parsed = ChatStreamTextEvent.model_validate_json(raw)
    assert parsed.delta == "Málaga — ¡hola! 🎉"


# ---------------------------------------------------------------------------
# ChatStreamMetaEvent
# ---------------------------------------------------------------------------


def test_chat_stream_meta_event_round_trip() -> None:
    """`ChatStreamMetaEvent` serializes the embedded `Intent` JSON verbatim.

    The wire format is `{"intent": <Intent JSON>}`. The
    `Intent` is a Pydantic `BaseModel`; the meta event
    embeds it as a nested field. A round-trip MUST
    preserve every field (q, location, experience_years,
    remote, employment_type, confidence, notes).
    """
    intent = Intent(
        q="python",
        location="Madrid",
        experience_years=2,
        remote=True,
        employment_type="full_time",
        confidence=0.95,
        notes="junior",
    )
    event = ChatStreamMetaEvent(intent=intent)
    raw = event.model_dump_json()
    # The wire format includes the full Intent JSON.
    parsed_obj = json.loads(raw)
    assert parsed_obj["intent"]["q"] == "python"
    assert parsed_obj["intent"]["location"] == "Madrid"
    assert parsed_obj["intent"]["experience_years"] == 2
    assert parsed_obj["intent"]["remote"] is True
    assert parsed_obj["intent"]["employment_type"] == "full_time"
    assert parsed_obj["intent"]["confidence"] == 0.95
    assert parsed_obj["intent"]["notes"] == "junior"
    # Round-trip: parse the same JSON back.
    parsed = ChatStreamMetaEvent.model_validate_json(raw)
    assert parsed.intent == intent


# ---------------------------------------------------------------------------
# ChatStreamDoneEvent
# ---------------------------------------------------------------------------


def _make_job(job_id: str) -> Job:
    """A sample Job for the done event's `jobs` list."""
    return Job(
        id=job_id,
        title=f"Title {job_id}",
        company=f"Co-{job_id}",
        location="Madrid",
        url=f"https://example.com/jobs/{job_id}",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="linkedin",
    )


def test_chat_stream_done_event_round_trip_with_request_id() -> None:
    """`ChatStreamDoneEvent` round-trips with the SSE-only `request_id` field.

    The done event carries the v1 `ChatResponse` shape +
    a `request_id` field (the route injects it from
    `request.state.request_id`). The wire format MUST
    include `request_id` (the v1 `ChatResponse` did NOT
    have it; the SSE done event does).
    """
    from jobs_finder.presentation.schemas import to_response  # noqa: PLC0415

    jobs = [_make_job("a"), _make_job("b"), _make_job("c")]
    event = ChatStreamDoneEvent(
        jobs=[to_response(j) for j in jobs],
        explanation="3 match",
        total_considered=3,
        total_matched=3,
        used_fallback=False,
        request_id="abc-123",
    )
    raw = event.model_dump_json()
    parsed_obj = json.loads(raw)
    # The 6 documented fields (jobs, explanation, total_considered,
    # total_matched, used_fallback, request_id) are all present.
    assert set(parsed_obj.keys()) == {
        "jobs",
        "explanation",
        "total_considered",
        "total_matched",
        "used_fallback",
        "request_id",
    }
    assert parsed_obj["explanation"] == "3 match"
    assert parsed_obj["total_considered"] == 3
    assert parsed_obj["total_matched"] == 3
    assert parsed_obj["used_fallback"] is False
    assert parsed_obj["request_id"] == "abc-123"
    # The `jobs` field is a list of JobResponse objects.
    assert [j["id"] for j in parsed_obj["jobs"]] == ["a", "b", "c"]
    # Round-trip: parse the same JSON back.
    parsed = ChatStreamDoneEvent.model_validate_json(raw)
    assert parsed == event


def test_chat_stream_done_event_default_request_id_is_empty_string() -> None:
    """A `ChatStreamDoneEvent` without `request_id` defaults to `""`.

    The `request_id` field is OPTIONAL (default `""`) so
    a unit test that constructs the event WITHOUT the
    request_id (testing the schema in isolation) does
    not have to set it. The route injects the real
    `request_id` from the request state.
    """
    from jobs_finder.presentation.schemas import to_response  # noqa: PLC0415

    event = ChatStreamDoneEvent(
        jobs=[to_response(_make_job("a"))],
        explanation="ok",
        total_considered=1,
        total_matched=1,
        used_fallback=False,
    )
    assert event.request_id == ""
