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

from jobs_finder.infrastructure.cv._template import (
    AdaptedCV,
    ProjectLink,
    derive_chip_label,
)
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
        cv = parse_adapted_cv_response('{"name": "Ada", "certifications": "not-an-array"}')
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
        assert "data:image/jpeg;base64,/9j/4AAQ" in html
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


# ===========================================================================
# T1/T2: ProjectLink dataclass + derive_chip_label helper
# (cv-project-links REQ-PJL-002 + §1.1 algorithm)
# ===========================================================================


class TestDeriveChipLabel:
    """The `derive_chip_label(url)` helper produces a short, human-readable
    label for a chip from the URL's hostname.

    Algorithm (per design §1.1):
      1. If the URL is unparseable, return "".
      2. Lowercase the hostname; strip a leading "www.".
      3. Look the hostname up in a KNOWN platform map.
      4. If not in the map, return the first label of the hostname,
         capitalized (e.g. "user.example.com" → "User").
      5. NEVER raise on bad input — always return a string.
    """

    def test_github_url_returns_github_label(self) -> None:
        assert derive_chip_label("https://github.com/user/v12-ui") == "GitHub"

    def test_gitlab_url_returns_gitlab_label(self) -> None:
        assert derive_chip_label("https://gitlab.com/user/project") == "GitLab"

    def test_bitbucket_url_returns_bitbucket_label(self) -> None:
        assert derive_chip_label("https://bitbucket.org/user/repo") == "Bitbucket"

    def test_npmjs_url_returns_npm_label(self) -> None:
        assert derive_chip_label("https://www.npmjs.com/package/react") == "npm"

    def test_storybook_url_returns_storybook_label(self) -> None:
        assert derive_chip_label("https://storybook.js.org/?path=/story/welcome") == "Storybook"

    def test_youtube_url_returns_youtube_label(self) -> None:
        assert derive_chip_label("https://www.youtube.com/watch?v=abc") == "YouTube"

    def test_youtu_be_short_url_returns_youtube_label(self) -> None:
        assert derive_chip_label("https://youtu.be/abc123") == "YouTube"

    def test_linkedin_url_returns_linkedin_label(self) -> None:
        assert derive_chip_label("https://www.linkedin.com/in/arturo-alba") == "LinkedIn"

    def test_strips_www_prefix_for_known_platforms(self) -> None:
        # The "www." prefix is dropped before the KNOWN-map lookup so
        # "https://www.github.com/..." and "https://github.com/..." both
        # map to "GitHub".
        assert derive_chip_label("https://www.github.com/x/y") == "GitHub"

    def test_unknown_hostname_returns_first_label_capitalized(self) -> None:
        # Custom domain — fall back to first label of the hostname,
        # capitalized. This handles "user.ar2d2.dev" → "User" and
        # "docs.example.com" → "Docs".
        assert derive_chip_label("https://user.ar2d2.dev/blog") == "User"
        assert derive_chip_label("https://docs.example.com/path") == "Docs"

    def test_empty_url_returns_empty_string(self) -> None:
        assert derive_chip_label("") == ""

    def test_invalid_url_returns_empty_string(self) -> None:
        # No scheme → not a URL. Don't crash, return "".
        assert derive_chip_label("not a url") == ""

    def test_http_and_https_produce_same_label(self) -> None:
        assert derive_chip_label("http://github.com/x/y") == "GitHub"
        assert derive_chip_label("https://github.com/x/y") == "GitHub"

    def test_url_with_port_returns_first_label(self) -> None:
        # The hostname is what we parse, so a port in the URL doesn't
        # affect the label.
        assert derive_chip_label("https://example.com:8080/path") == "Example"


class TestProjectLinkDataclass:
    """The `ProjectLink` dataclass is a pair `(label, url)` used to
    surface one clickable chip per project."""

    def test_constructs_with_label_and_url(self) -> None:
        link = ProjectLink(label="GitHub", url="https://github.com/user/v12-ui")
        assert link.label == "GitHub"
        assert link.url == "https://github.com/user/v12-ui"

    def test_equality_on_label_and_url(self) -> None:
        # Used by tests + the parser to dedupe identical links.
        a = ProjectLink(label="GitHub", url="https://github.com/x/y")
        b = ProjectLink(label="GitHub", url="https://github.com/x/y")
        assert a == b

    def test_inequality_on_different_label(self) -> None:
        a = ProjectLink(label="GitHub", url="https://x.com/y")
        b = ProjectLink(label="Demo", url="https://x.com/y")
        assert a != b


# ===========================================================================
# T4: parse_adapted_cv_response accepts new `links[]` shape and falls back
# from legacy `url` (REQ-PJL-001 + REQ-PJL-002)
# ===========================================================================


