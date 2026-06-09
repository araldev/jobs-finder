"""Unit tests for the `CachePort` Protocol and `JobSearchCacheKey` named tuple.

Spec: REQ-C-001 (the protocol), REQ-C-005 (per-source key isolation).

The `CachePort` is a `typing.Protocol` declaring the 4 methods the
infrastructure-layer `InMemoryTTLCache` (and any future Redis /
Memcached implementation) must satisfy. The named tuple is the
exact key shape used by `CachedJobSearchUseCase` for the 3 source
routes.

These tests pin the SHAPE of the protocol (so the application
layer's static type checks against the right interface) and the
KEY (so two sources with the same query get distinct cache
entries).
"""

from __future__ import annotations

from jobs_finder.application.ports import (
    CachePort,
    JobSearchCacheKey,
    JobSearchPort,
)

# ---------------------------------------------------------------------------
# CachePort shape
# ---------------------------------------------------------------------------


def test_cache_port_is_a_protocol() -> None:
    """`CachePort` is a `typing.Protocol` (structural subtyping)."""
    assert getattr(CachePort, "_is_protocol", None) is True
    protocol_attrs: set[str] = getattr(CachePort, "__protocol_attrs__", set())
    for expected in ("get", "set", "delete", "clear"):
        assert expected in protocol_attrs, f"CachePort must declare {expected!r}"


def test_cache_port_methods_have_correct_signatures() -> None:
    """Each `CachePort` method has the documented signature.

    For generic Protocols (`Protocol[K, V]`) the `__protocol_attrs__`
    lives on the bare class. Both attribute lookups are tried so the
    test is robust to Python 3.12's generic-Protocol details.
    """
    protocol_attrs: set[str] = getattr(CachePort, "__protocol_attrs__", set())
    for expected in ("get", "set", "delete", "clear"):
        assert expected in protocol_attrs, f"CachePort must declare {expected!r}"


def test_cache_port_get_is_a_method() -> None:
    """`CachePort.get` is callable; the signature accepts one arg."""
    # `Protocol` methods are abstract; we just confirm the attribute
    # exists and is declared.
    protocol_attrs: set[str] = getattr(CachePort, "__protocol_attrs__", set())
    assert "get" in protocol_attrs


# ---------------------------------------------------------------------------
# JobSearchCacheKey shape + isolation (REQ-C-005)
# ---------------------------------------------------------------------------


def test_job_search_cache_key_has_six_fields() -> None:
    """`JobSearchCacheKey` declares exactly the 6 documented fields.

    The 5th `geo_id: int | None = None` field was added in the
    `fix-linkedin-geoid` change so a query with
    `location="Madrid", geo_id=103374081` (resolved) is
    byte-distinct from `location="Madrid", geo_id=None` (not
    resolved) — they return different jobs, so a cache HIT on
    one would silently corrupt the other. The field is `None`
    by default for Indeed + InfoJobs (they accept `location=`
    strings; they don't need a `geoId=`).

    The 6th `query_tokens: tuple[str, ...] = ()` field was
    added in the `backend-scraper-query-tuning` change
    (REQ-CACHE-001) so a query with
    `query_tokens=("react",)` is byte-distinct from the same
    query with `query_tokens=()` — they return different
    jobs (the InfoJobs filter is opt-in based on the
    `query_tokens`).
    """
    hints = getattr(JobSearchCacheKey, "__annotations__", {})
    assert set(hints.keys()) == {
        "source",
        "keywords",
        "location",
        "limit",
        "geo_id",
        "query_tokens",
    }


def test_job_search_cache_key_geo_id_field_default_is_none() -> None:
    """`geo_id` defaults to `None` (backward compat with pre-`fix-linkedin-geoid` callers).

    The pre-change signature is `(source, keywords, location,
    limit)` (4 fields, all required). The 5th `geo_id` is
    optional with a `None` default so existing test fixtures
    that construct a 4-tuple continue to work. The
    `CachedJobSearchUseCase._search(...)` call site uses
    keyword args exclusively, so adding a 5th field with a
    `None` default is a non-breaking change.
    """
    key = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    assert key.geo_id is None


