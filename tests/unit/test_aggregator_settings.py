"""Unit tests for the `Settings.aggregator_*` ranking fields.

Spec: REQ-AR-008 (jobs-aggregator-ranking).

These tests pin the 2 new `Settings` fields plus the JSON validator
that parses `AGGREGATOR_PRIORITY_MAP` from the env:

- `aggregator_ranking_strategy`: `Literal["posted_at", "priority", "none"]`,
  default `"posted_at"`. Unknown values raise `pydantic.ValidationError`
  at startup (the Pydantic `Literal` validator enforces the closed
  set).
- `aggregator_priority_map`: `dict[str, int]`, default
  `{"linkedin": 0, "indeed": 1, "infojobs": 2}`. JSON env-var input
  is parsed by the `_parse_aggregator_priority_map`
  `field_validator(mode="before")` (mirrors the `_parse_exempt_paths`
  pattern at `infrastructure/config.py:418-442`).

These tests are the RED step of T-001 Cycle 1 (Strict TDD): they
MUST be authored BEFORE the Settings fields are added. The run
on a clean tree must FAIL for the right reason
("`Settings` has no field `aggregator_ranking_strategy`"), and the
GREEN step then adds the 2 fields + the validator.
"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError

from jobs_finder.infrastructure.config import Settings


def test_default_strategy_is_posted_at() -> None:
    """The default `aggregator_ranking_strategy` is `"posted_at"` (REQ-AR-002, REQ-AR-008).

    No env var is set, so Pydantic falls back to the field default.
    The default is the freshness strategy — the new behavior the
    `jobs-aggregator-ranking` change ships — per the spec's Q-3
    decision (`posted_at` is the most useful default for a job
    search).
    """
    settings = Settings()
    assert settings.aggregator_ranking_strategy == "posted_at"


def test_default_priority_map_is_linkedin_first() -> None:
    """The default `aggregator_priority_map` is LinkedIn-first (REQ-AR-004, REQ-AR-008).

    The 3 known sources are mapped to `0, 1, 2` in source-priority
    order (LinkedIn > Indeed > InfoJobs). This is the tie-breaker for
    `strategy="posted_at"` and the primary sort key for
    `strategy="priority"`.
    """
    settings = Settings()
    assert settings.aggregator_priority_map == {
        "linkedin": 0,
        "indeed": 1,
        "infojobs": 2,
    }


def test_env_var_override_for_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`AGGREGATOR_RANKING_STRATEGY=priority` parses to the field value `"priority"` (REQ-AR-003).

    The `validation_alias=AliasChoices("AGGREGATOR_RANKING_STRATEGY", ...)`
    on the field makes the env var the primary lookup; the
    programmatic `Settings(aggregator_ranking_strategy=...)` form
    still works via the second alias. Pydantic's `Literal` validator
    accepts `"priority"`.
    """
    monkeypatch.setenv("AGGREGATOR_RANKING_STRATEGY", "priority")
    settings = Settings()
    assert settings.aggregator_ranking_strategy == "priority"


def test_invalid_strategy_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`AGGREGATOR_RANKING_STRATEGY=banana` raises `pydantic.ValidationError` (REQ-AR-003).

    Pydantic's `Literal[...]` validator rejects values that are not
    in the closed set. The error is raised at `Settings()`
    construction time so misconfiguration fails fast at startup
    (not on the first `/jobs` request).
    """
    monkeypatch.setenv("AGGREGATOR_RANKING_STRATEGY", "banana")
    with pytest.raises(ValidationError):
        Settings()


def test_env_var_override_for_priority_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`AGGREGATOR_PRIORITY_MAP='{"linkedin":2,"indeed":1,"infojobs":0}'` reverses the order.

    REQ-AR-004 scenario "custom priority map reverses the order":
    the JSON env var is parsed by the `_parse_aggregator_priority_map`
    `field_validator(mode="before")`. The reversed map yields
    `infojobs` (0) > `indeed` (1) > `linkedin` (2) for
    `strategy="priority"`.
    """
    monkeypatch.setenv("AGGREGATOR_PRIORITY_MAP", '{"linkedin":2,"indeed":1,"infojobs":0}')
    settings = Settings()
    assert settings.aggregator_priority_map == {
        "linkedin": 2,
        "indeed": 1,
        "infojobs": 0,
    }


def test_invalid_json_priority_map_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`AGGREGATOR_PRIORITY_MAP='not json'` raises at startup (REQ-AR-004).

    The `_parse_aggregator_priority_map` validator catches
    `json.JSONDecodeError` and re-raises as `ValueError`. Pydantic
    surfaces `ValueError` from a `field_validator(mode="before")`
    as either a `pydantic.ValidationError` (post-parse validation)
    or a `pydantic_settings.exceptions.SettingsError` (pre-parse,
    when the env-var JSON itself is malformed). Both are
    `ValueError` subclasses, so the test asserts on `ValueError` to
    cover both paths — the same pattern used by
    `test_rate_limit_trusted_proxies_with_malformed_json_raises`
    in `test_rate_limit_settings.py:188-214`.

    The spec's intent is "malformed JSON fails fast at startup"; the
    exact exception class is an implementation detail of
    Pydantic-Settings' parse pipeline.
    """
    monkeypatch.setenv("AGGREGATOR_PRIORITY_MAP", "not json")
    with pytest.raises(ValueError):
        Settings()


def test_programmatic_construction_still_works() -> None:
    """`Settings(aggregator_ranking_strategy=..., aggregator_priority_map=...)` works.

    Programmatic construction is the second alias in
    `AliasChoices("AGGREGATOR_*", "aggregator_*")` — tests that build
    a `Settings` directly (no env var) must still be able to
    override the 2 new fields.
    """
    custom_map: dict[str, int] = {"linkedin": 0, "indeed": 1}
    settings = Settings(
        aggregator_ranking_strategy="none",
        aggregator_priority_map=custom_map,
    )
    assert settings.aggregator_ranking_strategy == "none"
    assert settings.aggregator_priority_map == custom_map


# Silence the unused-Literal-import linter when tests are selectively
# disabled — the import documents the type at module top for
# readability.
_ = Literal
