"""Indeed search results HTML fixture used by parser tests.

Spec: REQ-I-006 / REQ-I-009.

THIS IS A SYNTHETIC PLACEHOLDER. The parsers land RED → GREEN against
this fixture so the suite can run without network access. T-010 (later
batch) replaces this file with a REAL capture of the public Indeed
SERP and re-runs the same parser tests against the live DOM. If the
real DOM diverges from the assumptions encoded here, the parser is
updated to match the real DOM — the test stays as the source of truth.

Cards are shaped to mirror the public Indeed SERP:
    - `<div class="job_seen_beacon" data-jk="...">` (the per-job id
      Indeed exposes in its data attributes; the canonical view URL
      is `https://<domain>/viewjob?jk=<data-jk>`).
    - `<h2 class="jobTitle"><a href="/viewjob?jk=<data-jk>">...</a></h2>`
      (the title link).
    - `<span class="companyName">` (the company).
    - `<div class="companyLocation">` (the location).
    - `<span class="date">` (the relative-time string in Spanish:
      `Hoy`, `Hace 2 horas`, `hace 30+ días`, `Hace 3 días`,
      `Recién publicado`).

The placeholder has 15 cards: 3 per date string (5 distinct
relative-time shapes). The card count overshoots the real first-page
size of 10-15 cards so T-006's pagination logic has something to
chew on later.

T-010 will overwrite this file with real captured HTML; the
fixture's `BLOCKED_PAGE_HTML` constant and the `SEARCH_PAGE_HTML`
contract (15+ cards, 5 distinct date strings, every required
selector) are the only invariants the real capture must satisfy.
"""

from __future__ import annotations

# 15 cards: 3 each of 5 required date strings.
#
# Layout: (data-jk, title, company, location, date_text). The ids
# are 9-digit decimals mirroring the `data-jk` shape on the real
# Indeed SERP. Titles/companies/locations are deterministic so the
# parser tests can pin exact field values.
_CARDS: list[tuple[str, str, str, str, str]] = [
    # Hoy (3 cards)
    (
        "100000001",
        "Senior Python Developer",
        "Indeed Co 1",
        "Madrid, Spain",
        "Hoy",
    ),
    (
        "100000002",
        "Python Backend Engineer",
        "Indeed Co 2",
        "Barcelona, Spain",
        "Hoy",
    ),
    (
        "100000003",
        "Data Engineer Python",
        "Indeed Co 3",
        "Valencia, Spain",
        "Hoy",
    ),
    # Hace 2 horas (3 cards)
    (
        "100000004",
        "Junior Python Developer",
        "Indeed Co 4",
        "Sevilla, Spain",
        "Hace 2 horas",
    ),
    (
        "100000005",
        "Python Full-Stack",
        "Indeed Co 5",
        "Bilbao, Spain",
        "Hace 2 horas",
    ),
    (
        "100000006",
        "DevOps Python",
        "Indeed Co 6",
        "Zaragoza, Spain",
        "Hace 2 horas",
    ),
    # hace 30+ días (3 cards)
    (
        "100000007",
        "Python Architect",
        "Indeed Co 7",
        "Málaga, Spain",
        "hace 30+ días",
    ),
    (
        "100000008",
        "QA Automation Python",
        "Indeed Co 8",
        "Granada, Spain",
        "hace 30+ días",
    ),
    (
        "100000009",
        "Python SRE",
        "Indeed Co 9",
        "Alicante, Spain",
        "hace 30+ días",
    ),
    # Hace 3 días (3 cards)
    (
        "100000010",
        "Machine Learning Engineer",
        "Indeed Co 10",
        "Murcia, Spain",
        "Hace 3 días",
    ),
    (
        "100000011",
        "Python Microservices",
        "Indeed Co 11",
        "Valladolid, Spain",
        "Hace 3 días",
    ),
    (
        "100000012",
        "Backend Python Developer",
        "Indeed Co 12",
        "Salamanca, Spain",
        "Hace 3 días",
    ),
    # Recién publicado (3 cards)
    (
        "100000013",
        "Python Tech Lead",
        "Indeed Co 13",
        "Córdoba, Spain",
        "Recién publicado",
    ),
    (
        "100000014",
        "Python Data Scientist",
        "Indeed Co 14",
        "A Coruña, Spain",
        "Recién publicado",
    ),
    (
        "100000015",
        "Python Backend (Remote)",
        "Indeed Co 15",
        "Remote, Spain",
        "Recién publicado",
    ),
]


def _render_cards() -> str:
    """Render the synthetic card list as a search-results page body."""
    parts: list[str] = []
    for jk, title, company, location, date_text in _CARDS:
        parts.append(
            f"""
      <div class="job_seen_beacon" data-jk="{jk}">
        <h2 class="jobTitle">
          <a href="/viewjob?jk={jk}" title="{title}">{title}</a>
        </h2>
        <span class="companyName">{company}</span>
        <div class="companyLocation">{location}</div>
        <span class="date">{date_text}</span>
      </div>"""
        )
    return "\n".join(parts)


SEARCH_PAGE_HTML = f"""<!DOCTYPE html>
<html>
<head>
  <title>30 Python jobs in Madrid - Indeed</title>
</head>
<body>
  <main>
    <ul class="jobsearch-ResultsList">
{_render_cards()}
    </ul>
  </main>
</body>
</html>
"""

# A synthetic Cloudflare "Security Check" page used by `is_indeed_blocked`
# tests. The detector recognises (a) a `<meta http-equiv="refresh">` that
# points at the challenge URL, (b) a `<title>` containing "Security Check"
# OR "Access Denied", and (c) a `cf-mitigated: challenge` hint in any
# meta tag. The fixture has all three so the detector has at least one
# signal to fire on even if the heuristic surface drifts.
BLOCKED_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta http-equiv="refresh" content="0;url=https://www.indeed.com/cdp">
  <meta name="cf-mitigated" content="challenge">
  <title>Security Check | Indeed</title>
</head>
<body>
  <h1>Security Check</h1>
  <p>Please verify you are a human to continue.</p>
</body>
</html>
"""
