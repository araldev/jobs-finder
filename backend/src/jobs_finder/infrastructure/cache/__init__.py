"""In-memory TTL cache primitives.

The `cache-ttl` change introduces one concrete `CachePort[K, V]`
implementation: `InMemoryTTLCache` (in
`infrastructure/cache/in_memory_ttl_cache.py`). The module
docstring is intentionally short — the module is just a package
marker for the cache sub-package so future implementations
(Redis, Memcached, ...) can be added alongside the in-memory
primitive.
"""
