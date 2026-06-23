"""FastAPI dependencies for the backend-user-awareness change.

``get_current_user`` is the sole dependency: it reads
``request.state.current_user`` (set by ``JWTUserMiddleware``) and
raises a 401 if no authenticated user is present.

Routes that need the authenticated user can either:
  - Use ``get_current_user`` as a sub-dependency (raises 401 when
    absent).
  - Use ``get_optional_user`` when the user is nice-to-have but
    not required (returns ``None`` when absent).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.requests import Request

from jobs_finder.infrastructure.auth._jwt import UserState


async def _get_user_from_request(request: Request) -> UserState | None:
    """Read ``request.state.current_user`` (set by JWTUserMiddleware).

    Returns ``None`` when the middleware hasn't set it (the request
    did not carry a valid JWT) — the caller decides whether to raise
    401 or degrade gracefully.
    """
    return getattr(request.state, "current_user", None)


async def get_current_user(
    current_user: UserState | None = Depends(_get_user_from_request),  # noqa: B008
) -> UserState:
    """Require an authenticated user.

    Raises 401 if no valid JWT was provided.

    Usage::

        @router.post("/cv/generate")
        async def generate_cv(
            user: UserState = Depends(get_current_user),
        ):
            ...
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer JWT.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


async def get_optional_user(
    current_user: UserState | None = Depends(_get_user_from_request),  # noqa: B008
) -> UserState | None:
    """Return the authenticated user (if any) or ``None``.

    Unlike ``get_current_user``, this does NOT raise 401 — the
    route can use it for optional personalization.

    Usage::

        @router.get("/jobs")
        async def list_jobs(
            user: Optional[UserState] = Depends(get_optional_user),
        ):
            ...
    """
    return current_user
