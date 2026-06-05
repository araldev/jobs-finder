"""Unit test for the `RateLimitedResponse` Pydantic schema.

Spec: REQ-RL-010 scenario 2 (RateLimitedResponse schema exists).

The 429 body shape is `{"detail": "rate limit exceeded",
"request_id": "..."}` — the same shape as the existing 502 body,
differing only in the `detail` string. The Pydantic schema
`RateLimitedResponse` at `presentation/schemas.py` is the typed
contract: it has exactly two string fields, no more, no less.

This test pins the schema shape so a future refactor that adds or
removes a field surfaces in the unit suite (the schema is
exercised by every 429 integration test, but those tests
inspect the response body shape, not the schema directly).
"""

from __future__ import annotations

from jobs_finder.presentation.schemas import RateLimitedResponse


def test_rate_limited_response_schema() -> None:
    """`RateLimitedResponse` has exactly `{"detail", "request_id"}` (both `str`).

    REQ-RL-010 scenario 2: the schema at `presentation/schemas.py`
    declares exactly two fields — `detail: str` and
    `request_id: str`. The set of field names is pinned; both
    fields are `str`. The 429 body in the integration tests is
    the `model_dump()` of this schema, so the JSON shape is
    transitively pinned by the model.
    """
    field_names = set(RateLimitedResponse.model_fields.keys())
    assert field_names == {"detail", "request_id"}
    # Both fields are typed as `str` (REQ-RL-010: "no extra fields;
    # types are str, str").
    assert RateLimitedResponse.model_fields["detail"].annotation is str
    assert RateLimitedResponse.model_fields["request_id"].annotation is str
