"""`POST /cv/generate` — generate an adapted CV PDF (authenticated).

Auth & quota (backend-user-awareness change):
  - Requires a valid JWT via the ``get_current_user`` dependency.
  - Checks daily quota via ``EngagementPort.count_events_today`` BEFORE
    the LLM call (returns 429 when exceeded).
  - Records a ``cv_adapted`` event via ``EngagementPort.record_event``
    AFTER the PDF is generated successfully.
  - The quota limit comes from
    ``request.app.state.settings.user_cv_daily_quota`` (0 = unlimited).

Flow:
  1. Authenticate (JWT required).
  2. Read the uploaded PDF.
  3. Check daily quota.
  4. Send CV text + job description to MiniMax LLM.
  5. LLM returns structured adapted CV JSON.
  6. Render as HTML + weasyprint → PDF binary.
  7. Record the ``cv_adapted`` event.
  8. Return PDF as application/pdf attachment.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from jobs_finder.application.ports import EngagementPort
from jobs_finder.application.usecases.generate_adapted_cv import (
    CVAdaptationError,
    GenerateAdaptedCVRequest,
    GenerateAdaptedCVUseCase,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.auth._jwt import UserState
from jobs_finder.presentation.dependencies import get_current_user

_logger = logging.getLogger(__name__)


def build_cv_router(
    *,
    generate_adapted_cv_use_case: GenerateAdaptedCVUseCase,
) -> APIRouter:
    router = APIRouter(prefix="/cv", tags=["cv"])

    @router.post("/generate", response_model=None)
    async def generate_cv(
        request: Request,
        user: UserState = Depends(get_current_user),
        file: UploadFile = File(..., description="PDF del CV original"),
        job_title: str = Form(..., description="Título de la oferta"),
        job_company: str = Form(..., description="Empresa de la oferta"),
        job_description: str = Form("", description="Descripción de la oferta"),
        job_url: str = Form("", description="URL de la oferta"),
    ) -> StreamingResponse:
        """Generate a professional PDF CV adapted to the target job.

        Requires authentication (Bearer JWT). Respects the per-user
        daily quota (``user_cv_daily_quota``, default 5).
        The response is a streaming PDF download.
        """
        # 1. Check daily quota (ENG-001) BEFORE reading the PDF — fail
        #    fast so the user doesn't waste bandwidth uploading a file
        #    they won't be able to process.
        engagement_port: EngagementPort | None = getattr(
            request.app.state, "engagement_port", None
        )
        settings = getattr(request.app.state, "settings", None)
        daily_quota = getattr(settings, "user_cv_daily_quota", 5) if settings else 5

        quota_remaining = -1  # unlimited by default (when quota is 0 or no engagement port)
        if daily_quota > 0 and engagement_port is not None:
            today_count = await engagement_port.count_events_today(
                user_id=user.user_id,
                event_type="cv_adapted",
            )
            if today_count >= daily_quota:
                return JSONResponse(  # type: ignore[return-value]
                    status_code=429,
                    content={
                        "detail": (
                            "Límite diario de generación de CV alcanzado. "
                            f"Has generado {today_count} de {daily_quota} CVs hoy."
                        ),
                    },
                    headers={"X-Quota-Remaining": "0"},
                )
            quota_remaining = daily_quota - today_count - 1

        # 2. Validate the uploaded file
        # Reject non-PDF content types (client-side check — not authoritative
        # since content_type can be spoofed, but catches accidental wrong files).
        if file.content_type and file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="Solo se aceptan archivos PDF.",
            )

        # 3. Read the uploaded PDF (capped at 10MB to prevent OOM)
        max_file_size = 10 * 1024 * 1024  # 10 MB
        try:
            pdf_bytes = await file.read()
        except Exception as exc:
            _logger.warning("Error reading uploaded PDF: %s", exc)
            raise HTTPException(status_code=400, detail="Error leyendo el archivo PDF.") from exc

        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="El archivo PDF está vacío.")

        if len(pdf_bytes) > max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo PDF excede el tamaño máximo de 10 MB "
                f"(tamaño actual: {len(pdf_bytes) / 1024 / 1024:.1f} MB).",
            )

        # 3. Build a synthetic Job object from the form data
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

        # 4. Run the use case
        try:
            result = await generate_adapted_cv_use_case.execute(
                GenerateAdaptedCVRequest(cv_pdf_bytes=pdf_bytes, job=job)
            )
        except CVAdaptationError as exc:
            _logger.warning("CV adaptation error: %s", exc)
            raise HTTPException(
                status_code=422,
                detail="No se pudo adaptar el CV al perfil solicitado. "
                "Verificá que el PDF sea legible y contenGa información curricular.",
            ) from exc
        except JobSearchError as exc:
            _logger.warning("Job search error during CV generation: %s", exc)
            raise HTTPException(  # noqa: E501
                status_code=502,
                detail="Servicio de búsqueda no disponible.",
            ) from exc
        except Exception as exc:
            _logger.error("Unexpected error generating CV: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Error interno al generar el CV. Intentalo de nuevo más tarde.",
            ) from exc

        # 5. Record the engagement event (ENG-002 — best-effort)
        if engagement_port is not None:
            try:
                await engagement_port.record_event(
                    user_id=user.user_id,
                    event_type="cv_adapted",
                    metadata={"job_title": job_title, "job_company": job_company},
                )
            except Exception:
                _logger.warning(
                    "Failed to record cv_adapted event for user %s",
                    user.user_id,
                    exc_info=True,
                )

        # 6. Return the PDF as a download with quota info
        return StreamingResponse(
            io.BytesIO(result.pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
                "X-Quota-Remaining": str(quota_remaining),
            },
        )

    @router.get("/count")
    async def cv_count(
        request: Request,
        user: UserState = Depends(get_current_user),
    ) -> dict[str, int]:
        """Return today's CV generation count for the authenticated user.

        Requires authentication (Bearer JWT). Returns ``{ "total_today": N }``
        where ``N`` is the number of ``cv_adapted`` events recorded today.
        Used by the frontend dashboard to display per-user daily usage.
        """
        engagement_port: EngagementPort | None = getattr(
            request.app.state, "engagement_port", None
        )
        total_today = 0
        if engagement_port is not None:
            total_today = await engagement_port.count_events_today(
                user_id=user.user_id,
                event_type="cv_adapted",
            )
        return {"total_today": total_today}

    return router