class TestParseAdaptedCVResponseProjectLinks:
    """The parser must:
    - accept a project with a non-empty `links` array (REQ-PJL-001),
    - fall back from legacy `url` to `links` when `links` is empty
      or missing (REQ-PJL-002 backward compat),
    - prefer `links` over `url` when BOTH are present (REQ-PJL-002),
    - cap `links` at 8 entries (REQ-PJL-001 scenario "over-cap is capped"),
    - drop entries with empty `url` or non-http(s) scheme.
    """

    def test_parses_new_links_array_with_label_and_url(self) -> None:
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"],'
            '"links":['
            '{"label":"GitHub","url":"https://github.com/user/v12-ui"},'
            '{"label":"Storybook","url":"https://storybook.js.org/v12-ui"},'
            '{"label":"npm","url":"https://www.npmjs.com/package/v12-ui"}'
            "]"
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects) == 1
        assert len(cv.projects[0].links) == 3
        assert cv.projects[0].links[0].label == "GitHub"
        assert cv.projects[0].links[0].url == "https://github.com/user/v12-ui"
        assert cv.projects[0].links[1].label == "Storybook"
        assert cv.projects[0].links[2].label == "npm"

    def test_falls_back_from_legacy_url_synthesizing_one_link(self) -> None:
        # Legacy `url` is the only signal — parser synthesizes a single
        # entry with the label derived from the hostname.
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"],'
            '"url":"https://github.com/user/v12-ui"'
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects) == 1
        assert len(cv.projects[0].links) == 1
        assert cv.projects[0].links[0].label == "GitHub"
        assert cv.projects[0].links[0].url == "https://github.com/user/v12-ui"

    def test_prefers_links_over_legacy_url_when_both_present(self) -> None:
        # Both shapes present: the new `links` array is authoritative,
        # the legacy `url` is ignored.
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"],'
            '"url":"https://example.com/should-be-ignored",'
            '"links":['
            '{"label":"GitHub","url":"https://github.com/user/v12-ui"},'
            '{"label":"Storybook","url":"https://storybook.js.org/v12-ui"}'
            "]"
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects[0].links) == 2
        # The legacy `url` is NOT in the synthesized list.
        assert all("should-be-ignored" not in link.url for link in cv.projects[0].links)

    def test_neither_links_nor_url_yields_empty_links_list(self) -> None:
        # A project with no URL info at all: links = [] (not a fallback).
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"]'
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects) == 1
        assert cv.projects[0].links == []

    def test_drops_links_with_empty_url(self) -> None:
        # A link entry with an empty `url` is dropped (not rendered,
        # not in the cap).
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"],'
            '"links":['
            '{"label":"GitHub","url":"https://github.com/user/v12-ui"},'
            '{"label":"","url":""}'
            "]"
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects[0].links) == 1
        assert cv.projects[0].links[0].label == "GitHub"

    def test_drops_links_with_non_http_scheme(self) -> None:
        # ftp://, javascript:, file://, etc. are dropped.
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"],'
            '"links":['
            '{"label":"GitHub","url":"https://github.com/user/v12-ui"},'
            '{"label":"FTP","url":"ftp://files.example.com/v12-ui"}'
            "]"
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects[0].links) == 1
        assert cv.projects[0].links[0].label == "GitHub"

    def test_caps_links_at_eight_per_project(self) -> None:
        # REQ-PJL-001 scenario "over-cap is capped": 9 entries → 8.
        links = ",".join(f'{{"label":"L{i}","url":"https://example.com/{i}"}}' for i in range(9))
        raw = (
            '{"name":"Arturo","projects":[{'
            '"name":"V12-UI",'
            '"description":"React UI lib",'
            '"technologies":["React"],'
            f'"links":[{links}]'
            "}]}"
        )
        cv = parse_adapted_cv_response(raw)
        assert len(cv.projects[0].links) == 8


# ===========================================================================
# T5: _render_projects emits chip row (REQ-PJL-003 + REQ-PJL-004)
# ===========================================================================


