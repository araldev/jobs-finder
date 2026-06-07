"""Spanish system prompt + user message builder for the chat filter (T-009 of `ai-chat-filter`).

Spec: REQ-LLM-004 (5 invariant rules), REQ-LLM-001 (request body shape).

`SYSTEM_PROMPT` is the Spanish system prompt that drives the LLM
behavior. The text is from `sdd/ai-chat-filter/explore` §5
(verbatim) and embeds the 5 REQ-LLM-004 rules:

  1. Spanish — the model is told it is a Spanish-language assistant.
  2. No-ID-invention — "SOLO puedes devolver IDs que aparezcan en la
     lista. NUNCA inventes, modifiques ni añadas IDs."
  3. Favor-recall — "Si dudas entre incluir o excluir una oferta,
     INCLÚYELA."
  4. No-data-assumption — "no asumas experiencia, salario,
     modalidad remota" (and other fields not in the offer).
  5. JSON shape — the response MUST be exactly
     `{"matching_ids": [...], "explanation": "..."}` with no
     surrounding prose or markdown fences.

`build_user_message(intent, jobs)` builds the user-side half of
the request: a JSON-serialized object
`{"intent": "...", "jobs": [...]}`. Each job is a dict with the
5 keys `id, title, company, location, description` — the LLM
needs all 5 to filter on them. The `description` field is `null`
when the source has no description (per the spec's "no-assumption"
rule: an empty string would be interpreted as "explicitly empty
description" rather than "no information available").

The user message is sent as a JSON STRING (not a multi-part
message) so the LLM sees the structure verbatim. The OpenAI-
compatible chat-completions endpoint accepts a `content` string
per message, and a JSON string is the standard way to pass
structured input to a model that has been prompt-engineered for
JSON output.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

# Source: sdd/ai-chat-filter/explore §5. Verbatim from the
# exploration document, including the 5 REQ-LLM-004 rules. The
# `\` continuation + triple-quote-string + leading `\` ensures
# the rendered string is a single block of text (no leading
# newline). DO NOT edit the wording without updating
# `tests/unit/test_llm_prompt.py` (the 5 invariant checks
# string-grep the keywords).
SYSTEM_PROMPT: str = """\
Eres un asistente que filtra una lista de ofertas de trabajo según la \
intención del usuario. Recibirás dos cosas:

1. Una lista de ofertas de trabajo en formato JSON, cada una con los \
campos `id`, `title`, `company`, `location` y, opcionalmente, \
`description` (resumen corto extraído de la página de búsqueda). Si \
`description` está vacío o ausente, NO asumas experiencia, salario, \
modalidad remota, ni ningún otro dato que no esté en `title` + \
`company` + `location`.
2. La intención del usuario en lenguaje natural (por ejemplo: \
"quiero un puesto junior en Madrid", "solo remoto", "excluye \
consultoras", "pago > 40k", "experiencia mínima 3 años en Python").

Tu tarea es devolver los IDs de las ofertas que SÍ coinciden con la \
intención del usuario.

Reglas estrictas (léelas todas antes de responder):

- SOLO puedes devolver IDs que aparezcan en la lista de entrada. \
NUNCA inventes, modifiques ni añadas IDs. Si una oferta no está en \
la lista, no puede estar en tu respuesta.
- Si dudas entre incluir o excluir una oferta, INCLÚYELA. \
Preferimos falsos positivos (mostrar algo irrelevante) a falsos \
negativos (ocultar algo relevante). El usuario puede descartar \
manualmente, pero no puede recuperar lo que no se le muestra.
- NO asumas datos que no estén en la oferta. Si el usuario pide \
"remoto" y la oferta no menciona modalidad, trátala como \
"sin información" y NO la filtres por ese criterio (déjala pasar).
- Si la intención del usuario es vacía, absurda, o no se puede \
interpretar, devuelve `matching_ids: []` y explica brevemente.
- Tu respuesta DEBE ser un objeto JSON válido con exactamente esta \
forma (sin texto antes ni después, sin bloques de código markdown):

```json
{
  "matching_ids": ["id1", "id5", "id12"],
  "explanation": "Una o dos frases en español explicando brevemente \
por qué estas ofertas coinciden con la intención del usuario."
}
```

- `matching_ids` es una lista de strings (los IDs exactos de la lista \
de entrada). Si ninguna coincide, devuelve la lista vacía `[]`.
- `explanation` SIEMPRE debe estar presente, incluso si la lista \
está vacía (explica por qué ninguna coincide, o di "ninguna oferta \
coincide con tu intención" si es el caso).
- No devuelvas texto fuera del JSON. Tu respuesta completa es \
EXCLUSIVAMENTE el objeto JSON.\
"""


# The 5 keys per job. The defensive LLM caller in T-011 forwards
# these 5 keys to the model; any extra keys (e.g. `url`, `posted_at`)
# are dropped here so the user message stays minimal and the
# model is not distracted by fields it cannot filter on.
_JOB_KEYS: tuple[str, ...] = ("id", "title", "company", "location", "description")


def _job_to_dict(job: Mapping[str, Any]) -> dict[str, Any]:
    """Project a job mapping to the 5-key LLM-facing dict.

    `description` is preserved as-is — `None` becomes JSON
    `null` (per the no-assumption rule), and any string value
    is forwarded verbatim. Unknown extra keys are dropped so the
    user message stays focused on the filter-relevant fields.

    The function does NOT mutate the input mapping. Each call
    produces a fresh `dict`.
    """
    return {key: job.get(key) for key in _JOB_KEYS}


def build_user_message(intent: str, jobs: Sequence[Mapping[str, Any]]) -> str:
    """Build the user-side request body as a JSON-serialized string.

    The output is a single-line JSON string of the shape
    `{"intent": "<intent>", "jobs": [{"id", "title", "company",
    "location", "description"}, ...]}`. The LLM sees this string
    verbatim in the OpenAI-compatible `messages[user].content`
    field; the prompt instructs it to return a matching
    `{"matching_ids": [...], "explanation": "..."}` shape.

    Args:
        intent: The user's natural-language intent (e.g.
            "ingeniero < 2 años en Málaga"). Pre-normalized by
            the chat route via NFC + casefold + strip (per the
            preflight cache-key normalization decision).
        jobs: A sequence of job mappings (typically the result
            of `Job.to_dict()` per job). Each mapping MUST have
            the 5 keys (`id, title, company, location,
            description`); `description` is `None` when the
            source has no description. Unknown extra keys are
            silently dropped (the LLM does not need them).

    Returns:
        A single-line JSON string parseable by `json.loads`.
        `description=None` is serialized as `null` (not `""`).
    """
    payload: dict[str, Any] = {
        "intent": intent,
        "jobs": [_job_to_dict(j) for j in jobs],
    }
    # `ensure_ascii=False` keeps Spanish characters (accents, ñ)
    # as-is in the rendered string. The LLM endpoint accepts
    # UTF-8 input, and the escape sequences would add noise
    # without value.
    # `separators=(",", ":")` is the compact form (no spaces)
    # which keeps the prompt minimal — the model sees a tight
    # JSON document, not a pretty-printed one.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
