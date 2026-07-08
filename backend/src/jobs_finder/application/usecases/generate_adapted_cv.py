"""Generate an adapted CV for a specific job description.

1. Extract text + hyperlinks from the uploaded PDF (pymupdf)
2. Extract photo if present (pymupdf)
3. Send CV text + HYPERLINKS MAP + job description to MiniMax LLM
   (the HYPERLINKS MAP tells the LLM the REAL URLs from the PDF's
   link annotations — the belt layer)
4. LLM returns structured adapted CV JSON
5. Substitute any LLM-invented URLs with the REAL URLs from the PDF
   hyperlink map (suspenders layer — label-based matching)
6. Render as HTML + photo (if available) + weasyprint → PDF binary
7. Return PDF bytes
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...domain.exceptions import JobSearchError
from ...domain.job import Job
from ...infrastructure.cv._generator import generate_cv_pdf
from ...infrastructure.cv._link_matcher import build_url_map, find_url_for_label
from ...infrastructure.cv._parser import (
    CVData,
    HyperlinkEntry,
    extract_cv_data,
    extract_cv_image,
)
from ...infrastructure.cv._template import (
    AdaptedCV,
    ProjectEntry,
    ProjectLink,
)
from ...infrastructure.llm._client import MiniMaxLLMClient
from ...infrastructure.llm._cv_prompt import (
    ADAPT_CV_SYSTEM_PROMPT,
    build_adapt_cv_user_message,
    parse_adapted_cv_response,
)


@dataclass
class GenerateAdaptedCVRequest:
    """Request to generate an adapted CV."""

    cv_pdf_bytes: bytes
    job: Job


@dataclass
class GenerateAdaptedCVResult:
    """Result of generating an adapted CV."""

    pdf_bytes: bytes
    filename: str


class CVAdaptationError(JobSearchError):
    """Raised when CV adaptation fails."""


def substitute_hyperlinks_in_cv(
    cv: AdaptedCV,
    hyperlinks: list[HyperlinkEntry],
) -> AdaptedCV:
    """Replace LLM-invented URLs in `cv.projects[].links[]` with the
    real URLs from the PDF hyperlink map (by label match).

    Per design §1.5 of `cv-link-preservation`:
      - When `hyperlinks` is empty → returns `cv` unchanged (no-op,
        backward compat — REQ-CLP-006).
      - Otherwise: builds `url_map = {normalized_label: url}` and walks
        each `project.links[*]` entry. For each entry, looks up the
        real URL via `find_url_for_label` (4-strategy cascade: exact →
        substring either way → token Jaccard > 0.5). On a match,
        substitutes the URL; on no match, keeps the LLM's URL
        (don't lose data the LLM already had).
      - Pure: returns a NEW `AdaptedCV` via `dataclasses.replace`.
        Does NOT mutate the input.
      - Idempotent: when the LLM emitted the real URL, the
        substitution is a no-op (the URL is unchanged).

    This is the SUSPENDERS layer (mechanical guarantee). The BELT
    layer (prompt-side HYPERLINKS MAP) tells the LLM to emit the
    real URLs in the first place; this function catches whatever
    slips through (LLM hallucination, label paraphrasing, etc.).
    """
    if not hyperlinks:
        return cv

    url_map = build_url_map(hyperlinks)

    new_projects: list[ProjectEntry] = []
    for project in cv.projects:
        new_links: list[ProjectLink] = []
        for link in project.links:
            real_url = find_url_for_label(link.label, url_map)
            if real_url and real_url != link.url:
                # Substitute — the LLM's URL was invented or wrong.
                new_links.append(ProjectLink(label=link.label, url=real_url))
            else:
                # No match in the MAP — keep the LLM's URL (don't lose
                # data we already have; the link may be valid but
                # unannotated in the PDF).
                new_links.append(link)
        new_projects.append(
            ProjectEntry(
                name=project.name,
                description=project.description,
                technologies=project.technologies,
                url=project.url,
                links=new_links,
            ),
        )

    return replace(cv, projects=new_projects)


class GenerateAdaptedCVUseCase:
    """Generate a professional PDF CV adapted to a specific job."""

    def __init__(self, llm_client: MiniMaxLLMClient) -> None:
        self._llm = llm_client

    async def execute(self, request: GenerateAdaptedCVRequest) -> GenerateAdaptedCVResult:
        """Generate the adapted CV PDF.

        Args:
            request: Contains the raw CV PDF and the target job.

        Returns:
            PDF binary bytes with a suggested filename.

        Raises:
            CVAdaptationError: If extraction, LLM call, or PDF generation fails.
        """
        cv_data = self._extract_cv(request.cv_pdf_bytes)
        user_message = build_adapt_cv_user_message(
            cv_text=cv_data.full_text,
            job_title=request.job.title,
            job_company=request.job.company,
            job_description=request.job.description or "",
            hyperlinks=cv_data.hyperlinks,
        )

        raw_response = await self._llm.complete(
            system=ADAPT_CV_SYSTEM_PROMPT,
            user=user_message,
        )

        adapted_cv = parse_adapted_cv_response(raw_response)

        # SUSPENDERS layer: substitute any LLM-invented URLs with the
        # real URLs from the PDF hyperlink map (by label match). Runs
        # AFTER `parse_adapted_cv_response` and BEFORE `generate_cv_pdf`.
        adapted_cv = substitute_hyperlinks_in_cv(adapted_cv, cv_data.hyperlinks)

        # Attach extracted photo if available
        if cv_data.photo_base64:
            adapted_cv.photo_base64 = cv_data.photo_base64

        # Fallback to parsed contact info if LLM missed them
        if not adapted_cv.name and cv_data.name:
            adapted_cv.name = cv_data.name
        if not adapted_cv.email and cv_data.email:
            adapted_cv.email = cv_data.email
        if not adapted_cv.phone and cv_data.phone:
            adapted_cv.phone = cv_data.phone
        if not adapted_cv.location and cv_data.location:
            adapted_cv.location = cv_data.location

        pdf_bytes = generate_cv_pdf(adapted_cv)

        safe_name = adapted_cv.name.replace(" ", "_") if adapted_cv.name else "CV"
        safe_company = request.job.company.replace(" ", "_")[:20]
        filename = f"{safe_name}_{safe_company}_adaptado.pdf"

        return GenerateAdaptedCVResult(pdf_bytes=pdf_bytes, filename=filename)

    def _extract_cv(self, pdf_bytes: bytes) -> CVData:
        """Extract text, hyperlinks, and photo from the uploaded CV PDF."""
        try:
            cv_data = extract_cv_data(pdf_bytes)
        except Exception as exc:
            raise CVAdaptationError(f"Failed to extract text from CV PDF: {exc}") from exc

        try:
            photo = extract_cv_image(pdf_bytes)
            if photo:
                cv_data.photo_base64 = photo
        except Exception:
            # Photo extraction is best-effort; continue without it
            pass

        return cv_data
