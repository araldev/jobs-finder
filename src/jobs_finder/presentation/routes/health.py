"""`GET /health` route.

Spec: REQ-021. The health endpoint is independent of the port — it
NEVER calls `JobSearchPort` (and the integration test asserts the port's
call counter stays at zero after a health request). It returns a
static `{"status": "ok"}` so the app can answer liveness/readiness
probes without touching upstream sources.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a static 200 OK. No port calls are made here."""
    return {"status": "ok"}
