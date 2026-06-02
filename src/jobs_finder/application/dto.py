"""Application-layer data transfer objects (DTOs).

Plain dataclasses, not Pydantic — Pydantic lives only at the API edge.
The presentation layer is responsible for validating user input and
constructing these DTOs; the application trusts what it receives.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchLinkedInInput:
    """Validated input for the LinkedIn job search use case.

    Spec: REQ-009. `limit` defaults to 20 here AND on the Pydantic schema
    at the presentation boundary; the use case does not re-validate.
    """

    keywords: str
    location: str
    limit: int = 20


@dataclass(frozen=True, slots=True)
class SearchIndeedInput:
    """Validated input for the Indeed job search use case.

    Spec: REQ-I-004. `limit` defaults to 20 here AND on the Pydantic
    schema at the presentation boundary; the use case does not
    re-validate. The shape mirrors `SearchLinkedInInput` 1:1 so the
    presentation layer can use the same generic binding for both
    sources.
    """

    keywords: str
    location: str
    limit: int = 20
