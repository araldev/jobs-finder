"""Presentation layer — FastAPI app, schemas, routes, middleware, exception handlers.

Spec: REQ-002, REQ-006, REQ-017..REQ-022.
Dependency rule: this layer may import from `application` and `domain`,
and from FastAPI / Pydantic / Starlette. It MUST NOT import from
`infrastructure` (composition is done in `app_factory` via the injected
`use_case`).
"""
