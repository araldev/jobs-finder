# OSpec (OpenSpec) working directory

This directory holds the spec-driven development artifacts for the
`jobs-finder` project. It is **gitignored** by the root `.gitignore`
so the working tree is not committed.

> If you want to commit `openspec/` so specs survive across clones,
> remove the `openspec/` line from the root `.gitignore` and commit
> the directory.

## Layout

```
openspec/
├── changes/                     # active + archived SDD changes
│   ├── <change-name>/           # active change: explore/proposal/spec/design/tasks/verify/archive reports
│   │   ├── explore.md
│   │   ├── proposal.md
│   │   ├── specs/<capability>/spec.md
│   │   ├── design.md
│   │   ├── tasks.md
│   │   ├── verify-report.md
│   │   └── archive-report.md
│   └── archive/                 # closed changes, by date
│       └── YYYY-MM-DD-<change-name>/
└── specs/                       # canonical source-of-truth specs
    └── <capability>/spec.md     # promoted from a change on archive
```

## Why gitignored?

The orchestrator (Gentle AI SDD) keeps the canonical record in
**Engram** (persistent memory). The `openspec/` directory is a
human-readable mirror for in-session review. The artifact store mode
for this project is `both` (OpenSpec files + Engram copies), so specs
are durable even if `openspec/` is lost.

If you prefer git-tracked specs (e.g. for team review), drop this
`README.md` and the `openspec/` line from the root `.gitignore`,
then commit the directory normally.
