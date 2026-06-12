# Delta for `job-repository`

## MODIFIED Requirements

### Requirement: REQ-DB-004 — Upsert semantics

(Previously: `upsert_jobs` accepted a `source` parameter passed alongside
the job list and used it uniformly for all rows.)

The `JobRepositoryPort.upsert_jobs` signature MUST be changed from:

```python
async def upsert_jobs(
    self, jobs: list[Job], query_snapshot: str, source: str
) -> int: ...
```

To:

```python
async def upsert_jobs(self, jobs: list[Job], query_snapshot: str) -> int: ...
```

The `source` parameter MUST be removed. Each `Job` in the list MUST carry
its own `source` field. The repository implementation MUST read
`job.source` per-row and issue per-source SQL upserts, grouping jobs by
source internally. The SQL `ON CONFLICT` clause MUST use `excluded.source`
to preserve the per-row source value on conflict.

#### Scenario: New job inserts with job.source as row source

- GIVEN a repository with an empty `jobs` table
- WHEN `upsert_jobs([job_1], query_snapshot='{"keywords":"python","location":"Madrid"}')`
  is called where `job_1.source == "linkedin"`
- THEN 1 row is inserted with `source="linkedin"`
- AND `first_seen_at` equals `last_seen_at`

#### Scenario: Existing job updates using job.source on conflict

- GIVEN a repository with a row for `(source="linkedin", source_id="123")`
  with `title="Old Title"`
- WHEN `upsert_jobs([updated_job], query_snapshot=...)` is called
  where `updated_job.source == "linkedin"` and same `source_id`
- THEN the row's `title` is updated to `updated_job.title`
- AND `last_seen_at` is updated but `first_seen_at` is unchanged
- AND `source` is preserved as `"linkedin"` via `excluded.source`

#### Scenario: Mixed-source upsert groups by source internally

- GIVEN jobs with `source="linkedin"` and `source="indeed"` in the same call
- WHEN `upsert_jobs([linkedin_job, indeed_job], query_snapshot=...)` is called
- THEN the repository internally issues separate SQL upserts per source
- AND each row's `source` column matches `job.source` of the respective job

#### Scenario: Source parameter no longer accepted

- GIVEN a call with `upsert_jobs(jobs, query_snapshot, source="linkedin")`
- WHEN the call is made to `SqliteJobRepository`
- THEN a `TypeError` for unexpected keyword argument is raised

## Out of scope

- Changing the `Job` dataclass field ordering (handled by `job-domain` delta)
- Modifying `search_jobs`, `delete_older_than`, `search_jobs_history`, or `count_jobs`
- The cache key schema
