"""LinkedIn search results HTML fixture used by parser tests.

Spec: REQ-015 / REQ-024. The parser tests use a recorded HTML fragment
instead of a live network fetch. The fixture is best-effort; live
verification in T-010 confirms whether the selectors match the real DOM.
"""

# Two result cards. The first carries every field including `<time
# datetime=...>`; the second has the same shape but omits the `<time>`
# element so `parse_posted_at` can return `None`.
SEARCH_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>385 Python jobs in Madrid, Spain</title>
</head>
<body>
  <main class="jobs-search">
    <ul class="jobs-search__results-list">
      <li class="result-card" data-entity-urn="urn:li:jobPosting:3850000001">
        <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3850000001/?trk=public_jobs_jobs-search-results_search-card">
          <h3 class="base-card__title">Senior Python Developer</h3>
        </a>
        <h4 class="base-card__subtitle">Acme Corp</h4>
        <span class="job-search-card__location">Madrid, Spain</span>
        <time class="job-search-card__listdate" datetime="2026-05-01T00:00:00+00:00">
          1 day ago
        </time>
      </li>
      <li class="result-card" data-entity-urn="urn:li:jobPosting:3850000002">
        <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3850000002/">
          <h3 class="base-card__title">Backend Engineer</h3>
        </a>
        <h4 class="base-card__subtitle">Globex Inc</h4>
        <span class="job-search-card__location">Barcelona, Spain</span>
      </li>
    </ul>
  </main>
</body>
</html>
"""

# A LinkedIn auth-wall / verification page (used by `is_block_page` tests).
BLOCK_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Sign In | LinkedIn</title>
</head>
<body class="auth-wall">
  <main>
    <h1>Sign in</h1>
    <form id="login" action="/checkpoint">
      <input name="session_key" />
      <input name="session_password" type="password" />
      <button type="submit">Sign in</button>
    </form>
  </main>
</body>
</html>
"""
