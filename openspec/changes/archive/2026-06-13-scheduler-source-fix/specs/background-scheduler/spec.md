# Delta for `background-scheduler`

## MODIFIED Requirements

### Requirement: REQ-QUERY-001 — SCHEDULER_QUERIES default uses empty keywords

(Previously: `scheduler_queries` default was
`[{"keywords": "desarrollador", "location": "España"}]`.)

The default value for `scheduler_queries` in `Settings` MUST be changed to
use empty keywords with Spain locations:

```python
[{"keywords": "", "location": "España"}, ...]
```

#### Scenario: Default SCHEDULER_QUERIES uses empty keywords

- GIVEN no `SCHEDULER_QUERIES` env var set
- WHEN `Settings()` is constructed
- THEN `scheduler_queries` equals `[{"keywords": "", "location": "España"}, ...]`

#### Scenario: Empty keywords string is passed verbatim to search

- GIVEN `queries=[{"keywords": "", "location": "España"}]`
- WHEN the scheduler calls `search_fn(keywords, location)` for that query
- THEN `keywords=""` is passed (empty string, not `None`)

---

### Requirement: REQ-HOURS-001 — Scheduler checks Madrid time before each cycle

(Previously: the scheduler ran continuously without time restrictions.)

Before each cycle, the scheduler loop MUST check whether Madrid time is
within the active window using
`zoneinfo.ZoneInfo("Europe/Madrid")`. This check uses only Python's
built-in `zoneinfo` (no new dependencies — Python 3.12 per `AGENTS.md`).

#### Scenario: Cycle proceeds during active window (09:00–22:00)

- GIVEN Madrid time is 14:30
- WHEN the scheduler loop is about to start a cycle
- THEN the cycle proceeds immediately without sleeping

#### Scenario: Outside window — scheduler sleeps and re-checks

- GIVEN Madrid time is 23:00
- WHEN the scheduler loop is about to start a cycle
- THEN the scheduler follows the sleep behavior defined in REQ-HOURS-002

---

### Requirement: REQ-HOURS-002 — Outside 09:00-22:00: sleeps 5 min intervals

If Madrid time is outside the active window `09:00–22:00`, the scheduler
MUST `await asyncio.sleep(300)` (5 minutes) and re-check. This repeats
until the current Madrid time is within the window.

#### Scenario: Outside window — sleeps 5 minutes and re-checks

- GIVEN Madrid time is 23:00
- WHEN the scheduler loop is about to start a cycle
- THEN the scheduler sleeps 300 seconds
- AND after waking, re-checks the Madrid time
- AND continues to sleep in 5-minute intervals until Madrid time is within 09:00–22:00

---

### Requirement: REQ-HOURS-003 — At 22:00: stops and waits until 09:00 next day

At exactly 22:00 Madrid time: the scheduler MUST stop the current cycle
if running, sleep until 09:00 the next calendar day, and then proceed
with the cycle.

#### Scenario: At 22:00 — sleeps until next day 09:00

- GIVEN Madrid time is 22:00 exactly
- WHEN the scheduler loop is about to start a cycle
- THEN the scheduler sleeps until 09:00 on the next calendar day
- AND the cycle begins at 09:00

#### Scenario: Edge — 22:00:00 on the last day of the month

- GIVEN Madrid time is `2026-06-30 22:00:00`
- WHEN the scheduler checks the time
- THEN the scheduler sleeps until `2026-07-01 09:00:00` Madrid time

---

### Requirement: REQ-HOURS-004 — At 09:00: proceeds immediately with cycle

At exactly 09:00 Madrid time: the scheduler MUST proceed with the cycle
immediately without any additional delay.

#### Scenario: At 09:00 — proceeds immediately

- GIVEN Madrid time is 09:00 exactly
- WHEN the scheduler loop is about to start a cycle
- THEN the cycle proceeds immediately without any delay

#### Scenario: Edge — 09:00:00 on the first day of the month

- GIVEN Madrid time is `2026-06-01 09:00:00`
- WHEN the scheduler checks the time
- THEN `datetime.now(ZoneInfo("Europe/Madrid")).hour == 9`
- AND the cycle proceeds immediately

---

## ADDED Requirements

### Requirement: REQ-QUERY-002 — .env.example documents empty keywords format

The `backend/.env.example` file MUST document the `SCHEDULER_QUERIES`
format with empty keywords, clarifying that an empty `keywords` string
means a location-only search.

#### Scenario: .env.example documents empty keywords format

- GIVEN the `backend/.env.example` file
- WHEN it is read
- THEN the `SCHEDULER_QUERIES` comment documents the format
  `[{"keywords": "", "location": "España"}, ...]`
- AND the comment explains that empty keywords means location-only search

### Requirement: REQ-QUERY-003 (scrapers) — Scrapers handle empty keywords without error

[Covered by `linkedin-scraper`, `indeed-scraper`, and `infojobs-scraper` delta specs.]

The scrapers MUST pass `keywords=""` (empty string) verbatim to the URL
builder when the scheduler passes empty keywords. No scraper MUST raise
an error or skip the search when keywords are empty.

#### Scenario: Uses zoneinfo without additional dependencies

- GIVEN Python 3.12 standard library only
- WHEN `zoneinfo.ZoneInfo("Europe/Madrid")` is constructed
- THEN it resolves without `ImportError`
