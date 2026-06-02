"""InfoJobs-specific infrastructure: scraper, parsers, throttle, exceptions.

Mirrors the `infrastructure/indeed/` sub-package 1:1 (and, by extension,
the `infrastructure/linkedin/` sub-package that the Indeed package
mirrors). Depends on `application/` and `domain/`. Must not import
`presentation/`.

The T-001 bootstrap batch creates this empty sub-package and extends
`Settings` with the 6 `infojobs_*` env-overridable fields. Subsequent
batches (T-002..T-007) populate `exceptions.py`, `throttle.py`,
`parsers.py`, and `scraper.py` following the same RED → GREEN →
REFACTOR discipline the Indeed modules used.

The InfoJobs anti-bot surface (Distil + Geetest) is stricter than
Indeed's Cloudflare, so the InfoJobs scraper wires `Stealth()` in
production from T-008 onward (vs. the Indeed v1 which deferred stealth
to a follow-up change).
"""
