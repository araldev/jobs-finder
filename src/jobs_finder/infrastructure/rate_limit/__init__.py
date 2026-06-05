"""Token-bucket rate limiter implementations.

Spec: REQ-RL-001 (port + decision), REQ-RL-002 (in-memory),
REQ-RL-003 (Redis, added in T-003), REQ-RL-004 (factory, added in T-003).

This sub-package mirrors the layout of `infrastructure/cache/`: a
`Protocol` + 2 implementations + a `build_X` factory. The
`__init__.py` re-exports the public surface for callers.
"""
