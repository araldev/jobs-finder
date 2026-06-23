"""UserEngagement domain value object.

Spec: user-storage change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserEngagement:
    """A user's engagement event."""

    id: int
    user_id: UUID
    event_type: Literal["job_view", "job_click", "search", "cv_adapted"]
    job_id: int | None
    metadata: dict[str, Any]
    created_at: datetime
