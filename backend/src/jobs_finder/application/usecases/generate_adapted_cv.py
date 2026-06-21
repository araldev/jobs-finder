"""Generate an adapted CV for a specific job description.

1. Extract text from the uploaded PDF (pdfplumber)
2. Extract photo if present (pdfplumber)
3. Send CV text + job description to MiniMax LLM
4. LLM returns structured adapted CV JSON
5. Render as HTML + photo (if available) + weasyprint → PDF binary
6. Return PDF bytes
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.exceptions import JobSearchError
from ...domain.job import Job
from ...infrastructure.cv._generator import generate_cv_pdf
from ...infrastructure.cv._parser import CVData, extract_cv_image, extract_cv_text
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
        )

        raw_response = await self._llm.complete(
            system=ADAPT_CV_SYSTEM_PROMPT,
            user=user_message,
        )

        adapted_cv = parse_adapted_cv_response(raw_response)

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
        """Extract text and photo from the uploaded CV PDF."""
        try:
            cv_data = extract_cv_text(pdf_bytes)
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
