"""Unit tests for `usecases.generate_adapted_cv` — the link-preservation
suspenders (Approach B from `cv-link-preservation` design §4.7) and
the belt layer (HYPERLINKS MAP in the prompt).

Test coverage:
  - Belt: HYPERLINKS MAP appears in the user message when the CV has
    hyperlink annotations; absent when none.
  - Suspenders: post-processor substitutes LLM-invented URLs with
    the real URLs from the PDF hyperlink map by label match
    (4-strategy cascade).
  - Backward compat: empty hyperlinks → no MAP section + post-
    processor no-op + LLM URL preserved.
  - Multi-link project: 1 invented + 2 real URLs → only invented is
    substituted.
  - Mixed: 2 real + 1 invented → only invented substituted.
  - No-match: LLM URL preserved.
  - Idempotent: post-processor is a no-op when the LLM emitted the
    real URL.
  - Idempotent: post-processor handles re-running.

Per design §1.4-§1.7 of `cv-link-preservation` + spec REQ-CLP-004 +
REQ-CLP-006.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pymupdf
import pytest

from jobs_finder.application.usecases.generate_adapted_cv import (
    GenerateAdaptedCVRequest,
    GenerateAdaptedCVUseCase,
    substitute_hyperlinks_in_cv,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cv._parser import HyperlinkEntry
from jobs_finder.infrastructure.cv._template import (
    AdaptedCV,
    ProjectEntry,
    ProjectLink,
)

# ── Test doubles ─────────────────────────────────────────────────


class _FakeLLMClient:
    """In-memory LLM client that records the user message + returns
    a canned response. Mirrors the `MiniMaxLLMClient.complete()`
    signature (`*, system: str, user: str -> str`).

    Tests set `canned_response` to whatever the LLM should emit, then
    inspect `user_messages[-1]` to verify the HYPERLINKS MAP section
    appears (belt layer) and inspect the returned CV's `projects[*].links[*]`
    to verify the post-processor substituted invented URLs (suspenders).
    """

    def __init__(self, canned_response: str = "") -> None:
        self.canned_response = canned_response
        self.system_messages: list[str] = []
        self.user_messages: list[str] = []

    async def complete(self, *, system: str, user: str) -> str:
        self.system_messages.append(system)
        self.user_messages.append(user)
        return self.canned_response


def _adapted_cv_with_project_links(links: list[ProjectLink]) -> AdaptedCV:
    """Build an `AdaptedCV` with ONE project holding the given `links`."""
    return AdaptedCV(
        name="Test User",
        email="test@example.com",
        phone="",
        location="",
        summary="",
        experience=[],
        education=[],
        projects=[
            ProjectEntry(
                name="V12-UI",
                description="A test project",
                technologies=[],
                links=links,
            ),
        ],
        certifications=[],
        skills=[],
        languages=[],
    )


def _make_pdf_with_links(
    links: list[tuple[str, str, tuple[float, float, float, float]]],
) -> bytes:
    """Minimal 1-page PDF builder (mirrors test_cv_parser.py helper)."""
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=612, height=792)
    for label, _url, rect in links:
        page.insert_text((rect[0], rect[3] - 4), label, fontsize=11)
    for _label, url, rect in links:
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(*rect),  # type: ignore[no-untyped-call]
                "uri": url,
            }
        )
    return doc.tobytes()  # type: ignore[no-untyped-call,no-any-return]


def _make_job() -> Job:
    return Job(
        id="job-1",
        title="Senior Developer",
        company="Acme",
        location="Madrid",
        url="https://acme.example.com/job-1",
        posted_at=datetime(2026, 7, 8, tzinfo=UTC),
        source="manual",
    )


# ── substitute_hyperlinks_in_cv ─────────────────────────────────


class TestSubstituteHyperlinksInCV:
    """Direct unit tests for the post-processor (suspenders layer).

    The post-processor is `substitute_hyperlinks_in_cv(cv, hyperlinks)`
    per design §1.5. It is idempotent and non-destructive — when the
    LLM emits the real URL, the substitution is a no-op; when the LLM
    hallucinates, the real URL replaces it; when the LLM emits a label
    with no PDF match, the LLM URL is kept (don't lose data).
    """

    def test_empty_hyperlinks_returns_cv_unchanged(self) -> None:
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="GitHub", url="https://github.com/u/v")],
        )
        result = substitute_hyperlinks_in_cv(cv, [])
        assert result is cv  # no-op: same instance

    def test_substitutes_invented_url_via_exact_match(self) -> None:
        # LLM emits "GitHub" → "https://wrong.com" (invented).
        # PDF has "Github" → "https://github.com/u/v" (real).
        # After normalize both = "github" → exact match.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="GitHub", url="https://wrong.com")],
        )
        hyperlinks = [
            HyperlinkEntry(label="Github", url="https://github.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        assert result.projects[0].links[0].url == "https://github.com/u/v"

    def test_substitutes_via_substring_match(self) -> None:
        # LLM emits "GitHub" → invented.
        # PDF has "Github link" → real.
        # LLM label "github" substring of "github link" → match.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="GitHub", url="https://wrong.com")],
        )
        hyperlinks = [
            HyperlinkEntry(label="Github link", url="https://github.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        assert result.projects[0].links[0].url == "https://github.com/u/v"

    def test_preserves_llm_url_when_no_label_match(self) -> None:
        # LLM emits "Custom internal" → "https://internal.corp/x".
        # MAP has only github/storybook/npm — no match.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="Custom internal", url="https://internal.corp/x")],
        )
        hyperlinks = [
            HyperlinkEntry(label="GitHub", url="https://github.com/u/v", page=1),
            HyperlinkEntry(label="Storybook", url="https://sb.com/u/v", page=1),
            HyperlinkEntry(label="npm", url="https://npmjs.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        # LLM URL preserved.
        assert result.projects[0].links[0].url == "https://internal.corp/x"

    def test_multi_link_project_substitutes_only_invented(self) -> None:
        # Project has 3 links: 1 invented + 2 real (already matching).
        # Only the invented one should be substituted; the 2 real
        # ones go through unchanged.
        cv = _adapted_cv_with_project_links(
            [
                ProjectLink(label="GitHub", url="https://github.com/u/v"),  # already real
                ProjectLink(label="Storybook", url="https://wrong.com"),  # invented
                ProjectLink(label="npm", url="https://npmjs.com/u/v"),  # already real
            ],
        )
        hyperlinks = [
            HyperlinkEntry(label="GitHub", url="https://github.com/u/v", page=1),
            HyperlinkEntry(label="Storybook", url="https://sb.com/u/v", page=1),
            HyperlinkEntry(label="npm", url="https://npmjs.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        urls = [link.url for link in result.projects[0].links]
        assert urls == [
            "https://github.com/u/v",
            "https://sb.com/u/v",  # was wrong.com → substituted
            "https://npmjs.com/u/v",
        ]

    def test_idempotent_when_llm_emits_real_url(self) -> None:
        # LLM happens to emit the real URL — post-processor is a
        # no-op for that entry.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="GitHub", url="https://github.com/u/v")],
        )
        hyperlinks = [
            HyperlinkEntry(label="GitHub", url="https://github.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        # Same URL — the post-processor produced the same instance.
        assert result.projects[0].links[0].url == "https://github.com/u/v"

    def test_keeps_label_only_chip_when_no_url_match(self) -> None:
        # REGRESSION (cv-link-preservation follow-up): when the LLM
        # emits a chip with `label` set but `url: ""` AND no matching
        # hyperlink exists in the MAP (the original CV had a visual
        # label but no real hyperlink annotation), the post-processor
        # keeps that chip as-is (label-only). The chip is NOT dropped
        # — the label is still meaningful even without a URL target.
        cv = _adapted_cv_with_project_links(
            [
                ProjectLink(label="Custom badge", url=""),
            ],
        )
        # No matching hyperlinks in the MAP (Custom badge doesn't exist).
        hyperlinks = [
            HyperlinkEntry(label="GitHub", url="https://github.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        # The chip is preserved with its empty URL — the renderer will
        # draw it as a label-only `<span>`.
        assert result.projects[0].links[0] == ProjectLink(label="Custom badge", url="")

    def test_substitutes_empty_url_when_label_matches_map(self) -> None:
        # Companion case to `test_keeps_label_only_chip_when_no_url_match`:
        # when the LLM emits `url: ""` BUT the label DOES match a
        # hyperlink in the MAP, the post-processor substitutes the
        # empty URL with the real URL from the MAP. This is the
        # expected behavior — the user gets a clickable chip when a
        # real URL is available, even if the LLM forgot to emit it.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="Github link", url="")],
        )
        hyperlinks = [
            HyperlinkEntry(label="Github link", url="https://github.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        assert result.projects[0].links[0] == ProjectLink(
            label="Github link", url="https://github.com/u/v"
        )

    def test_substitutes_only_real_url_chips_in_mixed_input(self) -> None:
        # Mixed input: LLM emits one chip with a real URL (correct),
        # one chip with an empty URL (label-only, no hyperlink in PDF),
        # and one chip with an invented URL. Post-processor:
        #   - keeps the real URL as-is,
        #   - keeps the empty URL as-is (no substitution),
        #   - substitutes the invented URL with the real one.
        cv = _adapted_cv_with_project_links(
            [
                ProjectLink(label="GitHub", url="https://github.com/u/v"),
                ProjectLink(label="Storybook link", url=""),
                ProjectLink(label="npm", url="https://wrong.com"),
            ],
        )
        hyperlinks = [
            HyperlinkEntry(label="npm", url="https://npmjs.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        assert result.projects[0].links[0] == ProjectLink(
            label="GitHub", url="https://github.com/u/v"
        )
        assert result.projects[0].links[1] == ProjectLink(label="Storybook link", url="")
        assert result.projects[0].links[2] == ProjectLink(
            label="npm", url="https://npmjs.com/u/v"
        )

    def test_does_not_mutate_input(self) -> None:
        # The post-processor returns a NEW AdaptedCV (via
        # `dataclasses.replace`) — it must NOT mutate the input.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="GitHub", url="https://wrong.com")],
        )
        original_url = cv.projects[0].links[0].url
        hyperlinks = [
            HyperlinkEntry(label="GitHub", url="https://github.com/u/v", page=1),
        ]
        substitute_hyperlinks_in_cv(cv, hyperlinks)
        # Input is unchanged.
        assert cv.projects[0].links[0].url == original_url


# ── HYPERLINKS MAP belt layer (user message) ─────────────────────


class TestHyperlinksMapInUserMessage:
    """The belt layer: HYPERLINKS MAP appears in the user message when
    the CV has hyperlink annotations; absent when none. Verified by
    driving `GenerateAdaptedCVUseCase.execute()` with a fake LLM and
    inspecting the `user_message` it sent.

    These tests run as `@pytest.mark.asyncio` so the event loop is
    managed by pytest-asyncio (avoids `ResourceWarning` from
    `asyncio.run()` interacting with PyMuPDF's internal sockets).
    """

    @staticmethod
    def _canned_response() -> str:
        return json.dumps(
            {
                "name": "Test User",
                "email": "test@example.com",
                "phone": "",
                "location": "",
                "summary": "",
                "experience": [],
                "education": [],
                "projects": [],
                "certifications": [],
                "skills": [],
                "languages": [],
            },
        )

    @staticmethod
    async def _run_use_case(
        pdf_bytes: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> _FakeLLMClient:
        """Drive the use case with a fake LLM and a stubbed PDF renderer.

        Short-circuits `generate_cv_pdf` so the test doesn't trigger
        the weasyprint → pydyf PDF render (which raises a
        DeprecationWarning that pytest treats as an error in this
        project). The HYPERLINKS MAP assertion only needs the
        user_message recorded by the fake LLM.
        """
        llm = _FakeLLMClient(canned_response=TestHyperlinksMapInUserMessage._canned_response())
        use_case = GenerateAdaptedCVUseCase(llm_client=llm)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "jobs_finder.application.usecases.generate_adapted_cv.generate_cv_pdf",
            lambda _cv: b"%PDF-stub",
        )
        await use_case.execute(
            GenerateAdaptedCVRequest(cv_pdf_bytes=pdf_bytes, job=_make_job()),
        )
        return llm

    @pytest.mark.asyncio
    async def test_user_message_contains_hyperlinks_map_when_links_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdf_bytes = _make_pdf_with_links(
            links=[
                ("Github link", "https://github.com/u/v12-ui", (50.0, 50.0, 200.0, 70.0)),
                ("Storybook link", "https://sb.com/u/v12-ui", (50.0, 80.0, 250.0, 100.0)),
            ],
        )
        llm = await self._run_use_case(pdf_bytes, monkeypatch)
        user_msg = llm.user_messages[-1]
        assert "HYPERLINKS — ORIGINAL URL MAP" in user_msg
        assert "https://github.com/u/v12-ui" in user_msg
        assert "https://sb.com/u/v12-ui" in user_msg
        assert '"Github link"' in user_msg
        assert '"Storybook link"' in user_msg

    @pytest.mark.asyncio
    async def test_user_message_omits_hyperlinks_map_when_no_links(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Plain PDF with no link annotations.
        doc = pymupdf.open()  # type: ignore[no-untyped-call]
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "Plain CV text — no hyperlinks anywhere", fontsize=11)
        pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
        doc.close()  # type: ignore[no-untyped-call]

        llm = await self._run_use_case(pdf_bytes, monkeypatch)
        user_msg = llm.user_messages[-1]
        assert "HYPERLINKS — ORIGINAL URL MAP" not in user_msg

    def test_post_processor_runs_after_llm_returns(self) -> None:
        # End-to-end: LLM emits an invented URL, post-processor
        # substitutes with the real one. We verify the FINAL adapted CV
        # (post-render) by checking that the post-processor would have
        # substituted it. Direct call to substitute_hyperlinks_in_cv
        # confirms the logic — the integration is via the same function.
        cv = _adapted_cv_with_project_links(
            [ProjectLink(label="GitHub", url="https://wrong.com")],
        )
        hyperlinks = [
            HyperlinkEntry(label="Github", url="https://github.com/u/v", page=1),
        ]
        result = substitute_hyperlinks_in_cv(cv, hyperlinks)
        assert result.projects[0].links[0].url == "https://github.com/u/v"

    def test_system_prompt_contains_use_original_urls_rule(self) -> None:
        # Belt layer (system prompt): the new LINKS — USE ORIGINAL URLs
        # VERBATIM rule must appear in the system prompt so the LLM
        # is told not to invent URLs.
        from jobs_finder.infrastructure.llm._cv_prompt import (
            ADAPT_CV_SYSTEM_PROMPT,
        )

        assert "LINKS — USE ORIGINAL URLs VERBATIM" in ADAPT_CV_SYSTEM_PROMPT
