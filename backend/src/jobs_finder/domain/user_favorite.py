"""UserFavorite domain value object.

Spec: user-storage change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserFavorite:
    """A user's favorited job."""

    id: int
    user_id: UUID
    job_id: int
    created_at: datetime
