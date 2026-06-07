"""Unit tests for the Spanish system prompt + user message builder (T-009 of `ai-chat-filter`).

Spec: REQ-LLM-004 (5 invariant rules), REQ-LLM-001 (request body shape).

Two things live in `infrastructure/llm/_prompt.py`:

  1. `SYSTEM_PROMPT: str` — the Spanish prompt that drives the LLM
     behavior. The text is from `sdd/ai-chat-filter/explore` §5
     (verbatim) and must contain the 5 invariant keywords
     documented in REQ-LLM-004:

       a. Spanish (contains Spanish words like "Eres",
          "asistente", "filtra", "intención").
       b. No-ID-invention rule: contains
          "SOLO puedes devolver IDs".
       c. Favor-recall rule: contains
          "Si dudas entre incluir o excluir" AND "INCLÚYELA".
       d. No-data-assumption rule: contains
          "no asumas experiencia, salario, modalidad remota".
       e. JSON shape rule: declares the exact
          `{"matching_ids": [...], "explanation": "..."}` shape.

  2. `build_user_message(intent, jobs) -> str` — builds the user
     message as a JSON-serialized object:
       `{"intent": "<intent>", "jobs": [...]}`
     Each job in the `jobs` array is a dict with the keys
     `id, title, company, location, description`. The
     `description` MUST be `null` (not `""`) when the source has
     no description — per the spec's "no-assumption" rule (a
     model that sees `""` may interpret it as "explicitly empty
     description" rather than "no information available").

This is the RED → GREEN → REFACTOR anchor for T-009. The test is
authored BEFORE the production module is added, run to confirm
it fails (RED), then the module is added, then the test passes
(GREEN).
"""

from __future__ import annotations

import json

from jobs_finder.infrastructure.llm._prompt import SYSTEM_PROMPT, build_user_message

# ===========================================================================
# SYSTEM_PROMPT invariant checks (REQ-LLM-004, 5 keywords)
# ===========================================================================


def test_system_prompt_is_a_non_empty_string() -> None:
    """`SYSTEM_PROMPT` exists and is a non-empty `str`."""
    assert isinstance(SYSTEM_PROMPT, str)
    assert SYSTEM_PROMPT.strip() != ""


def test_system_prompt_is_in_spanish() -> None:
    """The prompt is in Spanish (contains Spanish-specific words).

    REQ-LLM-004 rule 1 (Spanish). The "Eres ... asistente" opening
    is the canonical phrase; "filtra" + "intención" are also
    Spanish-specific words that an English prompt would lack.
    """
    lowered = SYSTEM_PROMPT.lower()
    # Multiple Spanish-specific words must be present.
    assert "eres" in lowered
    assert "asistente" in lowered
    assert "filtra" in lowered
    assert "intención" in lowered or "intencion" in lowered


def test_system_prompt_contains_no_id_invention_rule() -> None:
    """REQ-LLM-004 rule 2: "SOLO puedes devolver IDs que aparezcan en la lista".

    The defensive parser (T-008) + the use case's strict-subset
    validation (T-013) are the second line of defense; the prompt
    is the FIRST line — without it, the model invents IDs and the
    strict-subset step silently drops them (no warning to the user
    about the model malfunction).
    """
    assert "SOLO puedes devolver IDs" in SYSTEM_PROMPT


def test_system_prompt_contains_favor_recall_rule() -> None:
    """REQ-LLM-004 rule 3: "Si dudas entre incluir o excluir ... INCLÚYELA".

    The favor-recall rule is critical for UX: a model that
    errs on the side of EXCLUSION will hide relevant jobs the
    user wanted to see (and the user can't recover what wasn't
    shown). The prompt's explicit "INCLÚYELA" (include it)
    forces the model toward recall over precision.
    """
    assert "Si dudas entre incluir o excluir" in SYSTEM_PROMPT
    assert "INCLÚYELA" in SYSTEM_PROMPT


def test_system_prompt_contains_no_data_assumption_rule() -> None:
    """REQ-LLM-004 rule 4: do NOT assume data not present in the offer.

    The exact phrase from the prompt is
    "no asumas experiencia, salario, modalidad remota" (per
    explore §5). A model that ASSUMES "no description = on-site"
    would silently drop every offer missing a description.
    """
    # Case-insensitive: the prompt uses "NO asumas" (uppercase for
    # emphasis in the third bullet) — the semantic is the same.
    assert "no asumas" in SYSTEM_PROMPT.lower()
    # All 3 forbidden assumptions are explicitly named in the prompt.
    assert "experiencia" in SYSTEM_PROMPT
    assert "salario" in SYSTEM_PROMPT
    assert "modalidad remota" in SYSTEM_PROMPT


def test_system_prompt_declares_exact_json_shape() -> None:
    """REQ-LLM-004 rule 5: declares the exact `{"matching_ids": [...], "explanation": "..."}` shape.

    The defensive parser (T-008) extracts this shape, so the
    prompt MUST name both keys verbatim — a model that returns
    `{"ids": [...], "reason": "..."}` would parse but produce
    empty results.
    """
    # Both keys are present in the prompt text (the example block).
    assert '"matching_ids"' in SYSTEM_PROMPT
    assert '"explanation"' in SYSTEM_PROMPT


