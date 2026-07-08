"""Unit tests for the CV prompt's `parse_adapted_cv_response` parser
and the `AdaptedCV` template.

Mirrors the TypeScript frontend's `parser.test.ts` + `render-cv.test.ts`
so the Python and TypeScript pipelines stay in parity. The two
implementations MUST agree on:

- which fields the parser extracts (so a field added on one side
  shows up on the other),
- which sections the renderer draws,
- the order of those sections.

If a test here diverges from the TypeScript side, the byte-for-byte
parity check in the frontend's `prompts.test.ts` will fail too.
"""

from __future__ import annotations

from jobs_finder.infrastructure.cv._template import AdaptedCV
from jobs_finder.infrastructure.llm._cv_prompt import parse_adapted_cv_response


class TestParseAdaptedCVResponseCertifications:
    """The 'certifications' field is emitted by the LLM when the
    original CV has a 'Certificaciones' / 'Certificaciones y
    Competencias' / 'Licencias' / 'Formación Complementaria' section.
    The Python parser MUST surface it on the AdaptedCV dataclass —
    a previous regression dropped the field (and the rendered
    PDF lost the section)."""

    def test_extracts_certifications_array(self) -> None:
        raw = (
            '{"name": "Arturo", "certifications": ['
            '"Carné de conducir B y vehículo propio.",'
            '"Ultimate JavaScript - Arturo Alba - 2025-02-09",'
            '"Java SE Programmer Certification Preparation | NTT DATA / Oracle Training"'
            "]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert cv.certifications == [
            "Carné de conducir B y vehículo propio.",
            "Ultimate JavaScript - Arturo Alba - 2025-02-09",
            "Java SE Programmer Certification Preparation | NTT DATA / Oracle Training",
        ]

    def test_defaults_certifications_to_empty_list_when_missing(self) -> None:
        cv = parse_adapted_cv_response('{"name": "Ada"}')
        assert cv.certifications == []

    def test_defaults_certifications_to_empty_list_when_not_an_array(self) -> None:
        cv = parse_adapted_cv_response(
            '{"name": "Ada", "certifications": "not-an-array"}'
        )
        assert cv.certifications == []


class TestPromptCertificationsScopeRule:
    """The Python prompt must include the "CERTIFICATION in the name
    does not make it a cert" rule, mirroring the TypeScript side.
    A regression here would let the LLM put 'Java SE Programmer
    Certification Preparation' (which lives in the EXPERIENCIA
    section of the original CV, not in a top-level
    'Certificaciones' section) into the 'certifications' array."""

    def test_prompt_contains_certification_in_name_rule(self) -> None:
        from jobs_finder.infrastructure.llm._cv_prompt import (
            ADAPT_CV_SYSTEM_PROMPT,
        )

        assert (
            "CRITICAL — 'CERTIFICATION' IN THE NAME DOES NOT MAKE IT A CERT"
            in ADAPT_CV_SYSTEM_PROMPT
        )
        assert (
            "The 'certifications' array is reserved for items that come from a TOP-LEVEL"
            in ADAPT_CV_SYSTEM_PROMPT
        )


class TestParseAdaptedCVResponseThinkingStrip:
    """The M2.x / M3 model family emits a verbose `<think>...</think>`
    preamble before the JSON. The parser must strip the entire
    block (content + tags), not just the literal tag strings, so
    the JSON it tries to parse is not contaminated with
    'Let me analyze...' text. A previous bug stripped only the
    tags and the brace-substring strategy then picked the wrong
    braces from a JSON-shaped example inside the think block."""

    def test_strips_entire_think_block_with_content(self) -> None:
        # Properly closed think block — content + tags stripped,
        # JSON below parses cleanly.
        raw = (
            "<think>Let me analyze the CV carefully and produce JSON.</think>\n"
            '{"name": "Ada", "experience": [], "education": [],'
            ' "skills": ["TypeScript"], "languages": ["English"],'
            ' "certifications": []}'
        )
        cv = parse_adapted_cv_response(raw)
        assert cv.name == "Ada"
        assert cv.skills == ["TypeScript"]

    def test_strips_unclosed_think_block(self) -> None:
        # Degenerate case: the LLM hit max_tokens mid-thinking and
        # never emitted the closing tag. The parser should drop
        # everything from the open tag to end-of-string.
        raw = (
            "<think>Let me analyze...\n"
            '{"name": "Ada", "experience": [], "education": [],'
            ' "skills": [], "languages": []}'
        )
        # After stripping the unclosed think block, nothing useful
        # remains — the parser should fail cleanly with a ValueError.
        import pytest

        with pytest.raises(ValueError, match="not valid JSON"):
            parse_adapted_cv_response(raw)


class TestAdaptedCVTemplateCertifications:
    """The HTML template must surface the certifications section
    between 'Proyectos' and 'Habilidades' (same order as the
    TypeScript renderer)."""

    def test_certifications_section_renders_between_projects_and_skills(self) -> None:
        from jobs_finder.infrastructure.cv._template import ProjectEntry

        cv = AdaptedCV(
            name="Arturo",
            email="arturo@example.com",
            phone="+34 600 000 000",
            location="Málaga",
            summary="Senior engineer.",
            experience=[],
            education=[],
            projects=[ProjectEntry(name="V12-UI", description="React lib")],
            certifications=["Carné de conducir B.", "Ultimate JavaScript."],
            skills=["TypeScript"],
            languages=["Español"],
        )
        html = cv.to_html()
        # The certifications section title and content must be
        # present, AND it must appear AFTER the projects section
        # and BEFORE the skills section.
        cert_idx = html.index("Certificaciones")
        assert "Carné de conducir B." in html
        assert "Ultimate JavaScript." in html
        # 'Proyectos Personales' is the projects section title.
        projects_idx = html.index("Proyectos Personales")
        skills_idx = html.index("Habilidades")
        assert projects_idx < cert_idx < skills_idx

    def test_no_certifications_section_when_array_is_empty(self) -> None:
        cv = AdaptedCV(
            name="Arturo",
            email="arturo@example.com",
            phone="+34 600 000 000",
            location="Málaga",
            summary="Senior engineer.",
            experience=[],
            education=[],
            projects=[],
            certifications=[],
            skills=["TypeScript"],
            languages=["Español"],
        )
        html = cv.to_html()
        assert "Certificaciones" not in html


class TestAdaptedCVTemplatePhoto:
    """The HTML template must embed the photo in the header when
    `photo_base64` is set. A previous backend regression rendered
    the photo section even when no photo was extracted, and the
    `<img src="">` ended up as a broken image in the PDF."""

    def test_photo_renders_when_base64_is_set(self) -> None:
        cv = AdaptedCV(
            name="Arturo",
            email="arturo@example.com",
            phone="+34 600 000 000",
            location="Málaga",
            summary="Senior engineer.",
            experience=[],
            education=[],
            projects=[],
            certifications=[],
            skills=["TypeScript"],
            languages=["Español"],
            photo_base64="data:image/jpeg;base64,/9j/4AAQ",
        )
        html = cv.to_html()
        assert 'data:image/jpeg;base64,/9j/4AAQ' in html
        assert 'class="photo"' in html

    def test_no_photo_element_when_base64_is_none(self) -> None:
        cv = AdaptedCV(
            name="Arturo",
            email="arturo@example.com",
            phone="+34 600 000 000",
            location="Málaga",
            summary="Senior engineer.",
            experience=[],
            education=[],
            projects=[],
            certifications=[],
            skills=["TypeScript"],
            languages=["Español"],
        )
        html = cv.to_html()
        # No <img class="photo"...> tag when photo is None.
        assert 'class="photo"' not in html
