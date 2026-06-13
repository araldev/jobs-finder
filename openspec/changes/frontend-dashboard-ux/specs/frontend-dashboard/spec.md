# Delta for frontend-dashboard

## ADDED Requirements

### REQ-DASH-011: Markdown description rendering

`JobDetailContent` MUST render `job.description` through `react-markdown` with `remark-gfm`. HTML MUST be sanitized (no raw HTML rendering). A `null` or empty description MUST render nothing.

- **SC-DASH-027**: Given a job with markdown description, headings, paragraphs, lists, and links render with design system tokens (`font-display`, `text-muted-foreground`).
- **SC-DASH-028**: Given a job with `null` description, the description section is omitted entirely.

### REQ-DASH-012: Compact card variant

The system MUST provide a compact variant of `JobCard` with `p-3` padding, single-line company, no divider, no calendar icon, relative date text, and an `ExternalLink` button opening `job.url` in a new tab. Cards MUST animate on mount with staggered spring animation.

- **SC-DASH-029**: Given a compact card renders, it shows: PlatformBadge (small), title (line-clamp-1), company, location inline, relative date, and ExternalLink button.
- **SC-DASH-030**: Given the user clicks ExternalLink, `job.url` opens in a new tab with `rel="noopener noreferrer"`.
- **SC-DASH-031**: Given the compact card is loading, a skeleton matching compact height renders.

### REQ-DASH-013: JobSourceBreakdown section

A new `JobSourceBreakdown` component MUST render between `StatsCardsRow` and the search bar on the Dashboard. It MUST show per-source job counts from `/api/stats` `platform_distribution`, with icon, name, and count for each of LinkedIn, Indeed, and InfoJobs.

- **SC-DASH-032**: Given the stats endpoint returns 3 platforms, JobSourceBreakdown renders 3 platform entries with correct counts.
- **SC-DASH-033**: Given the stats endpoint fails, the section shows an error state with retry option.

### REQ-DASH-014: Dashboard responsive grid

The Dashboard job list MUST render as a responsive grid: 1 column on mobile, 2 on `md:`, 3 on `lg:`. Compact cards replace the previous single-column list.

- **SC-DASH-034**: Given the Dashboard renders at 1024px+ width, jobs appear in 3 columns.

## MODIFIED Requirements

### REQ-DASH-002: Dashboard stats row

The Dashboard (`/`) MUST display 3 stat cards above `JobSourceBreakdown`: **Total Jobs**, **Active Platforms**, and **Last Sync**. The "Jobs Today" card is removed. Values MUST come from `GET /jobs/history?stats=1` or the first page response.
(Previously: included "Jobs Today" as the second of 4 stat cards)

- **SC-003**: Given the stats endpoint resolves, each card renders its value and label. No card is empty.
- **SC-004**: Given the endpoint fails (4xx/5xx), each card shows `—` and a sonner toast with the error.

### REQ-DASH-003: Dashboard job list with search and export

Below `JobSourceBreakdown` MUST be a search bar (debounced 400ms) and "Export CSV" button. Below that, a responsive grid of compact job cards (1/2/3 cols) with infinite scroll.
(Previously: scrollable single-column list of full-size cards)

- **SC-005**: Given the user types in the search bar, after 400ms a request fires with the search term.
- **SC-006**: Given the user clicks "Export CSV", the browser downloads a CSV of current results.
- **SC-007**: Given the user scrolls to the bottom, the next page loads via IntersectionObserver.
- **SC-008**: Given no more results, "No more jobs" appears.

### REQ-DASH-005: Job detail page

`/jobs/[id]` MUST render a 2-column layout: main column (title, company, skills as badges, salary range, **markdown-rendered description**) and aside column (metadata). A "Back to Dashboard" link appears at the top.
(Previously: plain-text description; now rendered as markdown)

- **SC-011**: Given a valid job ID, both columns render with all available fields. External link opens in new tab.
- **SC-012**: Given an invalid job ID (404), an Alert shows "Job not found" with a "Back to Dashboard" button.
- **SC-013**: Given no salary data, the salary field is omitted.
