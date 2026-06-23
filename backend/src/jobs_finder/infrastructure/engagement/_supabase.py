"""Supabase REST API-backed engagement repository.

Implements the ``EngagementPort`` protocol using raw ``httpx`` calls
to the Supabase REST API (``supabase-py`` does not expose
``create_client``). Uses the service_role key so the backend can write
engagement events on behalf of any authenticated user without RLS
restrictions.

Best-effort contract: never raises, logs warnings on failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

_logger = logging.getLogger(__name__)

# Default table within the Supabase public schema.
_TABLE = "user_engagement"
_REST_API_VERSION = "1"


class SupabaseEngagementRepository:
    """Records and queries user engagement events via the Supabase REST API.

    Args:
        supabase_url: The Supabase project URL (e.g. ``https://abc.supabase.co``).
        service_key: The Supabase server-side API key — either the legacy
            ``service_role`` JWT (starts with ``eyJ...``) OR the new
            ``secret`` key (starts with ``sb_secret_...``). Both bypass RLS
            and are sent as Bearer tokens to the REST API (Supabase accepts
            either format in the ``Authorization`` header).
    """

    __slots__ = ("_base_url", "_headers")

    def __init__(self, supabase_url: str, service_key: str) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v{_REST_API_VERSION}/{_TABLE}"
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    # ── EngagementPort conformance ─────────────────────────────────────────

    async def record_event(
        self,
        user_id: str,
        event_type: str,
        job_id: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Record a user engagement event (best-effort).

        POSTs to the Supabase REST API. Never raises on failure — logs a
        warning and returns silently.
        """
        body: dict[str, object] = {
            "user_id": user_id,
            "event_type": event_type,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if job_id is not None:
            body["job_id"] = job_id
        if metadata is not None:
            body["metadata"] = metadata

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._base_url,
                    json=body,
                    headers=self._headers,
                )
                resp.raise_for_status()
        except Exception:
            _logger.warning(
                "Failed to record engagement event user_id=%s event_type=%s",
                user_id,
                event_type,
                exc_info=True,
            )

    async def count_events_today(self, user_id: str, event_type: str) -> int:
        """Count events of a given type for a user today (UTC).

        Best-effort: returns 0 on any failure.
        """
        today_start = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00Z")

        params: dict[str, str] = {
            "select": "count",
            "user_id": f"eq.{user_id}",
            "event_type": f"eq.{event_type}",
            "created_at": f"gte.{today_start}",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._base_url,
                    params=params,
                    headers={**self._headers, "Accept": "application/json"},
                )
                if resp.status_code != 200:  # noqa: PLR2004
                    _logger.warning(
                        "count_events_today got status=%d for user=%s type=%s",
                        resp.status_code,
                        user_id,
                        event_type,
                    )
                    return 0
                data = resp.json()
                if not data or not isinstance(data, list):
                    return 0
                return int(data[0].get("count", 0))
        except Exception:
            _logger.warning(
                "Failed to count engagement events user_id=%s event_type=%s",
                user_id,
                event_type,
                exc_info=True,
            )
            return 0

    # ── equality / hash / repr (std project pattern) ───────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._base_url == other._base_url

    def __hash__(self) -> int:
        return hash(self._base_url)

    def __repr__(self) -> str:
        return f"<SupabaseEngagementRepository base={self._base_url}>"