class TestRenderProjectsChipRow:
    """The HTML template's `_render_projects` (and thus `to_html`)
    must:
      - emit a chip row when the project has 1+ links,
      - emit ZERO chip rows when the project has no links,
      - each chip is a separate `<a>` with a distinct `href`,
      - chip CSS class `project-link-chip` is applied,
      - the legacy `url` field (no `links`) still renders as a chip
        with the hostname-derived label.
    """

    def _project_html(self, project: ProjectLink | None = None) -> str:
        from jobs_finder.infrastructure.cv._template import ProjectEntry

        proj = ProjectEntry(name="V12-UI", description="React UI lib")
        if project is not None:
            proj.links = [project]
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        return cv.to_html()

    def test_multi_link_project_renders_three_distinct_chips(self) -> None:
        from jobs_finder.infrastructure.cv._template import ProjectEntry

        proj = ProjectEntry(
            name="V12-UI",
            description="React UI lib",
            links=[
                ProjectLink(label="GitHub", url="https://github.com/user/v12-ui"),
                ProjectLink(label="Storybook", url="https://storybook.js.org/v12-ui"),
                ProjectLink(label="npm", url="https://www.npmjs.com/package/v12-ui"),
            ],
        )
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        html = cv.to_html()
        # Three distinct chip anchors, each with a distinct href.
        for url in [
            "https://github.com/user/v12-ui",
            "https://storybook.js.org/v12-ui",
            "https://www.npmjs.com/package/v12-ui",
        ]:
            assert f'href="{url}"' in html
        # Each chip carries the project-link-chip class.
        assert html.count('class="project-link-chip"') == 3

    def test_single_link_project_renders_one_chip(self) -> None:
        from jobs_finder.infrastructure.cv._template import ProjectEntry

        proj = ProjectEntry(
            name="V12-UI",
            description="React UI lib",
            links=[ProjectLink(label="GitHub", url="https://github.com/user/v12-ui")],
        )
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        html = cv.to_html()
        assert html.count('class="project-link-chip"') == 1
        assert 'href="https://github.com/user/v12-ui"' in html

    def test_no_link_project_renders_no_chip_row(self) -> None:
        from jobs_finder.infrastructure.cv._template import ProjectEntry

        proj = ProjectEntry(name="V12-UI", description="React UI lib")
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        html = cv.to_html()
        # No chip element rendered (the CSS class definition lives in
        # the stylesheet and would always be present, so we check for
        # the actual `<a class="project-link-chip">` element instead).
        assert '<a class="project-link-chip"' not in html
        # And no chip-row container either.
        assert 'class="project-links-row"' not in html

    def test_label_only_chip_renders_as_span(self) -> None:
        # REGRESSION (cv-link-preservation follow-up): when the LLM
        # emits a link with `label` set but `url: ""` (because the
        # original CV had a visual label but no real hyperlink
        # annotation), the renderer MUST still draw a chip — as a
        # label-only `<span>`, NOT as an empty-href `<a>` that would
        # render as a link to the current page.
        from jobs_finder.infrastructure.cv._template import ProjectEntry, ProjectLink

        proj = ProjectEntry(
            name="V12-UI",
            description="React UI lib",
            links=[
                ProjectLink(label="Github link", url=""),
                ProjectLink(label="Storybook link", url=""),
            ],
        )
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        html = cv.to_html()
        # Two label-only chip spans rendered (no href, no <a>).
        assert html.count('class="project-link-chip project-link-chip--no-url"') == 2
        assert '<a class="project-link-chip"' not in html
        # Both labels are present in the HTML.
        assert "Github link" in html
        assert "Storybook link" in html
        # Chip-row container is present.
        assert 'class="project-links-row"' in html

    def test_mixed_url_and_label_only_chips(self) -> None:
        # A project with MIXED clickable + label-only chips renders
        # both correctly: real URLs as `<a>` (clickable), empty URLs
        # as `<span>` (label-only).
        from jobs_finder.infrastructure.cv._template import ProjectEntry, ProjectLink

        proj = ProjectEntry(
            name="V12-UI",
            description="React UI lib",
            links=[
                ProjectLink(label="GitHub", url="https://github.com/user/v12-ui"),
                ProjectLink(label="Storybook link", url=""),
            ],
        )
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        html = cv.to_html()
        # 1 clickable <a> chip + 1 label-only <span> chip.
        assert html.count('<a class="project-link-chip"') == 1
        assert html.count('class="project-link-chip project-link-chip--no-url"') == 1
        assert 'href="https://github.com/user/v12-ui"' in html

    def test_legacy_url_fallback_renders_chip_with_derived_label(self) -> None:
        # A project with ONLY a legacy `url` (no `links`) renders
        # exactly one chip with the hostname-derived label.
        from jobs_finder.infrastructure.cv._template import ProjectEntry

        proj = ProjectEntry(
            name="V12-UI",
            description="React UI lib",
            url="https://github.com/user/v12-ui",
        )
        cv = AdaptedCV(
            name="Arturo",
            email="a@b.c",
            phone="+34",
            location="M",
            summary="S",
            experience=[],
            education=[],
            projects=[proj],
            certifications=[],
            skills=[],
            languages=[],
        )
        html = cv.to_html()
        # One chip, with the derived label.
        assert html.count('class="project-link-chip"') == 1
        assert ">GitHub<" in html
        assert 'href="https://github.com/user/v12-ui"' in html
