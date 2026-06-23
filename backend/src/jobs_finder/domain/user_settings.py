"""UserSettings domain value object.

Spec: user-storage change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserSettings:
    """A user's settings and preferences."""

    user_id: UUID
    enabled_platforms: list[str]
    notifications_enabled: bool
    created_at: datetime
    updated_at: datetime
