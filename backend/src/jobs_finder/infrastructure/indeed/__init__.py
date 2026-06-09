"""Indeed-specific infrastructure: scraper, parsers, throttle, exceptions.

Mirrors the `infrastructure/linkedin/` sub-package 1:1. Depends on
`application/` and `domain/`. Must not import `presentation/`.

The T-001 bootstrap batch creates this empty sub-package and extends
`Settings` with the `indeed_*` env-overridable fields. Subsequent
batches (T-002..T-007) populate `exceptions.py`, `throttle.py`,
`parsers.py`, and `scraper.py` following the same RED → GREEN →
REFACTOR discipline the LinkedIn modules used.
"""