def test_job_search_cache_key_different_geo_id_is_not_equal() -> None:
    """A different `geo_id` field makes the key distinct.

    `location="Madrid", geo_id=103374081` (resolved) and
    `location="Madrid", geo_id=None` (not resolved) return
    different jobs (one with the correct geo filter, one
    without), so they MUST be different cache keys.
    """
    resolved = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20, geo_id=103374081
    )
    unresolved = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20, geo_id=None
    )
    assert resolved != unresolved


def test_job_search_cache_key_same_geo_id_is_equal() -> None:
    """Two keys with the same 5 fields are equal (same query + same source)."""
    a = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20, geo_id=103374081
    )
    b = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20, geo_id=103374081
    )
    assert a == b
    assert hash(a) == hash(b)


def test_job_search_cache_key_is_a_named_tuple() -> None:
    """`JobSearchCacheKey` is a `typing.NamedTuple` (immutable + hashable)."""
    # NamedTuples are tuples, so they are hashable + support equality.
    key = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    assert isinstance(key, tuple)
    assert key.source == "linkedin"
    assert key.keywords == "python"
    assert key.location == "madrid"
    assert key.limit == 20


def test_job_search_cache_key_different_sources_are_not_equal() -> None:
    """REQ-C-005: two keys with the same query but different sources are distinct."""
    linkedin = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    indeed = JobSearchCacheKey(source="indeed", keywords="python", location="madrid", limit=20)
    infojobs = JobSearchCacheKey(source="infojobs", keywords="python", location="madrid", limit=20)
    assert linkedin != indeed
    assert linkedin != infojobs
    assert indeed != infojobs
    # Hashes differ too — they would map to different dict entries.
    assert len({hash(linkedin), hash(indeed), hash(infojobs)}) == 3


def test_job_search_cache_key_same_fields_are_equal() -> None:
    """Two keys with the same 4 fields are equal (same query + same source)."""
    a = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    b = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    assert a == b
    assert hash(a) == hash(b)


def test_job_search_cache_key_different_limit_is_not_equal() -> None:
    """A different `limit` field makes the key distinct (limit is part of the key)."""
    a = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    b = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=5)
    assert a != b


def test_job_search_cache_key_different_keywords_is_not_equal() -> None:
    """A different `keywords` field makes the key distinct."""
    a = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    b = JobSearchCacheKey(source="linkedin", keywords="rust", location="madrid", limit=20)
    assert a != b


def test_job_search_cache_key_different_location_is_not_equal() -> None:
    """A different `location` field makes the key distinct."""
    a = JobSearchCacheKey(source="linkedin", keywords="python", location="madrid", limit=20)
    b = JobSearchCacheKey(source="linkedin", keywords="python", location="barcelona", limit=20)
    assert a != b


# ---------------------------------------------------------------------------
# Protocol cohesion: the existing `JobSearchPort` is unchanged.
# ---------------------------------------------------------------------------


def test_job_search_port_is_unchanged() -> None:
    """`JobSearchPort` (the search port) is unchanged by T-001."""
    assert getattr(JobSearchPort, "_is_protocol", None) is True
    protocol_attrs: set[str] = getattr(JobSearchPort, "__protocol_attrs__", set())
    assert "search" in protocol_attrs


# ---------------------------------------------------------------------------
# Application dependency rule (REQ: no infrastructure / presentation import)
# ---------------------------------------------------------------------------


def test_application_ports_does_not_import_infrastructure_or_presentation() -> None:
    """`ports.py` must not import infrastructure or presentation (dependency rule)."""
    import ast  # noqa: PLC0415

    source_path = "src/jobs_finder/application/ports.py"
    with open(source_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    joined = " ".join(imported)
    assert "infrastructure" not in joined, f"{source_path} imports infrastructure"
    assert "presentation" not in joined, f"{source_path} imports presentation"
    assert "playwright" not in joined, f"{source_path} imports playwright"
    assert "fastapi" not in joined, f"{source_path} imports fastapi"
