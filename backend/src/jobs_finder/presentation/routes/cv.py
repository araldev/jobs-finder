"""`POST /cv/generate` — generate an adapted CV PDF.

Receives:
  - A PDF file (multipart/form-data, field name: "file")
  - Job data as form fields (title, company, description)

Flow:
  1. Extract text + photo from the uploaded PDF.
  2. Send CV text + job description to MiniMax LLM.
  3. LLM returns structured adapted CV JSON.
  4. Render as HTML + weasyprint → PDF binary.
  5. Return PDF as application/pdf attachment.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from jobs_finder.application.usecases.generate_adapted_cv import (
    CVAdaptationError,
    GenerateAdaptedCVRequest,
    GenerateAdaptedCVUseCase,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job


def build_cv_router(
    *,
    generate_adapted_cv_use_case: GenerateAdaptedCVUseCase,
) -> APIRouter:
    router = APIRouter(prefix="/cv", tags=["cv"])

    @router.post("/generate")
    async def generate_cv(
        file: UploadFile = File(..., description="PDF del CV original"),
        job_title: str = Form(..., description="Título de la oferta"),
        job_company: str = Form(..., description="Empresa de la oferta"),
        job_description: str = Form("", description="Descripción de la oferta"),
        job_url: str = Form("", description="URL de la oferta"),
    ) -> StreamingResponse:
        """Generate a professional PDF CV adapted to the target job.

        The response is a streaming PDF download.
        """
        # 1. Read the uploaded PDF
        try:
            pdf_bytes = await file.read()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Error leyendo PDF: {exc}") from exc

        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="PDF vacío")

        # 2. Build a synthetic Job object from the form data
        # We don't do a DB lookup — the job data comes from the frontend
        # which already has it from the job detail page
        job = Job(
            id="synthetic",
            title=job_title,
            company=job_company,
            location="",
            url=job_url,
            posted_at=datetime.now(UTC),
            source="cv-adaptation",
            description=job_description or None,
        )

        # 3. Run the use case
        try:
            result = await generate_adapted_cv_use_case.execute(
                GenerateAdaptedCVRequest(cv_pdf_bytes=pdf_bytes, job=job)
            )
        except CVAdaptationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Error adaptando el CV: {exc}",
            ) from exc
        except JobSearchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Error generando CV: {exc}",
            ) from exc

        # 4. Stream the PDF back as a download
        return StreamingResponse(
            io.BytesIO(result.pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
            },
        )

    return router
