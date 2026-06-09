"""SHA256 hashing of the rate-limiter `client_id` for PII sanitization.

Spec: REQ-RL-012 (added in `rate-limit-followups`).

The HTTP rate limiter uses a per-key bucket keyed by the
client's IP. The raw IP is sensitive personal data (GDPR, CCPA,
AEPD/LOPDGDD) and would be a PII leak in:
  - Redis `KEYS` / `SCAN` / `MONITOR` dumps
  - The in-memory `InMemoryTokenBucket._buckets` dict (a
    `repr(self._buckets)` in a traceback leaks the IPs).
  - The `_LOGGER` output on a 429 WARNING.

`hash_client_id()` solves this by hashing the resolved IP with
SHA256 and truncating to 16 hex chars (64 bits) before the
middleware hands it to the limiter. The limiter is unaware of
the hashing (one SHA256 round-trip per request, microseconds);
both `InMemoryTokenBucket._buckets` and `RedisTokenBucket._key`
receive opaque hash strings.

Properties of the 16-char (64-bit) truncation:
  - Deterministic: same input always produces the same output.
  - Fixed length: 16 hex chars regardless of input length
    (IPv4 ≤ 15 chars, IPv6 ≤ 45 chars; both compress to 16).
  - Non-reversible: SHA256 is a one-way function; the raw IP
    cannot be recovered from the hash.
  - Collision-safe: 2^32 (≈ 4.3 billion) unique keys before a
    50% birthday-bound collision. A rate-limiter bucket lives
    for `2 × window_seconds = 120` seconds by default; a single
    API receives < 1M unique IPs per 120s in practice, so 10^3x
    safety margin.

The truncation length is shorter than the project's
`RedisCache._key()` precedent (32 chars = 128 bits) because
rate-limiter cardinality is bounded by the 2x window TTL
(< 1M unique keys) while cache cardinality is bounded only
by the TTL (which can be 60s for fresh keys). The 16-char
value is sufficient for the rate-limiter's use case.

Observability: the resolved (pre-hash) IP is still logged at
WARNING when a 429 is emitted (separate concern, deferred to a
follow-up). The hashing is for STORAGE, not for observability.
"""

from __future__ import annotations

import hashlib

# The truncation length, in hex characters (16 hex chars = 64 bits).
# Pinned as a module-level constant so a future change to e.g. 32
# chars is a single-line edit, and a test that asserts the length
# is a single-source-of-truth check.
HASH_TRUNCATION_CHARS: int = 16


def hash_client_id(client_id: str) -> str:
    """Return `SHA256(client_id.encode("utf-8")).hexdigest()[:16]`.

    Args:
        client_id: The resolved client identifier (typically a
            string IP from `_resolve_client_id`).

    Returns:
        A 16-character lowercase hex string. Deterministic
        (same input -> same output), non-reversible (the raw
        IP cannot be recovered from the hash), and bounded
        length (16 chars regardless of input length).

    Raises:
        UnicodeEncodeError: if `client_id` is not UTF-8 encodable.
            In practice, `request.client.host` is always a valid
            IP string (Starlette validates the Host header) or
            an opaque string from the XFF walk (which is also
            UTF-8 by construction). The error is defensive and
            surfaces as a 5xx in the middleware, not as a
            silent mis-hash.
    """
    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:HASH_TRUNCATION_CHARS]


__all__ = ["hash_client_id", "HASH_TRUNCATION_CHARS"]
