"""LinkedIn search results HTML fixture: the canonical structured-location URL.

Spec: REQ-015 / REQ-024. Captured on 2026-06-02 from a real public
LinkedIn job search with the structured location format:

    https://www.linkedin.com/jobs/search?keywords=python&location=
        M%C3%A1laga%2C%20Andaluc%C3%ADa%2C%20Spain

Two key differences from the regular SERP fixture
(`tests/fixtures/linkedin_search.py`):

1. The cards still use `div[data-entity-urn]` and
   `base-search-card__*` / `job-search-card__*` classes, so the
   per-field parsers work unchanged.

2. The page CONTAINS HIDDEN SIGN-IN MODALS that are always
   present in the public SERP HTML, just hidden by CSS. The
   `alert-toggle-sign-in-modal` includes a `<form id="login">`
   element. A naive `is_block_page` that scans for
   `form#login` would mistake this for an auth wall and 502
   the request even though the page is the legitimate search
   results. The `is_block_page` implementation is expected to
   short-circuit on the presence of job cards (a real result
   page always has at least one).

Three cards, copied verbatim from the live capture. The
hidden sign-in modal is included to make the regression
visible: a future change that re-orders `is_block_page` to
check forms first would break this fixture.
"""

MALAGA_CANONICAL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta name="pageKey" content="d_jobs_guest_search">
  <meta name="linkedin:pageTag" content="urlType=jserp_custom;emptyResult=false">
  <title>20 Python jobs in Málaga</title>
</head>
<body dir="ltr" class="">
  <div class="base-serp-page">

    <!-- Hidden sign-in modal that is ALWAYS present in the public SERP.
         Contains a <form id="login"> which a naive block-page detector
         would mis-classify. The real signal is: cards present == not
         blocked. -->
    <div id="alert-toggle-sign-in-modal"
         class="modal modal--contextual-sign-in
                modal--contextual-sign-in-v2
                modal--contextual-sign-in-v2--stacked">
      <div class="modal__overlay opacity-0 invisible pointer-events-none"
           aria-hidden="true">
        <section role="dialog" tabindex="-1" class="modal__wrapper">
          <button aria-label="Dismiss" class="modal__dismiss">×</button>
          <div class="modal__main">
            <h2 id="alert-toggle-sign-in-modal-modal-header">
              Sign in to set job alerts for "Python" roles.
            </h2>
            <form id="login" action="/checkpoint" novalidate="">
              <label for="csm-v2_session_key">Email or phone</label>
              <input id="csm-v2_session_key" name="session_key" type="text" />
              <label for="csm-v2_session_password">Password</label>
              <input id="csm-v2_session_password" name="session_password" type="password" />
              <button type="submit">Sign in</button>
            </form>
            <button>Sign in with Email</button>
          </div>
        </section>
      </div>
    </div>

    <main id="main-content" role="main">
      <ul class="jobs-search__results-list">
        <li>
          <div class="base-card base-search-card job-search-card job-search-card--active"
               data-entity-urn="urn:li:jobPosting:4354113538"
               data-column="1" data-row="1">
            <a class="base-card__full-link"
               href="https://es.linkedin.com/jobs/view/python-developer-at-version-1-4354113538?position=1&pageNum=0&refId=foo&trackingId=bar">
              <span class="sr-only">Python Developer</span>
            </a>
            <h3 class="base-search-card__title">Python Developer</h3>
            <h4 class="base-search-card__subtitle">Version 1</h4>
            <span class="job-search-card__location">Málaga, Andalusia, Spain</span>
            <time class="job-search-card__listdate" datetime="2026-05-29">4 days ago</time>
          </div>
        </li>
        <li>
          <div class="base-card base-search-card job-search-card"
               data-entity-urn="urn:li:jobPosting:4391577086"
               data-column="1" data-row="2">
            <a class="base-card__full-link"
               href="https://es.linkedin.com/jobs/view/python-backend-developer-at-transperfect-4391577086?position=2&pageNum=0&refId=foo&trackingId=bar">
              <span class="sr-only">Python Backend Developer</span>
            </a>
            <h3 class="base-search-card__title">Python Backend Developer</h3>
            <h4 class="base-search-card__subtitle">TransPerfect</h4>
            <span class="job-search-card__location">Málaga, Andalusia, Spain</span>
            <time class="job-search-card__listdate" datetime="2026-03-10">2 months ago</time>
          </div>
        </li>
        <li>
          <div class="base-card base-search-card job-search-card"
               data-entity-urn="urn:li:jobPosting:4417875990"
               data-column="1" data-row="3">
            <a class="base-card__full-link"
               href="https://es.linkedin.com/jobs/view/senior-backend-python-developer-at-altia-4417875990?position=3&pageNum=0&refId=foo&trackingId=bar">
              <span class="sr-only">Senior Backend Python Developer</span>
            </a>
            <h3 class="base-search-card__title">Senior Backend Python Developer</h3>
            <h4 class="base-search-card__subtitle">Altia</h4>
            <span class="job-search-card__location">Málaga, Andalusia, Spain</span>
            <time class="job-search-card__listdate" datetime="2026-05-25">1 week ago</time>
          </div>
        </li>
      </ul>
    </main>
  </div>
</body>
</html>
"""
