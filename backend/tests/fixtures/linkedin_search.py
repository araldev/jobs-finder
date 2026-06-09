"""LinkedIn search results HTML fixture used by parser tests.

Spec: REQ-015 / REQ-024. The parser tests use a recorded HTML fragment
instead of a live network fetch.

The current fixture was generated from a real capture of the public
LinkedIn job search page (https://www.linkedin.com/jobs/search/) on
2026-06-02. Real cards use `<div data-entity-urn="urn:li:jobPosting:<id>">`
containers with `base-search-card__title` / `base-search-card__subtitle` /
`job-search-card__location` / `job-search-card__listdate` children. The
earlier fixture used `li` and `base-card__*` classes that the live DOM
no longer emits; this is the corrected version.

Three cards:
- Card 1: every field, including a `<time>` with a real `datetime` value.
- Card 2: every field, different job id and metadata.
- Card 3: no `<time>` element, so `parse_posted_at` returns `None` (this
  exercises the spec's "missing" path, not the "malformed" path).
"""

SEARCH_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>90 Python jobs in Madrid</title>
</head>
<body>
  <main>
    <ul>
      <div
        class="base-card base-search-card job-search-card"
        data-entity-urn="urn:li:jobPosting:4217873836"
      >
        <a
          class="base-card__full-link"
          href="https://es.linkedin.com/jobs/view/developer-python-aws-at-plexus-tech-4217873836?position=1&pageNum=0&refId=foo&trackingId=bar"
        >
          <span class="sr-only">Developer Python/AWS</span>
        </a>
        <h3 class="base-search-card__title">Developer Python/AWS</h3>
        <h4 class="base-search-card__subtitle">Plexus Tech</h4>
        <span class="job-search-card__location">Madrid, Community of Madrid, Spain</span>
        <time class="job-search-card__listdate" datetime="2025-04-29">1 year ago</time>
      </div>
      <div
        class="base-card base-search-card job-search-card"
        data-entity-urn="urn:li:jobPosting:4349673400"
      >
        <a
          class="base-card__full-link"
          href="https://es.linkedin.com/jobs/view/python-programmer-analyst-at-plexus-tech-4349673400?position=2&pageNum=0&refId=foo&trackingId=bar"
        >
          <span class="sr-only">Python Programmer Analyst</span>
        </a>
        <h3 class="base-search-card__title">Python Programmer Analyst</h3>
        <h4 class="base-search-card__subtitle">Plexus Tech</h4>
        <span class="job-search-card__location">Madrid, Community of Madrid, Spain</span>
        <time class="job-search-card__listdate" datetime="2025-05-02">1 year ago</time>
      </div>
      <div
        class="base-card base-search-card job-search-card"
        data-entity-urn="urn:li:jobPosting:4414091381"
      >
        <a
          class="base-card__full-link"
          href="https://es.linkedin.com/jobs/view/python-developer-at-statkraft-4414091381?position=3&pageNum=0&refId=foo&trackingId=bar"
        >
          <span class="sr-only">Python Developer</span>
        </a>
        <h3 class="base-search-card__title">Python Developer</h3>
        <h4 class="base-search-card__subtitle">Statkraft</h4>
        <span class="job-search-card__location">Madrid, Community of Madrid, Spain</span>
      </div>
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
