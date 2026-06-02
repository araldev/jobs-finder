"""Runtime configuration for the jobs-finder service (skeleton).

Spec: REQ-005, REQ-006. Env-driven so the same image can run in dev, CI,
and prod with different throttles, UAs, and timeouts.

NOTE: this is a plain dataclass skeleton. T-009 finalizes it as a
`pydantic_settings.BaseSettings` with explicit `LINKEDIN_*` env-var
overrides and adds a `load_settings()` factory. The fields and defaults
are intentionally locked here so the rest of the presentation layer can
type against them in T-008 without depending on the pydantic-settings
package (which lands with T-009).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Env-driven runtime configuration (skeleton, finalized in T-009).

    Fields and defaults are stable; the loader (`load_settings`) and the
    `BaseSettings` wiring land in T-009.
    """

    throttle_seconds: float = 3.0
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    headless: bool = True
    request_timeout_ms: int = 10_000