# ===========================================================================
# build_user_message — returns JSON-serializable user message
# ===========================================================================


def test_build_user_message_returns_valid_json_string() -> None:
    """`build_user_message` returns a `str` parseable by `json.loads`."""
    result = build_user_message("hola", [])
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_build_user_message_includes_intent_field() -> None:
    """The serialized JSON has an `intent` field with the input intent."""
    result = build_user_message("ingeniero < 2 años en Málaga", [])
    parsed = json.loads(result)
    assert parsed["intent"] == "ingeniero < 2 años en Málaga"


def test_build_user_message_includes_jobs_array() -> None:
    """The serialized JSON has a `jobs` field with the input jobs (as a list)."""
    jobs = [
        {
            "id": "a",
            "title": "T",
            "company": "C",
            "location": "L",
            "description": None,
        }
    ]
    result = build_user_message("any", jobs)
    parsed = json.loads(result)
    assert "jobs" in parsed
    assert isinstance(parsed["jobs"], list)
    assert len(parsed["jobs"]) == 1


def test_build_user_message_jobs_have_required_keys() -> None:
    """Each job dict in the serialized JSON has the 5 required keys.

    The LLM needs the 5 fields to filter on them; missing any
    would force the LLM to either invent a value (forbidden by
    the no-assumption rule) or refuse to answer.
    """
    jobs = [
        {
            "id": "id-1",
            "title": "Senior Python",
            "company": "Acme",
            "location": "Madrid",
            "description": "5+ years experience",
        }
    ]
    parsed = json.loads(build_user_message("python", jobs))
    job = parsed["jobs"][0]
    assert set(job.keys()) == {"id", "title", "company", "location", "description"}


def test_build_user_message_description_none_serializes_as_null() -> None:
    """A job with `description=None` is serialized as JSON `null`, NOT empty string.

    Per the spec's "no-assumption" rule, a model that sees
    `description=""` may interpret it as "explicitly empty
    description" rather than "no information available".
    The use case's `j.to_dict()` and the prompt's
    `description` field use `None` as the canonical "absent"
    sentinel; `json.dumps(None) == "null"`, which the LLM
    sees as "no information" — exactly the right semantic.
    """
    jobs = [
        {
            "id": "linkedin-1",
            "title": "Job",
            "company": "Co",
            "location": "Loc",
            "description": None,
        }
    ]
    result = build_user_message("any", jobs)
    # The literal `null` is in the rendered string (compact form, no space).
    assert '"description":null' in result
    # And the empty-string alternative is NOT in the rendered string.
    assert '"description":""' not in result


def test_build_user_message_description_with_text_is_preserved() -> None:
    """A job with a non-None description string serializes that string."""
    jobs = [
        {
            "id": "indeed-1",
            "title": "Job",
            "company": "Co",
            "location": "Loc",
            "description": "5+ years Python, full-time",
        }
    ]
    result = build_user_message("any", jobs)
    parsed = json.loads(result)
    assert parsed["jobs"][0]["description"] == "5+ years Python, full-time"


def test_build_user_message_with_empty_jobs_list() -> None:
    """An empty `jobs` list serializes as `[]` (not omitted)."""
    result = build_user_message("any", [])
    parsed = json.loads(result)
    assert parsed["jobs"] == []
    assert parsed["intent"] == "any"


def test_build_user_message_preserves_job_order() -> None:
    """The serialized `jobs` list preserves the input order.

    The LLM should not re-order (the input order is the
    aggregator's order, which is the user-facing presentation
    order). A reordered prompt would also confuse the strict-
    subset ID validation in the use case.
    """
    jobs = [
        {"id": "z", "title": "Z", "company": "Z", "location": "Z", "description": None},
        {"id": "a", "title": "A", "company": "A", "location": "A", "description": None},
        {"id": "m", "title": "M", "company": "M", "location": "M", "description": None},
    ]
    parsed = json.loads(build_user_message("any", jobs))
    assert [j["id"] for j in parsed["jobs"]] == ["z", "a", "m"]


def test_build_user_message_does_not_mutate_input() -> None:
    """`build_user_message` does not mutate the caller's `jobs` sequence.

    The function may build a fresh list of dicts to enforce the
    5-key shape (e.g. drop extra keys from `to_dict()` output),
    but it MUST NOT mutate the caller's input.
    """
    original = {
        "id": "x",
        "title": "T",
        "company": "C",
        "location": "L",
        "description": None,
        "extra_field": "should be dropped or preserved without mutation",
    }
    jobs = [original]
    before_id = id(jobs[0])
    build_user_message("any", jobs)
    # The same dict object is still in the input.
    assert id(jobs[0]) == before_id
    # The original dict was not mutated (no keys added/removed).
    assert "extra_field" in jobs[0]
