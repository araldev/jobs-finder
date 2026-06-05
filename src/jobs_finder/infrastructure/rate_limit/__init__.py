"""Token-bucket rate limiter implementations.

Spec: REQ-RL-001 (port + decision), REQ-RL-002 (in-memory),
REQ-RL-003 (Redis), REQ-RL-004 (factory).

This sub-package mirrors the layout of `infrastructure/cache/`: a
`Protocol` + 2 implementations + a `build_X` factory. The
`__init__.py` re-exports the public surface for callers.
"""

from jobs_finder.infrastructure.rate_limit._factory import build_rate_limiter
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.infrastructure.rate_limit.redis_token_bucket import (
    RedisTokenBucket,
)

__all__ = [
    "build_rate_limiter",
    "InMemoryTokenBucket",
    "RedisTokenBucket",
]
