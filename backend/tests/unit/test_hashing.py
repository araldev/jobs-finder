"""Unit tests for `hash_client_id` (SHA256 truncated to 16 hex chars).

Spec: REQ-RL-012.

`hash_client_id()` is the PII-sanitization helper at the HTTP
boundary. The middleware calls it AFTER `_resolve_client_id()` and
BEFORE `try_acquire(key=...)`, so the bucket key (and the
`InMemoryTokenBucket._buckets` dict key, and the `RedisTokenBucket`
Redis key) is the SHA256 hash, not the raw IP.

The 5 scenarios are Given/When/Then, observable behavior, deterministic.
They cover the 4 spec scenarios for the helper (length, format,
idempotency, distinct inputs, raw-IP-absent) plus the implicit
"hashes the entire input" semantic (no partial truncation for
IPv6 inputs longer than 16 chars).
"""

from __future__ import annotations

import re

from jobs_finder.infrastructure.rate_limit._hashing import hash_client_id

# A pre-computed reference hash for `"1.2.3.4"` so the test can
# assert determinism + format. `hashlib.sha256(b"1.2.3.4").hexdigest()[:16]`
# is the canonical computation. Pinned here so a future change
# that drifts the algorithm (e.g., a typo in `.hexdigest()[:16]`)
# surfaces as a test failure, not as a silent re-hash of all
# existing rate-limiter buckets in production.
EXPECTED_HASH_OF_1_2_3_4 = "6694f83c9f476da3"  # hashlib.sha256(b"1.2.3.4").hexdigest()[:16]
EXPECTED_HASH_OF_1_2_3_5 = "f53eea05fa9e492d"  # hashlib.sha256(b"1.2.3.5").hexdigest()[:16]


# ---------------------------------------------------------------------------
# REQ-RL-012 scenario 1 — Length + hex format
# ---------------------------------------------------------------------------


def test_hash_client_id_returns_16_char_hex_string() -> None:
    """`hash_client_id("1.2.3.4")` is exactly 16 lowercase hex chars.

    REQ-RL-012 scenario 1: the hash format is
    `re.fullmatch(r"[0-9a-f]{16}", result)`. The 16-char truncation
    (64 bits) is collision-safe for any realistic rate-limiter
    cardinality (2^32 keys before 50% birthday-bound collision; a
    single API receives < 1M unique IPs per 2x window in practice).
    """
    result = hash_client_id("1.2.3.4")
    assert len(result) == 16, f"expected 16 chars, got {len(result)}: {result!r}"
    assert re.fullmatch(r"[0-9a-f]{16}", result), f"not lowercase hex: {result!r}"


# ---------------------------------------------------------------------------
# REQ-RL-012 scenario 2 — Idempotency (same input twice → same output)
# ---------------------------------------------------------------------------


def test_hash_client_id_is_idempotent() -> None:
    """Calling `hash_client_id(x)` twice with the same input returns the same hash.

    REQ-RL-012 scenario 2: SHA256 is deterministic; the
    truncation is positional (first 16 chars of the hex digest).
    Two calls with the same input MUST return the same output
    so the bucket key is stable across processes.
    """
    assert hash_client_id("1.2.3.4") == hash_client_id("1.2.3.4")
    assert hash_client_id("") == hash_client_id("")


def test_hash_client_id_matches_sha256_truncation_reference() -> None:
    """The algorithm is exactly `sha256(input).hexdigest()[:16]` (no drift).

    Pinned reference values (computed with `hashlib`):
    - `hashlib.sha256(b"1.2.3.4").hexdigest()[:16]` = `6694f83c9f476da3`
    - `hashlib.sha256(b"1.2.3.5").hexdigest()[:16]` = `f53eea05fa9e492d`

    A future refactor that changes the algorithm (e.g., a typo
    in `[:16]`, a different encoding, a different hash) will
    surface here, not as a silent re-hash of every existing
    rate-limiter bucket.
    """
    assert hash_client_id("1.2.3.4") == EXPECTED_HASH_OF_1_2_3_4
    assert hash_client_id("1.2.3.5") == EXPECTED_HASH_OF_1_2_3_5


# ---------------------------------------------------------------------------
# REQ-RL-012 scenario 3 — Distinct inputs → distinct hashes
# ---------------------------------------------------------------------------


def test_hash_client_id_distinct_inputs_produce_distinct_hashes() -> None:
    """Two different inputs produce two different hashes (no test-set collision).

    REQ-RL-012 scenario 3: SHA256 has ~2^-64 collision probability
    for any 2 specific inputs. The test set has 2 different
    IPs, so the hashes MUST be different.
    """
    hash_a = hash_client_id("1.2.3.4")
    hash_b = hash_client_id("1.2.3.5")
    assert hash_a != hash_b, f"collision in test set: {hash_a} == {hash_b}"


# ---------------------------------------------------------------------------
# REQ-RL-012 scenario 4 — Raw IP does NOT appear in the hash
# ---------------------------------------------------------------------------


def test_hash_client_id_does_not_leak_raw_input() -> None:
    """The raw input is NOT a substring of the hash (no PII leakage).

    REQ-RL-012 scenario 4: the hash is 16 lowercase hex chars; a
    raw IP like `"1.2.3.4"` contains `"."` (not a hex char), so
    a substring search returns `None`. The hash is a one-way
    function; ops cannot recover the input from the hash.
    """
    result = hash_client_id("1.2.3.4")
    # The raw IP is not a substring.
    assert "1.2.3.4" not in result, f"raw IP leaked in hash: {result!r}"
    # The raw IP is not matched by regex (the IP contains `.`
    # which is not a hex char; the regex would only match a
    # contiguous hex substring, which is a 1-in-2^32 chance).
    assert re.search(re.escape("1.2.3.4"), result) is None


# ---------------------------------------------------------------------------
# Bonus scenario — IPv6 input is fully hashed (not truncated to 16 chars)
# ---------------------------------------------------------------------------


def test_hash_client_id_hashes_ipv6_input_fully() -> None:
    """An IPv6 address (longer than 16 chars) is hashed, not truncated.

    A naive impl could `return client_id[:16]` which would leak
    the IPv6 prefix. SHA256 of the encoded input + truncation
    is the contract.
    """
    ipv6 = "2001:0db8:0000:0000:0000:ff00:0042:8329"
    result = hash_client_id(ipv6)
    # The result is 16 hex chars, NOT a substring of the IPv6
    # (which contains `:` and digits; the hash has no `:`).
    assert len(result) == 16
    assert ":" not in result, f"hash should not contain ':': {result!r}"
    # The raw IPv6 is not a substring.
    assert ipv6[:8] not in result
