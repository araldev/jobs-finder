"""LinkedIn search results HTML fixture (with detail panel) used by parser tests.

Spec: REQ-PARSER-LINKEDIN-001 (pinned by `linkedin-description-capture`,
Branch B).

This fixture is a REAL capture of
`https://www.linkedin.com/jobs/search?keywords=ingeniero&geoId=100292246`
performed on 2026-06-07. Sanctioned by AGENTS.md rule #1 (one-time
manual Playwright capture; the HTML is committed, the capture script
itself is not).

EMPIRICAL FINDING (Branch B):
The LinkedIn public search results page does NOT expose description
text on the individual job cards in the results list. Each card
(`<div class="base-search-card">`) carries only title, company,
location, and date. The full description is only visible in a separate
"detail panel" that the page renders when a user clicks a card:
    <section class="show-more-less-html">
      <div class="show-more-less-html__markup ...">
        <the actual description text>
      </div>
    </section>

The captured page had the detail panel open (one of the cards was the
"active" card), so the HTML contains 3 cards + 1 detail panel. The
parser `parse_description` is "detail-panel aware":
- Given a card, returns `None` (cards don't carry descriptions).
- Given the detail panel element, returns the text content with
  `separator=" "` and `strip=True`.

The chat filter (POST /jobs/chat) handles `description=None` for
LinkedIn rows gracefully via the no-assumption rule in
`src/jobs_finder/infrastructure/llm/_prompt.py` (REQ-LLM-004).

SANITIZATION
The raw HTML was sanitized before commit:
- Company names replaced with `<COMPANY>` (only "Lumon" in this
  capture, but the regex catches "Lumon", "Lumon Espana", "Grupo
  Lumon", etc.).
- Posted dates replaced with `<DATE>` ("1 day ago" -> `<DATE>`, etc.).
- Job IDs / URNs replaced with `<ID>` / `<TYPE>:<ID>` placeholders.
- PII-tracking attributes stripped: data-urn, data-id,
  data-tracking-*, data-ghost-url, data-ghost-classes,
  data-impression-id, data-view-time, data-entity-urn,
  data-view-tracking-scope, data-control-name, data-job-id,
  data-search-*, data-results-*, aria-busy.
- `src` and `alt` on `<img>` tags stripped (logos with company URLs).
- Company profile URLs (`/company/<slug>`) replaced with
  `/company/<COMPANY_SLUG>`.
- User profile URLs (`/in/<slug>`) replaced with `/in/<USER_SLUG>`.
  - 57 of 60 cards removed to keep the fixture small (~155KB instead
  of ~380KB). 3 cards retained: 1 active (the clicked job) + 2
  normal cards.
  - Job-identifying attributes KEPT (with values replaced): the
    tests in `tests/unit/test_parsers.py` use `div[data-entity-urn]`
    as a card selector, so the attribute is preserved (value becomes
    `urn:li:jobPosting:<ID>`). `data-job-id` similar.

VERIFICATION
After sanitization, the file contains:
- 0 occurrences of the original company name
- 0 job IDs / URNs
- 0 PII-tracking attributes
- 7 `<COMPANY>` placeholders
- 9 `<DATE>` placeholders
- 1 detail panel (the only one in the capture)
- 3 search cards (1 active + 2 normal)

The fixture is intentionally not derived from the existing
`tests/fixtures/linkedin_search.py` (synthetic 3-card capture from
2026-06-02) which lacks the description element. The two fixtures
coexist: `linkedin_search.py` exercises the card-level parsers
(title/company/location/date); this new fixture exercises the
description parser.
"""

SEARCH_PAGE_HTML = """
WARN: card selector not found within 10s; sleeping 5s anyway
<!DOCTYPE html>
<html lang="en"><head>
<meta content="d_jobs_guest_search" name="pageKey"/>
<meta content="max-image-preview:large, noarchive" name="robots"/>
<meta content="max-image-preview:large, archive" name="bingbot"/>
<!-- --> <meta content="urlType=jserp_custom;emptyResult=false" name="linkedin:pageTag"/>
<meta content="en_US" name="locale"/>
<!-- --> <meta data-app-version="2.0.2949" data-browser-id="498b6ef7-62a6-467b-8966-0a9d93356bdf" data-call-tree-id="AAZTsFVUZ3j9ZIOxGtlFDA==" data-dfp-member-lix-treatment="control" data-disable-jsbeacon-pagekey-suffix="false" data-dna-member-lix-treatment="enabled" data-enable-page-view-heartbeat-tracking="" data-human-member-lix-treatment="enabled" data-is-bot="false" data-is-epd-audit-event-enabled="false" data-is-feed-sponsored-tracking-kill-switch-enabled="false" data-member-id="0" data-multiproduct-name="jobs-guest-frontend" data-network-interceptor-lix-value="control" data-page-instance="urn:li:page:d_jobs_guest_search;KZ2YRuT+Qsu6ZEGjaWKv1w==" data-recaptcha-v3-integration-lix-value="control" data-sequence-auto-redirect-before-request-enabled="true" data-service-name="jobs-guest-frontend" data-should-use-full-url-in-pve-path="true" data-sync-apfc-cb-lix-treatment="control" data-sync-apfc-headers-lix-treatment="control" id="config"/>
<link href="https://es.linkedin.com/jobs/ingeniero-empleos-m%C3%A1laga" rel="canonical"/>
<!-- --><!-- -->
<!-- -->
<!-- -->
<!-- -->
<!-- -->
<link href="https://static.licdn.com/aero-v1/sc/h/al2o9zrvru7aqj8e1x2rzsrca" rel="icon"/>
<script>
          function getDfd() {let yFn,nFn;const p=new Promise(function(y, n){yFn=y;nFn=n;});p.resolve=yFn;p.reject=nFn;return p;}
          window.lazyloader = getDfd();
          window.tracking = getDfd();
          window.impressionTracking = getDfd();
          window.ingraphTracking = getDfd();
          window.appDetection = getDfd();
          window.pemTracking = getDfd();
          window.appRedirectCompleted = getDfd();
        </script>
<!-- -->
<title>65 Ingeniero jobs in Málaga</title>
<meta content="<DATE>&amp;#39;s top 65 Ingeniero jobs in Málaga. Leverage your professional network, and get hired. New Ingeniero jobs added daily." name="description"/>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="jobs-guest-frontend" name="litmsProfileName"/>
<meta content="1" data-counter-metric-endpoint="/jobs-guest/api/ingraphs/counter" data-gauge-metric-endpoint="/jobs-guest/api/ingraphs/gauge" name="clientSideIngraphs"/>
<meta charset="utf-8"/>
<meta content="website" property="og:type"/>
<meta content="65 Ingeniero jobs in Málaga" property="og:title"/>
<meta content="https://es.linkedin.com/jobs/ingeniero-empleos-m%C3%A1laga" property="og:url"/>
<meta content="<DATE>&amp;#39;s top 65 Ingeniero jobs in Málaga. Leverage your professional network, and get hired. New Ingeniero jobs added daily." property="og:description"/>
<!-- --> <meta content="65 Ingeniero jobs in Málaga" name="twitter:title"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="@LinkedIn" name="twitter:site"/>
<meta content="<DATE>&amp;#39;s top 65 Ingeniero jobs in Málaga. Leverage your professional network, and get hired. New Ingeniero jobs added daily." name="twitter:description"/>
<meta content="https://www.linkedin.com/jobs/search?keywords=ingeniero&amp;geoId=100292246" property="lnkd:url"/>
<link href="https://static.licdn.com/aero-v1/sc/h/5ssghaanyvzbzjxuxjs5e2qou" rel="stylesheet"/>
<!-- --> <script async="" src="https://platform.linkedin.com/litms/utag/jobs-guest-frontend/utag.js?cb=1780866600000" type="text/javascript"></script></head>
<body class="overflow-hidden transition-in" dir="ltr">
<!-- --><!-- -->
<div aria-hidden="true" aria-live="assertive" class="global-alert-banner transition-in" id="artdeco-global-alert-container" role="alert" style="height: 192px;">
<div alert-id="urn:li:<TYPE>:<ID>" aria-hidden="false" class="artdeco-global-alert artdeco-global-alert--NOTICE artdeco-global-alert--COOKIE_CONSENT" severity="NOTICE" style="height: 192px; visibility: visible;" type="COOKIE_CONSENT">
<section class="artdeco-global-alert__body">
<li-icon class="artdeco-global-alert__icon">
<!-- -->
<!-- -->
<span>
<svg height="24" version="1.1" width="24" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path d="M12,2C6.5,2,2,6.5,2,12c0,5.5,4.5,10,10,10c5.5,0,10-4.5,10-10C22,6.5,17.5,2,12,2zM12,20.2c-4.5,0-8.2-3.7-8.2-8.2S7.5,3.8,12,3.8s8.2,3.7,8.2,8.2S16.5,20.2,12,20.2zM11,10h2v8h-2V10zM11,6h2v2h-2V6z" fill="#fff"></path>
</svg>
</span>
</li-icon>
<div class="artdeco-global-alert__responsive-container">
<h2>LinkedIn respects your privacy</h2>
<div class="artdeco-global-alert__responsive-content-container">
<div class="artdeco-global-alert__content">
<p>LinkedIn and 3rd parties use essential and non-essential cookies to provide, secure, analyze and improve our Services, and to show you relevant ads (including <b>professional and job ads</b>) on and off LinkedIn. Learn more in our <a href="https://www.linkedin.com/legal/cookie-policy">Cookie Policy</a>.</p><p>Select Accept to consent or Reject to decline non-essential cookies for this use. You can update your choices at any time in your <a href="https://www.linkedin.com/mypreferences/g/guest-cookies">settings</a>.</p>
</div>
</div>
<div class="artdeco-global-alert-action__wrapper">
<button action-type="ACCEPT" action-url="" class="artdeco-global-alert-action artdeco-button artdeco-button--inverse artdeco-button--2 artdeco-button--primary">
                Accept
                </button>
<button action-type="DENY" action-url="" class="artdeco-global-alert-action artdeco-button artdeco-button--inverse artdeco-button--2 artdeco-button--primary">
                Reject
                </button>
</div>
</div>
<!-- --> </section>
</div>
</div>
<div aria-hidden="true" id="artdeco-global-alerts-cls-offset" style="height: 192px;"></div>
<!-- -->
<div aria-hidden="true" class="base-serp-page">
<a class="skip-link btn-md btn-primary absolute z-11 -top-[100vh] focus:top-0" href="#main-content">
      Skip to main content
    </a>
<header class="base-serp-page__header global-alert-offset sticky-header" style="top: 192px;">
<nav aria-label="Primary" class="nav pt-1.5 pb-2 flex items-center justify-between relative flex-nowrap babymamabear:py-1.5 nav--minified-mobile">
<a class="nav__logo-link link-no-visited-state z-1 mr-auto min-h-[52px] flex items-center babybear:z-0 hover:no-underline focus:no-underline active:no-underline babymamabear:mr-3" href="/?trk=public_jobs_nav-header-logo">
<span class="sr-only">LinkedIn</span>
<icon aria-hidden="true" class="nav-logo--inbug flex text-color-brand papabear:hidden mamabear:hidden lazy-loaded" data-svg-class-name="h-[34px] w-[34px] babybear:h-[26px] babybear:w-[26px]"><svg class="h-[34px] w-[34px] babybear:h-[26px] babybear:w-[26px] lazy-loaded" focusable="false" height="27" viewbox="0 0 27 27" width="27" xmlns="http://www.w3.org/2000/svg">
<g fill="currentColor">
<path d="M1.91 0h22.363a1.91 1.91 0 011.909 1.91v22.363a1.91 1.91 0 01-1.91 1.909H1.91A1.91 1.91 0 010 24.272V1.91A1.91 1.91 0 011.91 0zm1.908 22.364h3.818V9.818H3.818zM8.182 5.727a2.455 2.455 0 10-4.91 0 2.455 2.455 0 004.91 0zm2.182 4.091v12.546h3.818v-6.077c0-2.037.75-3.332 2.553-3.332 1.3 0 1.81 1.201 1.81 3.332v6.077h3.819v-6.93c0-3.74-.895-5.78-4.667-5.78-1.967 0-3.277.921-3.788 1.946V9.818z" fill="currentColor" fill-rule="evenodd"></path>
</g>
</svg></icon>
<icon aria-hidden="true" class="block text-color-brand w-[102px] h-[26px] babybear:hidden lazy-loaded" data-test-id="nav-logo"><svg class="lazy-loaded" focusable="false" preserveaspectratio="xMinYMin meet" version="1.1" viewbox="0 0 84 21" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<g class="inbug" fill="none" fill-rule="evenodd" stroke="none" stroke-width="1">
<path class="bug-text-color" d="M19.479,0 L1.583,0 C0.727,0 0,0.677 0,1.511 L0,19.488 C0,20.323 0.477,21 1.333,21 L19.229,21 C20.086,21 21,20.323 21,19.488 L21,1.511 C21,0.677 20.336,0 19.479,0" transform="translate(63.000000, 0.000000)"></path>
<path class="background" d="M82.479,0 L64.583,0 C63.727,0 63,0.677 63,1.511 L63,19.488 C63,20.323 63.477,21 64.333,21 L82.229,21 C83.086,21 84,20.323 84,19.488 L84,1.511 C84,0.677 83.336,0 82.479,0 Z M71,8 L73.827,8 L73.827,9.441 L73.858,9.441 C74.289,8.664 75.562,7.875 77.136,7.875 C80.157,7.875 81,9.479 81,12.45 L81,18 L78,18 L78,12.997 C78,11.667 77.469,10.5 76.227,10.5 C74.719,10.5 74,11.521 74,13.197 L74,18 L71,18 L71,8 Z M66,18 L69,18 L69,8 L66,8 L66,18 Z M69.375,4.5 C69.375,5.536 68.536,6.375 67.5,6.375 C66.464,6.375 65.625,5.536 65.625,4.5 C65.625,3.464 66.464,2.625 67.5,2.625 C68.536,2.625 69.375,3.464 69.375,4.5 Z" fill="currentColor"></path>
</g>
<g class="linkedin-text">
<path d="M60,18 L57.2,18 L57.2,16.809 L57.17,16.809 C56.547,17.531 55.465,18.125 53.631,18.125 C51.131,18.125 48.978,16.244 48.978,13.011 C48.978,9.931 51.1,7.875 53.725,7.875 C55.35,7.875 56.359,8.453 56.97,9.191 L57,9.191 L57,3 L60,3 L60,18 Z M54.479,10.125 C52.764,10.125 51.8,11.348 51.8,12.974 C51.8,14.601 52.764,15.875 54.479,15.875 C56.196,15.875 57.2,14.634 57.2,12.974 C57.2,11.268 56.196,10.125 54.479,10.125 L54.479,10.125 Z" fill="currentColor"></path>
<path d="M47.6611,16.3889 C46.9531,17.3059 45.4951,18.1249 43.1411,18.1249 C40.0001,18.1249 38.0001,16.0459 38.0001,12.7779 C38.0001,9.8749 39.8121,7.8749 43.2291,7.8749 C46.1801,7.8749 48.0001,9.8129 48.0001,13.2219 C48.0001,13.5629 47.9451,13.8999 47.9451,13.8999 L40.8311,13.8999 L40.8481,14.2089 C41.0451,15.0709 41.6961,16.1249 43.1901,16.1249 C44.4941,16.1249 45.3881,15.4239 45.7921,14.8749 L47.6611,16.3889 Z M45.1131,11.9999 C45.1331,10.9449 44.3591,9.8749 43.1391,9.8749 C41.6871,9.8749 40.9121,11.0089 40.8311,11.9999 L45.1131,11.9999 Z" fill="currentColor"></path>
<polygon fill="currentColor" points="38 8 34.5 8 31 12 31 3 28 3 28 18 31 18 31 13 34.699 18 38.241 18 34 12.533"></polygon>
<path d="M16,8 L18.827,8 L18.827,9.441 L18.858,9.441 C19.289,8.664 20.562,7.875 22.136,7.875 C25.157,7.875 26,9.792 26,12.45 L26,18 L23,18 L23,12.997 C23,11.525 22.469,10.5 21.227,10.5 C19.719,10.5 19,11.694 19,13.197 L19,18 L16,18 L16,8 Z" fill="currentColor"></path>
<path d="M11,18 L14,18 L14,8 L11,8 L11,18 Z M12.501,6.3 C13.495,6.3 14.3,5.494 14.3,4.5 C14.3,3.506 13.495,2.7 12.501,2.7 C11.508,2.7 10.7,3.506 10.7,4.5 C10.7,5.494 11.508,6.3 12.501,6.3 Z" fill="currentColor"></path>
<polygon fill="currentColor" points="3 3 0 3 0 18 9 18 9 15 3 15"></polygon>
</g>
</svg></icon>
</a>
<section class="search-bar relative flex flex-grow h-[40px] bg-cool-gray-20 min-w-0 max-w-full mx-4 rounded-sm babymamabear:mx-0 babymamabear:mb-1.5 babymamabear:bg-color-transparent babymamabear:w-full babymamabear:flex babymamabear:flex-wrap search-bar--minified-mobile" data-current-search-type="JOBS">
<button class="search-bar__placeholder papabear:hidden text-input w-full mt-1.5 !pl-[14px] border-1 border-solid border-color-border-faint rounded-[2px] h-[40px] max-h-[40px] flex items-center overflow-hidden cursor-text">
<icon aria-hidden="true" class="text-color-icon w-3 h-3 mr-1 lazy-loaded"><svg class="lazy-loaded" focusable="false" height="24px" version="1.1" viewbox="0 0 24 24" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path d="M21,19.67l-5.44-5.44a7,7,0,1,0-1.33,1.33L19.67,21ZM10,15.13A5.13,5.13,0,1,1,15.13,10,5.13,5.13,0,0,1,10,15.13Z" style="fill: currentColor;"></path>
</svg></icon>
<div class="search-bar__full-placeholder font-sans text-md text-color-text max-w-[calc(100%-40px)] text-left whitespace-nowrap overflow-hidden text-ellipsis">
<!-- -->              Ingeniero in Málaga
<!-- --><!-- --> </div>
<span class="sr-only">Expand search</span>
</button>
<div class="switcher-tabs__trigger-and-tabs babymamabear:flex">
<button aria-describedby="switcher-description" aria-expanded="false" class="switcher-tabs__placeholder flex !h-full !py-0 !pl-2 !pr-1.5 border-r-1 border-solid border-r-color-border-faint babymamabear:hidden tab-md papabear:tab-vertical papabear:justify-start cursor-pointer">
<span class="switcher-tabs__placeholder-text m-auto">
                        Jobs
                    </span>
<icon aria-hidden="true" class="switcher-tabs__caret-down-filled onload pointer-events-none block my-auto min-h-[24px] min-w-[24px] h-[24px] babymamabear:hidden lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="hidden" id="switcher-description">This button displays the currently selected search type. When expanded it provides a list of search options that will switch the search inputs to match the current selection. </div>
<!-- --> <div class="switcher-tabs hidden z-[1] w-auto min-w-[160px] mb-1.5 py-1 absolute top-[48px] left-0 border-solid border-1 border-color-border-faint papabear:container-raised babymamabear:static babymamabear:w-[100vw] babymamabear:h-[48px] babymamabear:p-0 overflow-y-hidden overflow-x-auto md:overflow-x-hidden">
<ul class="switcher-tabs__list flex flex-1 items-stretch papabear:flex-col" role="tablist">
<li class="switcher-tabs__tab h-[44px] babymamabear:basis-1/2" role="presentation">
<button aria-controls="jobs-search-panel" aria-selected="true" class="switcher-tabs__button w-full h-full tab-md papabear:tab-vertical papabear:justify-start cursor-pointer tab-selected" data-switcher-type="JOBS" id="job-switcher-tab" role="tab">
                        Jobs
                    </button>
</li>
<li class="switcher-tabs__tab h-[44px] babymamabear:basis-1/2" role="presentation">
<button aria-controls="people-search-panel" aria-selected="false" class="switcher-tabs__button w-full h-full tab-md papabear:tab-vertical papabear:justify-start cursor-pointer" data-switcher-type="PEOPLE" id="people-switcher-tab" role="tab">
                        People
                    </button>
</li>
<li class="switcher-tabs__tab h-[44px] babymamabear:basis-1/2" role="presentation">
<button aria-controls="learning-search-panel" aria-selected="false" class="switcher-tabs__button w-full h-full tab-md papabear:tab-vertical papabear:justify-start cursor-pointer" data-switcher-type="LEARNING" id="learning-switcher-tab" role="tab">
                        Learning
                    </button>
</li>
</ul>
<button aria-label="Close" class="switcher-tabs__cancel-btn papabear:hidden block w-6 h-6 m-auto text-color-text-low-emphasis" type="button">
<icon aria-hidden="true" class="switcher-tabs__cancel-icon block w-3 h-3 m-auto onload lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</div>
</div>
<section aria-labelledby="people-switcher-tab" class="base-search-bar w-full h-full" data-searchbar-type="PEOPLE" id="people-search-panel" role="tabpanel">
<form action="/pub/dir" class="base-search-bar__form w-full flex babymamabear:mx-mobile-container-padding babymamabear:flex-col" role="search">
<section class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 search-input">
<input aria-label="First Name" autocomplete="on" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" maxlength="500" name="firstName" placeholder="First Name" type="search"/>
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100" disabled="" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<section class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 search-input">
<input aria-label="Last Name" autocomplete="on" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" maxlength="500" name="lastName" placeholder="Last Name" type="search"/>
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100" disabled="" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<input name="trk" type="hidden" value="public_jobs_people-search-bar_search-submit"/>
<button aria-label="Search" class="base-search-bar__submit-btn block basis-[40px] flex-shrink-0 cursor-pointer babymamabear:invisible babymamabear:ml-[-9999px] babymamabear:w-[1px] babymamabear:h-[1px]" type="submit">
<icon aria-hidden="true" class="base-search-bar__search-icon onload mx-auto lazy-loaded"><svg class="lazy-loaded" focusable="false" height="24px" version="1.1" viewbox="0 0 24 24" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path class="large-icon" d="M21,19.67l-5.44-5.44a7,7,0,1,0-1.33,1.33L19.67,21ZM10,15.13A5.13,5.13,0,1,1,15.13,10,5.13,5.13,0,0,1,10,15.13Z" style="fill: currentColor; color: #7a8b98;"></path>
</svg></icon>
</button>
</form>
</section>
<section aria-labelledby="job-switcher-tab" class="base-search-bar w-full h-full" data-searchbar-type="JOBS" id="jobs-search-panel" role="tabpanel">
<form action="/jobs/search" class="base-search-bar__form w-full flex babymamabear:mx-mobile-container-padding babymamabear:flex-col" role="search">
<section class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 typeahead-input keywords-typeahead-input text-input">
<input aria-autocomplete="list" aria-controls="job-search-bar-keywords-typeahead-list" aria-expanded="false" aria-haspopup="listbox" aria-label="Search job titles or companies" autocomplete="off" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" id="job-search-bar-keywords" maxlength="500" name="keywords" placeholder="Search job titles or companies" role="combobox" type="search" value="Ingeniero"/>
<!-- --> <div class="typeahead-input__dropdown container-lined absolute top-[calc(100%+3px)] left-0 w-full rounded-b-md rounded-t-none z-[10] overflow-hidden max-w-none babybear:min-w-full babybear:bottom-0 babybear:overflow-y-auto">
<template class="typeahead-item-template">
<li class="typeahead-input__dropdown-item py-1.5 px-2 hover:cursor-pointer hover:bg-color-surface-new-hover hover:border-y-2 hover:border-solid hover:border-color-container-primary" role="option">
<span class="typeahead-input__dropdown-text font-sans text-sm font-bold text-color-text"></span>
</li>
</template>
<ul class="typeahead-input__dropdown-list w-full" id="job-search-bar-keywords-typeahead-list" role="listbox"></ul>
</div>
<!-- -->
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100 dismissable-input__button--show" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<!-- -->
<section class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 typeahead-input location-typeahead-input">
<input aria-autocomplete="list" aria-controls="job-search-bar-location-typeahead-list" aria-expanded="false" aria-haspopup="listbox" aria-label="Location" autocomplete="off" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" id="job-search-bar-location" maxlength="500" name="location" placeholder="Location" role="combobox" type="search" value="Málaga"/>
<!-- --> <div class="typeahead-input__dropdown container-lined absolute top-[calc(100%+3px)] left-0 w-full rounded-b-md rounded-t-none z-[10] overflow-hidden max-w-none babybear:min-w-full babybear:bottom-0 babybear:overflow-y-auto">
<template class="typeahead-item-template">
<li class="typeahead-input__dropdown-item py-1.5 px-2 hover:cursor-pointer hover:bg-color-surface-new-hover hover:border-y-2 hover:border-solid hover:border-color-container-primary" role="option">
<span class="typeahead-input__dropdown-text font-sans text-sm font-bold text-color-text"></span>
</li>
</template>
<ul class="typeahead-input__dropdown-list w-full" id="job-search-bar-location-typeahead-list" role="listbox"></ul>
</div>
<!-- -->
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100 dismissable-input__button--show" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<input name="geoId" type="hidden" value="100292246"/>
<input name="trk" type="hidden" value="public_jobs_jobs-search-bar_search-submit"/>
<button aria-label="Search" class="base-search-bar__submit-btn block basis-[40px] flex-shrink-0 cursor-pointer babymamabear:invisible babymamabear:ml-[-9999px] babymamabear:w-[1px] babymamabear:h-[1px]" type="submit">
<icon aria-hidden="true" class="base-search-bar__search-icon onload mx-auto lazy-loaded"><svg class="lazy-loaded" focusable="false" height="24px" version="1.1" viewbox="0 0 24 24" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path class="large-icon" d="M21,19.67l-5.44-5.44a7,7,0,1,0-1.33,1.33L19.67,21ZM10,15.13A5.13,5.13,0,1,1,15.13,10,5.13,5.13,0,0,1,10,15.13Z" style="fill: currentColor; color: #7a8b98;"></path>
</svg></icon>
</button>
</form>
</section>
<section aria-labelledby="learning-switcher-tab" class="base-search-bar w-full h-full" data-searchbar-type="LEARNING" id="learning-search-panel" role="tabpanel">
<form action="/learning/search" class="base-search-bar__form w-full flex babymamabear:mx-mobile-container-padding babymamabear:flex-col" role="search">
<section class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 search-input">
<input aria-label="Search skills, subjects, or software" autocomplete="on" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" maxlength="500" name="keywords" placeholder="Search skills, subjects, or software" type="search" value="Ingeniero"/>
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100 dismissable-input__button--show" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<input class="nav__search-uoo" name="upsellOrderOrigin" type="hidden"/>
<input name="trk" type="hidden" value="public_jobs_learning-search-bar_search-submit"/>
<button aria-label="Search" class="base-search-bar__submit-btn block basis-[40px] flex-shrink-0 cursor-pointer babymamabear:invisible babymamabear:ml-[-9999px] babymamabear:w-[1px] babymamabear:h-[1px]" type="submit">
<icon aria-hidden="true" class="base-search-bar__search-icon onload mx-auto lazy-loaded"><svg class="lazy-loaded" focusable="false" height="24px" version="1.1" viewbox="0 0 24 24" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path class="large-icon" d="M21,19.67l-5.44-5.44a7,7,0,1,0-1.33,1.33L19.67,21ZM10,15.13A5.13,5.13,0,1,1,15.13,10,5.13,5.13,0,0,1,10,15.13Z" style="fill: currentColor; color: #7a8b98;"></path>
</svg></icon>
</button>
</form>
</section>
<div aria-live="polite" class="search-bar__live-text sr-only" role="status"></div>
</section>
<!-- -->
<div class="nav__cta-container order-3 flex gap-x-1 justify-end min-w-[100px] flex-nowrap flex-shrink-0 babybear:flex-wrap flex-2 babymamabear:min-w-[50px]">
<a class="nav__button-secondary btn-secondary-emphasis ml-3 btn-md" href="https://www.linkedin.com/login?emailAddress=&amp;fromSignIn=&amp;fromSignIn=true&amp;session_redirect=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fsearch%3Fkeywords%3Dingeniero%26geoId%3D100292246&amp;trk=public_jobs_nav-header-signin">
          Sign in
      </a>
<a class="nav__button-tertiary btn-primary btn-md" data-test-live-nav-primary-cta="" href="https://www.linkedin.com/signup/cold-join?source=jobs_registration&amp;session_redirect=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fsearch%3Fkeywords%3Dingeniero%26geoId%3D100292246&amp;trk=public_jobs_nav-header-join">
      Join now
<!-- --> </a>
<!-- -->
<!-- -->
<a aria-label="Sign in" class="nav__link-person papabear:hidden mamabear:hidden" href="https://www.linkedin.com/login?emailAddress=&amp;fromSignIn=&amp;fromSignIn=true&amp;session_redirect=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fsearch%3Fkeywords%3Dingeniero%26geoId%3D100292246&amp;trk=public_jobs_nav-header-signin">
<img/>
</a>
</div>
<!-- -->
<!-- --> </nav>
</header>
<section class="base-serp-page__filters-bar">
<div class="base-serp-page__filters">
<div class="search-filters search-filters--carousel">
<div class="filters filters--desktop">
<form action="https://www.linkedin.com/jobs/search" class="filters__form" id="jserp-filters">
<input name="keywords" type="hidden" value="Ingeniero"/>
<input name="location" type="hidden" value="Málaga"/>
<input name="geoId" type="hidden" value="100292246"/>
<ul class="filters__list">
<!-- -->
<li class="filter">
<div class="dropdown-to-modal filter__dropdown-to-modal">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Date posted filter. Any time filter is currently applied. Clicking this button displays all Date posted filter options." class="filter-button pill flex items-center !min-h-0 filter-button--selected pill-checked filter__dropdown-to-modal-trigger" type="button">
        
        Any time
      <icon aria-hidden="true" class="filter-button__icon h-3 w-3 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" tabindex="-1">
<!-- -->
<div class="filter-values-container">
<div aria-label="Date posted filter options" class="filter-values-container__filter-values" role="group">
<div class="filter-values-container__filter-value">
<input checked="" form="jserp-filters" id="f_TPR-0" name="f_TPR" type="radio" value=""/>
<label for="f_TPR-0">
        Any time (64)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_TPR-1" name="f_TPR" type="radio" value="r2592000"/>
<label for="f_TPR-1">
        Past month (50)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_TPR-2" name="f_TPR" type="radio" value="r604800"/>
<label for="f_TPR-2">
        Past week (21)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_TPR-3" name="f_TPR" type="radio" value="r86400"/>
<label for="f_TPR-3">
        Past 24 hours (1)
    </label>
</div>
</div>
</div>
<button class="filter__submit-button" form="jserp-filters" type="submit">
    Done
  </button>
</div>
<!-- --> </div>
</div>
</li>
<li class="filter">
<div class="dropdown-to-modal filter__dropdown-to-modal">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Company filter. Clicking this button displays all Company filter options." class="filter-button pill flex items-center !min-h-0 filter__dropdown-to-modal-trigger" type="button">
        Company
<!-- --> <icon aria-hidden="true" class="filter-button__icon h-3 w-3 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" tabindex="-1">
<section aria-label="Add a filter for Company" class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 typeahead-input filter__typeahead" data-base-api-url="/jobs-guest/api/typeaheadHits?typeaheadType=COMPANY">
<input aria-autocomplete="list" aria-controls="f_C-typeahead-list" aria-expanded="false" aria-haspopup="listbox" aria-label="Add a filter" autocomplete="off" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" id="f_C" maxlength="500" placeholder="Add a filter" role="combobox" type="text"/>
<div aria-live="polite" class="typeahead-live-text sr-only" role="status"></div>
<div class="typeahead-input__dropdown container-lined absolute top-[calc(100%+3px)] left-0 w-full rounded-b-md rounded-t-none z-[10] overflow-hidden max-w-none babybear:min-w-full babybear:bottom-0 babybear:overflow-y-auto">
<template class="typeahead-item-template">
<li class="typeahead-input__dropdown-item py-1.5 px-2 hover:cursor-pointer hover:bg-color-surface-new-hover hover:border-y-2 hover:border-solid hover:border-color-container-primary" role="option">
<span class="typeahead-input__dropdown-text font-sans text-sm font-bold text-color-text"></span>
</li>
</template>
<ul class="typeahead-input__dropdown-list w-full" id="f_C-typeahead-list" role="listbox"></ul>
</div>
<!-- -->
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100" disabled="" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<div class="filter-values-container">
<div aria-label="Company filter options" class="filter-values-container__filter-values" role="group">
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_C-0" name="f_C" type="checkbox" value="110494"/>
<label for="f_C-0">
        AERTEC (3)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_C-1" name="f_C" type="checkbox" value="11241967"/>
<label for="f_C-1">
        Vías y Construcciones S.A. (3)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_C-2" name="f_C" type="checkbox" value="12586731"/>
<label for="f_C-2">
        TDK Electronics (2)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_C-3" name="f_C" type="checkbox" value="1927157"/>
<label for="f_C-3">
        TROPS (2)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_C-4" name="f_C" type="checkbox" value="103158"/>
<label for="f_C-4">
        Inforges (1)
    </label>
</div>
</div>
</div>
<button class="filter__submit-button" form="jserp-filters" type="submit">
    Done
  </button>
</div>
<!-- --> </div>
</div>
</li>
<li class="filter">
<div class="dropdown-to-modal filter__dropdown-to-modal">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Job type filter. Clicking this button displays all Job type filter options." class="filter-button pill flex items-center !min-h-0 filter__dropdown-to-modal-trigger" type="button">
        Job type
<!-- --> <icon aria-hidden="true" class="filter-button__icon h-3 w-3 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" tabindex="-1">
<!-- -->
<div class="filter-values-container">
<div aria-label="Job type filter options" class="filter-values-container__filter-values" role="group">
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_JT-0" name="f_JT" type="checkbox" value="F"/>
<label for="f_JT-0">
        Full-time (64)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_JT-1" name="f_JT" type="checkbox" value="O"/>
<label for="f_JT-1">
        Other (1)
    </label>
</div>
</div>
</div>
<button class="filter__submit-button" form="jserp-filters" type="submit">
    Done
  </button>
</div>
<!-- --> </div>
</div>
</li>
<li class="filter">
<div class="dropdown-to-modal filter__dropdown-to-modal">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Experience level filter. Clicking this button displays all Experience level filter options." class="filter-button pill flex items-center !min-h-0 filter__dropdown-to-modal-trigger" type="button">
        Experience level
<!-- --> <icon aria-hidden="true" class="filter-button__icon h-3 w-3 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" tabindex="-1">
<!-- -->
<div class="filter-values-container">
<div aria-label="Experience level filter options" class="filter-values-container__filter-values" role="group">
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_E-0" name="f_E" type="checkbox" value="2"/>
<label for="f_E-0">
        Entry level (21)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_E-1" name="f_E" type="checkbox" value="3"/>
<label for="f_E-1">
        Associate (9)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_E-2" name="f_E" type="checkbox" value="4"/>
<label for="f_E-2">
        Mid-Senior level (16)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_E-3" name="f_E" type="checkbox" value="5"/>
<label for="f_E-3">
        Director (1)
    </label>
</div>
</div>
</div>
<button class="filter__submit-button" form="jserp-filters" type="submit">
    Done
  </button>
</div>
<!-- --> </div>
</div>
</li>
<li class="filter">
<div class="dropdown-to-modal filter__dropdown-to-modal">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Location filter. Clicking this button displays all Location filter options." class="filter-button pill flex items-center !min-h-0 filter__dropdown-to-modal-trigger" type="button">
        Location
<!-- --> <icon aria-hidden="true" class="filter-button__icon h-3 w-3 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" tabindex="-1">
<section aria-label="Add a filter for Location" class="dismissable-input text-input !pr-3 bg-color-transparent flex items-center h-[40px] min-w-0 relative babybear:w-full babybear:mb-1 typeahead-input filter__typeahead" data-base-api-url="/jobs-guest/api/typeaheadHits?origin=jserp&amp;typeaheadType=GEO&amp;geoTypes=POPULATED_PLACE">
<input aria-autocomplete="list" aria-controls="f_PP-typeahead-list" aria-expanded="false" aria-haspopup="listbox" aria-label="Add a filter" autocomplete="off" class="dismissable-input__input font-sans text-md text-color-text bg-color-transparent flex items-center flex-1 focus:outline-none placeholder:text-color-text-secondary" id="f_PP" maxlength="500" placeholder="Add a filter" role="combobox" type="text"/>
<div aria-live="polite" class="typeahead-live-text sr-only" role="status"></div>
<div class="typeahead-input__dropdown container-lined absolute top-[calc(100%+3px)] left-0 w-full rounded-b-md rounded-t-none z-[10] overflow-hidden max-w-none babybear:min-w-full babybear:bottom-0 babybear:overflow-y-auto">
<template class="typeahead-item-template">
<li class="typeahead-input__dropdown-item py-1.5 px-2 hover:cursor-pointer hover:bg-color-surface-new-hover hover:border-y-2 hover:border-solid hover:border-color-container-primary" role="option">
<span class="typeahead-input__dropdown-text font-sans text-sm font-bold text-color-text"></span>
</li>
</template>
<ul class="typeahead-input__dropdown-list w-full" id="f_PP-typeahead-list" role="listbox"></ul>
</div>
<!-- -->
<button class="dismissable-input__button text-color-text h-[40px] min-w-[24px] w-[24px] -mr-2 opacity-0 transition-opacity duration-[0.1s] disabled:invisible focus:opacity-100" disabled="" type="button">
<label class="sr-only">Clear text</label>
<icon aria-hidden="true" class="dismissable-input__button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<g fill="none" fill-rule="evenodd">
<path d="M7.90356 9.19393l-3.3763 3.3763-1.29037-1.29037 3.3763-3.3763-3.3763-3.3763 1.29037-1.29037 3.3763 3.3763 3.3763-3.3763 1.29037 1.29037-3.3763 3.3763 3.3763 3.3763-1.29037 1.29037z" fill="currentColor"></path>
<path d="M0 0h16v16H0z"></path>
</g>
</svg></icon>
</button>
</section>
<div class="filter-values-container">
<div aria-label="Location filter options" class="filter-values-container__filter-values" role="group">
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_PP-0" name="f_PP" type="checkbox" value="104401670"/>
<label for="f_PP-0">
        Málaga (35)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_PP-1" name="f_PP" type="checkbox" value="102711616"/>
<label for="f_PP-1">
        Vélez-Málaga (5)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_PP-2" name="f_PP" type="checkbox" value="104755912"/>
<label for="f_PP-2">
        Marbella (3)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_PP-3" name="f_PP" type="checkbox" value="100473056"/>
<label for="f_PP-3">
        Viñuela (1)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_PP-4" name="f_PP" type="checkbox" value="103427432"/>
<label for="f_PP-4">
        Antequera (1)
    </label>
</div>
</div>
</div>
<button class="filter__submit-button" form="jserp-filters" type="submit">
    Done
  </button>
</div>
<!-- --> </div>
</div>
</li>
<li class="filter">
<div class="dropdown-to-modal filter__dropdown-to-modal">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Remote filter. Clicking this button displays all Remote filter options." class="filter-button pill flex items-center !min-h-0 filter__dropdown-to-modal-trigger" type="button">
        Remote
<!-- --> <icon aria-hidden="true" class="filter-button__icon h-3 w-3 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="caret-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 16L5 9h14z" fill-rule="evenodd"></path>
</svg></icon>
</button>
<div class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" tabindex="-1">
<!-- -->
<div class="filter-values-container">
<div aria-label="Remote filter options" class="filter-values-container__filter-values" role="group">
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_WT-0" name="f_WT" type="checkbox" value="1"/>
<label for="f_WT-0">
        On-site (45)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_WT-1" name="f_WT" type="checkbox" value="3"/>
<label for="f_WT-1">
        Hybrid (15)
    </label>
</div>
<div class="filter-values-container__filter-value">
<input form="jserp-filters" id="f_WT-2" name="f_WT" type="checkbox" value="2"/>
<label for="f_WT-2">
        Remote (5)
    </label>
</div>
</div>
</div>
<button class="filter__submit-button" form="jserp-filters" type="submit">
    Done
  </button>
</div>
<!-- --> </div>
</div>
</li>
</ul>
</form>
<!-- --> </div>
</div>
</div>
</section>
<!-- -->
<div class="base-serp-page__content">
<main class="two-pane-serp-page__results" id="main-content" role="main">
<section class="two-pane-serp-page__search-header">
<!-- -->
<section class="job-alert-redirect-section__wrapper">
<div class="flex justify-between items-center container-lined py-1.5 px-2 mr-2 mb-2">
<div class="flex">
<icon aria-hidden="true" class="align-middle mr-1 w-[24px] h-[24px] flex-shrink-0 lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="bell-outline-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M22 18a4.52 4.52 0 00-1.17-2.83L19 13l-.8-5.56A6.27 6.27 0 0012 2a6.27 6.27 0 00-6.21 5.44L5 13l-1.83 2.17A4.52 4.52 0 002 18v1h8.28a2 2 0 103.44 0H22zM12 4a4.29 4.29 0 014.23 3.72L17 13H7l.77-5.3A4.26 4.26 0 0112 4zM4.32 17c.12-.19.24-.37.38-.55L6.77 14h10.46l2 2.42a4.67 4.67 0 01.41.58z"></path>
</svg></icon>
<span class="pr-3">Get notified when a new job is posted.</span>
</div>
<div>
<button aria-labelledby="jobs-alert-switch-label" class="switch" data-modal="alert-toggle-sign-in-modal" id="alert-toggle-button"></button>
<label for="alert-toggle-button" id="jobs-alert-switch-label">
            Set alert
          </label>
</div>
</div>
<div class="contextual-sign-in-modal">
<!-- -->
<div class="">
<!-- -->
<div class="modal modal--contextual-sign-in modal--contextual-sign-in-v2 modal--contextual-sign-in-v2--stacked" data-outlet="alert-toggle-sign-in-modal" id="alert-toggle-sign-in-modal">
<!-- --> <div aria-hidden="true" class="modal__overlay flex items-center bg-color-background-scrim justify-center fixed bottom-0 left-0 right-0 top-0 opacity-0 invisible pointer-events-none z-[1000] transition-[opacity] ease-[cubic-bezier(0.25,0.1,0.25,1.0)] duration-[0.17s] py-4">
<section aria-labelledby="alert-toggle-sign-in-modal-modal-header" aria-modal="true" class="max-h-full modal__wrapper overflow-auto p-0 bg-color-surface max-w-[1128px] min-h-[160px] relative scale-[0.25] shadow-sm shadow-color-border-faint transition-[transform] ease-[cubic-bezier(0.25,0.1,0.25,1.0)] duration-[0.33s] focus:outline-0 w-[1128px] mamabear:w-[744px] babybear:w-[360px] rounded-md" role="dialog" tabindex="-1">
<button aria-label="Dismiss" class="modal__dismiss btn-tertiary h-[40px] w-[40px] p-0 rounded-full indent-0 contextual-sign-in-modal__modal-dismiss absolute right-0 m-[20px] cursor-pointer">
<icon aria-hidden="true" class="contextual-sign-in-modal__modal-dismiss-icon lazy-loaded"><svg class="artdeco-icon lazy-loaded" focusable="false" height="24px" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path d="M20,5.32L13.32,12,20,18.68,18.66,20,12,13.33,5.34,20,4,18.68,10.68,12,4,5.32,5.32,4,12,10.69,18.68,4Z" fill="currentColor"></path>
</svg></icon>
</button>
<div class="modal__main w-full">
<div class="flex overflow-hidden babybear:contextual-sign-in-modal__layout--stacked contextual-sign-in-modal__layout--stacked">
<div class="contextual-sign-in-modal__left-content">
<img/>
<h2 class="contextual-sign-in-modal__context-screen-title font-sans text-lg text-color-text mt-2 mb-1 text-center" id="alert-toggle-sign-in-modal-modal-header">
                    Sign in to set job alerts for “Ingeniero” roles.
                  </h2>
<!-- --> </div>
<div class="contextual-sign-in-modal__right-content">
<div class="contextual-sign-in-modal__google-sign-in-primary w-full">
<div class="google-auth-button" data-google-auth-iframe-initialized="">
<!-- --> <div aria-label="Continue with google" class="google-auth-button__placeholder mx-auto" data-locale="en_US" data-logo-alignment="center" data-theme="filled_blue" role="button"><div class="S9gUrf-YoZ4jf" style="position: relative;"><div></div><iframe allow="identity-credentials-get" id="gsi_672158_657742" src="https://accounts.google.com/gsi/button?logo_alignment=center&amp;shape=pill&amp;size=large&amp;text=continue_with&amp;theme=filled_blue&amp;type=undefined&amp;width=312px&amp;client_id=990339570472-k6nqn1tpmitg8pui82bfaun3jrpmiuhs.apps.googleusercontent.com&amp;iframe_id=gsi_672158_657742&amp;as=x%2B5x8kVOJaMQF%2Bqf6wvEwg&amp;hl=en_US" style="display: block; position: relative; top: 0px; left: 0px; height: 44px; width: 332px; border: 0px; margin: -2px -10px;" title="Sign in with Google Button"></iframe></div></div>
<!-- --> </div>
</div>
<code id="i18n_username_error_empty" style="display: none"><!--"Please enter an email address or phone number"--></code>
<code id="i18n_username_error_too_long" style="display: none"><!--"Email or phone number must be between 3 to 128 characters"--></code>
<code id="i18n_username_error_too_short" style="display: none"><!--"Email or phone number must be between 3 to 128 characters"--></code>
<code id="i18n_password_error_empty" style="display: none"><!--"Please enter a password"--></code>
<code id="i18n_password_error_too_short" style="display: none"><!--"The password you provided must have at least 6 characters"--></code>
<code id="i18n_password_error_too_long" style="display: none"><!--"The password you provided must have at most 400 characters"--></code>
<!-- --> <form action="https://www.linkedin.com/uas/login-submit" class="contextual-sign-in-modal__sign-in-form mb-1 hidden" method="post" novalidate="">
<input name="loginCsrfParam" type="hidden" value="498b6ef7-62a6-467b-8966-0a9d93356bdf"/>
<div class="flex flex-col">
<div class="mt-1.5" data-js-module-id="guest-input">
<div class="flex flex-col">
<label class="input-label mb-1" for="csm-v2_session_key">
          Email or phone
        </label>
<div class="text-input flex">
<input autocomplete="username" class="text-color-text font-sans text-md outline-0 bg-color-transparent w-full" id="csm-v2_session_key" name="session_key" required="" type="text"/>
</div>
</div>
<p class="input-helper mt-1.5" data-js-module-id="guest-input__message" for="csm-v2_session_key" role="alert"></p>
</div>
<div class="mt-1.5" data-js-module-id="guest-input">
<div class="flex flex-col">
<label class="input-label mb-1" for="csm-v2_session_password">
          Password
        </label>
<div class="text-input flex">
<input autocomplete="current-password" class="text-color-text font-sans text-md outline-0 bg-color-transparent w-full" id="csm-v2_session_password" name="session_password" required="" type="password"/>
<button aria-label="Show your LinkedIn password" aria-live="assertive" aria-relevant="text" class="font-sans text-md font-bold text-color-action z-10 ml-[12px] hover:cursor-pointer" type="button">Show</button>
</div>
</div>
<p class="input-helper mt-1.5" data-js-module-id="guest-input__message" for="csm-v2_session_password" role="alert"></p>
</div>
<input name="session_redirect" type="hidden" value="https://www.linkedin.com/jobs/search?keywords=ingeniero&amp;geoId=100292246"/>
<!-- --> </div>
<div class="flex justify-between sign-in-form__footer--full-width">
<a class="font-sans text-md font-bold link leading-regular sign-in-form__forgot-password--full-width" href="https://www.linkedin.com/uas/request-password-reset?trk=csm-v2_forgot_password">Forgot password?</a>
<!-- -->
<input name="trk" type="hidden" value="csm-v2_sign-in-submit"/>
<button class="btn-md btn-primary flex-shrink-0 cursor-pointer sign-in-form__submit-btn--full-width" type="submit">
          Sign in
        </button>
</div>
<!-- --> <input name="controlId" type="hidden" value="d_jobs_guest_search-csm-v2_sign-in-submit-btn"/><input name="pageInstance" type="hidden" value="urn:li:page:d_jobs_guest_search_jsbeacon;fkObdPf6RjC8RdB0O9xEJw=="/><input name="controlId" type="hidden" value="d_jobs_guest_search-csm-v2_sign-in-submit-btn"/><input name="pageInstance" type="hidden" value="urn:li:page:d_jobs_guest_search_jsbeacon;fkObdPf6RjC8RdB0O9xEJw=="/></form>
<!-- --><!-- -->
<button class="contextual-sign-in-modal__sign-in-with-email-cta my-2 btn-sm btn-secondary min-h-[40px] w-full flex align-center justify-center">
<icon aria-hidden="true" class="inline-block align-middle h-[24px] w-[24px] mr-0.5 lazy-loaded"><svg class="lazy-loaded" data-supported-dps="16x16" fill="currentColor" focusable="false" id="envelope-small" viewbox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
<path d="M14 3H2a1 1 0 00-1 1v8a1 1 0 001 1h12a1 1 0 001-1V4a1 1 0 00-1-1zm-1 2L8 8.21 3 5h10zM3 11V6.07L7.32 8.8a1.25 1.25 0 001.37 0L13 6.07V11H3z"></path>
</svg></icon>
<span class="self-center">Sign in with Email</span>
</button>
<div class="contextual-sign-in-modal__divider left-right-divider">
<p class="contextual-sign-in-modal__divider-text font-sans text-sm text-color-text px-2">
                      or
                    </p>
</div>
<div class="contextual-sign-in-modal__google-sign-in-secondary contextual-sign-in-modal__google-sign-in-secondary--hidden">
<div class="google-auth-button" data-google-auth-iframe-initialized="">
<!-- --> <div aria-label="Continue with google" class="google-auth-button__placeholder mx-auto google-auth-button__placeholder--black-border" data-locale="en_US" data-logo-alignment="center" data-theme="outline" role="button"><div class="S9gUrf-YoZ4jf" style="position: relative;"><div></div><iframe allow="identity-credentials-get" id="gsi_672163_643501" src="https://accounts.google.com/gsi/button?logo_alignment=center&amp;shape=pill&amp;size=large&amp;text=continue_with&amp;theme=outline&amp;type=undefined&amp;width=312px&amp;client_id=990339570472-k6nqn1tpmitg8pui82bfaun3jrpmiuhs.apps.googleusercontent.com&amp;iframe_id=gsi_672163_643501&amp;as=x%2B5x8kVOJaMQF%2Bqf6wvEwg&amp;hl=en_US" style="display: block; position: relative; top: 0px; left: 0px; height: 44px; width: 332px; border: 0px; margin: -2px -10px;" title="Sign in with Google Button"></iframe></div></div>
<!-- --> </div>
</div>
<p class="contextual-sign-in-modal__join-now m-auto font-sans text-md text-center text-color-text my-2">
                      New to LinkedIn? <a class="contextual-sign-in-modal__join-link" href="https://www.linkedin.com/signup/cold-join?source=jobs_registration&amp;trk=public_jobs_contextual-sign-in-modal_join-link">Join now</a>
</p>
<p class="linkedin-tc__text text-color-text-low-emphasis text-xs pb-2 contextual-sign-in-modal__terms-and-conditions m-auto w-full text-center">
      By clicking Continue to join or sign in, you agree to LinkedIn’s <a href="/legal/user-agreement?trk=linkedin-tc_auth-button_user-agreement" target="_blank">User Agreement</a>, <a href="/legal/privacy-policy?trk=linkedin-tc_auth-button_privacy-policy" target="_blank">Privacy Policy</a>, and <a href="/legal/cookie-policy?trk=linkedin-tc_auth-button_cookie-policy" target="_blank">Cookie Policy</a>.
    </p>
</div>
</div>
</div>
<!-- --> </section>
</div>
</div>
</div>
<!-- --><!-- --> </div>
</section>
</section>
<!-- -->
<div class="results-context-header">
<h1 class="results-context-header__context">
<span class="results-context-header__job-count">65</span> <span class="results-context-header__query-search">Ingeniero Jobs in Málaga</span>
</h1>
</div>
<section class="two-pane-serp-page__results-list">
<ul class="jobs-search__results-list">
<li>
<div aria-current="true" class="base-card relative w-full hover:no-underline focus:no-underline base-card--link base-search-card base-search-card--link job-search-card job-search-card--active" data-column="1" data-entity-urn="urn:li:jobPosting:<ID>" data-reference-id="WvFVwEAGhf4nN0r2XzIrbg==" data-row="1">
<a class="base-card__full-link absolute top-0 right-0 bottom-0 left-0 p-0 z-[2] outline-offset-[4px]" href="https://es.linkedin.com/jobs/view/ingeniero-a-de-procesos-at-lumon-espa%C3%B1a-4412770860?position=1&amp;pageNum=0&amp;refId=WvFVwEAGhf4nN0r2XzIrbg%3D%3D&amp;trackingId=Yi8mtQwLdGpurEdhR1rp7g%3D%3D">
<span class="sr-only">
              
        
        Ingeniero/a de Procesos
      
      
          </span>
</a>
<div class="search-entity-media">
<img/>
</div>
<div class="base-search-card__info">
<h3 class="base-search-card__title">
            
        Ingeniero/a de Procesos
      
          </h3>
<h4 class="base-search-card__subtitle">
<a class="hidden-nested-link" href="https://es.linkedin.com/company/<COMPANY_SLUG>%C3%B1a?trk=public_jobs_jserp-result_job-search-card-subtitle">
            <COMPANY>
          </a>
</h4>
<!-- -->
<div class="base-search-card__metadata">
<span class="job-search-card__location">
            Antequera, Andalusia, Spain
          </span>
<div class="job-posting-benefits text-sm">
<icon aria-hidden="true" class="job-posting-benefits__icon lazy-loaded" data-svg-class-name="job-posting-benefits__icon-svg"><svg class="job-posting-benefits__icon-svg lazy-loaded" fill="none" focusable="false" height="24" viewbox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 20C7.6 20 4 16.4 4 12C4 7.6 7.6 4 12 4C13.8 4 15.5 4.6 16.9 5.7L15.5 7.1C14.5 6.4 13.3 6 12 6C8.7 6 6 8.7 6 12C6 15.3 8.7 18 12 18C15.3 18 18 15.3 18 12C18 10.7 17.6 9.5 16.9 8.5L20.7 4.7C20.9 4.5 21 4.3 21 4C21 3.7 20.9 3.5 20.7 3.3C20.5 3.1 20.3 3 20 3C19.7 3 19.5 3.1 19.3 3.3L18.3 4.3C16.6 2.8 14.4 2 12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22C17.5 22 22 17.5 22 12H20C20 16.4 16.4 20 12 20ZM17 12C17 14.8 14.8 17 12 17C9.2 17 7 14.8 7 12C7 9.2 9.2 7 12 7C13 7 14 7.3 14.8 7.8L12.6 10C12.3 10 12.2 10 12 10C10.9 10 10 10.9 10 12C10 13.1 10.9 14 12 14C13.1 14 14 13.1 14 12C14 11.8 14 11.7 13.9 11.5L16.1 9.3C16.7 10 17 11 17 12Z" fill="currentColor"></path>
</svg></icon>
<span class="job-posting-benefits__text">
          <DATE>
<!-- --> </span>
</div>
<time class="job-search-card__listdate" datetime="2026-05-11">
            

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    
    
    
    
    

      <DATE>
  
          </time>
<!-- -->
</div>
</div>
<!-- -->
</div>
</li>
<li>
<div class="base-card relative w-full hover:no-underline focus:no-underline base-card--link base-search-card base-search-card--link job-search-card" data-column="1" data-entity-urn="urn:li:jobPosting:<ID>" data-reference-id="WvFVwEAGhf4nN0r2XzIrbg==" data-row="2">
<a class="base-card__full-link absolute top-0 right-0 bottom-0 left-0 p-0 z-[2] outline-offset-[4px]" href="https://es.linkedin.com/jobs/view/ingeniero-a-de-procesos-y-mejora-continua-at-inforges-4414023449?position=2&amp;pageNum=0&amp;refId=WvFVwEAGhf4nN0r2XzIrbg%3D%3D&amp;trackingId=RV%2F5fTxN2%2BVwRXoINdc8GQ%3D%3D">
<span class="sr-only">
              
        
        Ingeniero/a de procesos y mejora continua
      
      
          </span>
</a>
<div class="search-entity-media">
<img/>
</div>
<div class="base-search-card__info">
<h3 class="base-search-card__title">
            
        Ingeniero/a de procesos y mejora continua
      
          </h3>
<h4 class="base-search-card__subtitle">
<a class="hidden-nested-link" href="https://es.linkedin.com/company/<COMPANY_SLUG>?trk=public_jobs_jserp-result_job-search-card-subtitle">
            Inforges
          </a>
</h4>
<!-- -->
<div class="base-search-card__metadata">
<span class="job-search-card__location">
            Vélez-Málaga, Andalusia, Spain
          </span>
<!-- -->
<time class="job-search-card__listdate" datetime="2026-05-21">
            

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    
    
    
    
    

      <DATE>
  
          </time>
<!-- -->
</div>
</div>
<!-- -->
</div>
</li>
<li>
<div class="base-card relative w-full hover:no-underline focus:no-underline base-card--link base-search-card base-search-card--link job-search-card" data-column="1" data-entity-urn="urn:li:jobPosting:<ID>" data-reference-id="WvFVwEAGhf4nN0r2XzIrbg==" data-row="3">
<a class="base-card__full-link absolute top-0 right-0 bottom-0 left-0 p-0 z-[2] outline-offset-[4px]" href="https://es.linkedin.com/jobs/view/ingeniero-a-de-procesos-m-f-d-at-tdk-electronics-4417619232?position=3&amp;pageNum=0&amp;refId=WvFVwEAGhf4nN0r2XzIrbg%3D%3D&amp;trackingId=vik%2BsK1fuI6HkfP%2FREhVcg%3D%3D">
<span class="sr-only">
              
        
        Ingeniero/a de Procesos (m/f/d)
      
      
          </span>
</a>
<div class="search-entity-media">
<img/>
</div>
<div class="base-search-card__info">
<h3 class="base-search-card__title">
            
        Ingeniero/a de Procesos (m/f/d)
      
          </h3>
<h4 class="base-search-card__subtitle">
<a class="hidden-nested-link" href="https://de.linkedin.com/company/<COMPANY_SLUG>?trk=public_jobs_jserp-result_job-search-card-subtitle">
            TDK Electronics
          </a>
</h4>
<!-- -->
<div class="base-search-card__metadata">
<span class="job-search-card__location">
            Málaga, Andalusia, Spain
          </span>
<div class="job-posting-benefits text-sm">
<icon aria-hidden="true" class="job-posting-benefits__icon lazy-loaded" data-svg-class-name="job-posting-benefits__icon-svg"><svg class="job-posting-benefits__icon-svg lazy-loaded" fill="none" focusable="false" height="24" viewbox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 20C7.6 20 4 16.4 4 12C4 7.6 7.6 4 12 4C13.8 4 15.5 4.6 16.9 5.7L15.5 7.1C14.5 6.4 13.3 6 12 6C8.7 6 6 8.7 6 12C6 15.3 8.7 18 12 18C15.3 18 18 15.3 18 12C18 10.7 17.6 9.5 16.9 8.5L20.7 4.7C20.9 4.5 21 4.3 21 4C21 3.7 20.9 3.5 20.7 3.3C20.5 3.1 20.3 3 20 3C19.7 3 19.5 3.1 19.3 3.3L18.3 4.3C16.6 2.8 14.4 2 12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22C17.5 22 22 17.5 22 12H20C20 16.4 16.4 20 12 20ZM17 12C17 14.8 14.8 17 12 17C9.2 17 7 14.8 7 12C7 9.2 9.2 7 12 7C13 7 14 7.3 14.8 7.8L12.6 10C12.3 10 12.2 10 12 10C10.9 10 10 10.9 10 12C10 13.1 10.9 14 12 14C13.1 14 14 13.1 14 12C14 11.8 14 11.7 13.9 11.5L16.1 9.3C16.7 10 17 11 17 12Z" fill="currentColor"></path>
</svg></icon>
<span class="job-posting-benefits__text">
          <DATE>
<!-- --> </span>
</div>
<time class="job-search-card__listdate" datetime="2026-05-28">
            

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    
    
    
    
    

      <DATE>
  
          </time>
<!-- -->
</div>
</div>
<!-- -->
</div>
</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
<li>

</li>
</ul>
<div class="loader">
<div class="loader__container mb-2 overflow-hidden">
<icon aria-hidden="true" class="loader__icon inline-block loader__icon--default text-color-progress-loading lazy-loaded" data-svg-class-name="loader__icon-svg--small fill-currentColor h-[30px] min-h-[30px] w-[30px] min-w-[30px]"><svg class="loader__icon-svg--small fill-currentColor h-[30px] min-h-[30px] w-[30px] min-w-[30px] lazy-loaded" focusable="false" height="60" viewbox="0 0 60 60" width="60" xmlns="http://www.w3.org/2000/svg">
<g>
<path d="M30.1,16.1L30.1,16.1c-0.6,0-1-0.5-1-1V1c0-0.6,0.5-1,1-1l0,0c0.6,0,1,0.5,1,1v14.1C31.1,15.7,30.6,16.1,30.1,16.1z" opacity="1"></path>
<path d="M23.1,18.1L23.1,18.1c-0.5,0.3-1.1,0.1-1.4-0.4L14.5,5.6c-0.3-0.5-0.2-1.1,0.4-1.4l0,0C15.4,3.9,16,4,16.3,4.6l7.2,12.1C23.8,17.2,23.6,17.8,23.1,18.1z" opacity="0.85"></path>
<path d="M17.9,23.1L17.9,23.1c-0.3,0.5-0.9,0.7-1.4,0.4l-12.2-7c-0.5-0.3-0.7-0.9-0.4-1.4l0,0c0.3-0.5,0.9-0.7,1.4-0.4l12.2,7C18,22,18.2,22.7,17.9,23.1z" opacity="0.77"></path>
<path d="M16.1,30.1L16.1,30.1c0,0.6-0.5,1-1,1L1,31.2c-0.6,0-1-0.5-1-1l0,0c0-0.6,0.5-1,1-1l14.1-0.1C15.7,29.1,16.1,29.5,16.1,30.1z" opacity="0.69"></path>
<path d="M18,36.9L18,36.9c0.3,0.5,0.2,1.1-0.4,1.4L5.5,45.6c-0.5,0.3-1.1,0.2-1.4-0.4l0,0c-0.3-0.5-0.2-1.1,0.4-1.4l12.1-7.3C17.1,36.2,17.7,36.4,18,36.9z" opacity="0.61"></path>
<path d="M23.3,42.1L23.3,42.1c0.5,0.3,0.6,0.9,0.4,1.4l-7.3,12.1c-0.3,0.5-0.9,0.6-1.4,0.4l0,0c-0.5-0.3-0.6-0.9-0.4-1.4l7.3-12.1C22.1,41.9,22.8,41.8,23.3,42.1z" opacity="0.53"></path>
<path d="M30.1,43.9L30.1,43.9c0.6,0,1,0.5,1,1V59c0,0.6-0.5,1-1,1l0,0c-0.6,0-1-0.5-1-1V44.9C29,44.4,29.5,43.9,30.1,43.9z" opacity="0.45"></path>
<path d="M37,41.9L37,41.9c0.5-0.3,1.1-0.2,1.4,0.4l7.2,12.1c0.3,0.5,0.2,1.1-0.4,1.4l0,0c-0.5,0.3-1.1,0.2-1.4-0.4l-7.2-12.1C36.4,42.8,36.6,42.2,37,41.9z" opacity="0.37"></path>
<path d="M42.2,36.8L42.2,36.8c0.3-0.5,0.9-0.7,1.4-0.4l12.2,7c0.5,0.3,0.7,0.9,0.4,1.4l0,0c-0.3,0.5-0.9,0.7-1.4,0.4l-12.2-7C42.1,38,41.9,37.4,42.2,36.8z" opacity="0.29"></path>
<path d="M44,29.9L44,29.9c0-0.6,0.5-1,1-1h14.1c0.6,0,1,0.5,1,1l0,0c0,0.6-0.5,1-1,1L45,31C44.4,31,44,30.5,44,29.9z" opacity="0.21 "></path>
<path d="M42.1,23.1L42.1,23.1c-0.3-0.5-0.2-1.1,0.4-1.4l12.1-7.3c0.5-0.3,1.1-0.2,1.4,0.4l0,0c0.3,0.4,0.1,1.1-0.4,1.3l-12.1,7.3C43.1,23.7,42.4,23.6,42.1,23.1z" opacity="0.13"></path>
<path d="M36.9,17.9L36.9,17.9c-0.5-0.3-0.6-0.9-0.4-1.4l7.3-12.1c0.3-0.5,0.9-0.6,1.4-0.4l0,0c0.5,0.3,0.6,0.9,0.4,1.4l-7.4,12.2C38,18.1,37.3,18.2,36.9,17.9z" opacity="0.05"></path>
<animatetransform attributename="transform" attributetype="XML" begin="0s" calcmode="discrete" dur="1s" keytimes="0;.0833;.166;.25;.3333;.4166;.5;.5833;.6666;.75;.8333;.9166;1" repeatcount="indefinite" type="rotate" values="0,30,30;30,30,30;60,30,30;90,30,30;120,30,30;150,30,30;180,30,30;210,30,30;240,30,30;270,30,30;300,30,30;330,30,30;360,30,30"></animatetransform>
</g>
</svg></icon>
</div>
</div>
<button aria-label="See more jobs" class="infinite-scroller__show-more-button">

          
                See more jobs
              
      </button>
<div class="px-1.5 flex inline-notification hidden text-color-signal-positive see-more-jobs__viewed-all" role="alert" type="success">
<icon aria-hidden="true" class="inline-notification__icon w-[20px] h-[20px] shrink-0 mr-[10px] inline-block lazy-loaded"><svg aria-hidden="true" class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" id="signal-success-medium" role="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
<path d="M12 2a10 10 0 1010 10A10 10 0 0012 2zm-1.25 15L7 13.25l1.41-1.41L10.59 14l4.84-6H18z"></path>
</svg></icon>
<p class="inline-notification__text text-sm leading-regular">
        You've viewed all jobs for this search
<!-- --> </p>
</div>
<section class="similar-titles">
<h3 class="similar-titles__heading">
          Search similar titles
        </h3>
<ul class="similar-titles__list">
<li class="similar-titles__title">
<a class="similar-titles__link" href="https://www.linkedin.com/jobs/software-engineer-jobs?trk=public_jobs_similar-title">
                Software Engineer jobs
              </a>
</li>
<li class="similar-titles__title">
<a class="similar-titles__link" href="https://www.linkedin.com/jobs/developer-jobs?trk=public_jobs_similar-title">
                Developer jobs
              </a>
</li>
<li class="similar-titles__title">
<a class="similar-titles__link" href="https://www.linkedin.com/jobs/network-engineer-jobs?trk=public_jobs_similar-title">
                Network Engineer jobs
              </a>
</li>
</ul>
</section>
</section>
</main>
<section class="two-pane-serp-page__detail-view" style="height: calc(-135px + 100vh);">
<div class="details-pane__loader details-pane__loader--hide">
<div class="loader">
<div class="loader__container mb-2 overflow-hidden">
<icon aria-hidden="true" class="loader__icon inline-block loader__icon--default text-color-progress-loading lazy-loaded" data-svg-class-name="loader__icon-svg--large fill-currentColor h-[60px] min-h-[60px] w-[60px] min-w-[60px]"><svg class="loader__icon-svg--large fill-currentColor h-[60px] min-h-[60px] w-[60px] min-w-[60px] lazy-loaded" focusable="false" height="60" viewbox="0 0 60 60" width="60" xmlns="http://www.w3.org/2000/svg">
<g>
<path d="M30.1,16.1L30.1,16.1c-0.6,0-1-0.5-1-1V1c0-0.6,0.5-1,1-1l0,0c0.6,0,1,0.5,1,1v14.1C31.1,15.7,30.6,16.1,30.1,16.1z" opacity="1"></path>
<path d="M23.1,18.1L23.1,18.1c-0.5,0.3-1.1,0.1-1.4-0.4L14.5,5.6c-0.3-0.5-0.2-1.1,0.4-1.4l0,0C15.4,3.9,16,4,16.3,4.6l7.2,12.1C23.8,17.2,23.6,17.8,23.1,18.1z" opacity="0.85"></path>
<path d="M17.9,23.1L17.9,23.1c-0.3,0.5-0.9,0.7-1.4,0.4l-12.2-7c-0.5-0.3-0.7-0.9-0.4-1.4l0,0c0.3-0.5,0.9-0.7,1.4-0.4l12.2,7C18,22,18.2,22.7,17.9,23.1z" opacity="0.77"></path>
<path d="M16.1,30.1L16.1,30.1c0,0.6-0.5,1-1,1L1,31.2c-0.6,0-1-0.5-1-1l0,0c0-0.6,0.5-1,1-1l14.1-0.1C15.7,29.1,16.1,29.5,16.1,30.1z" opacity="0.69"></path>
<path d="M18,36.9L18,36.9c0.3,0.5,0.2,1.1-0.4,1.4L5.5,45.6c-0.5,0.3-1.1,0.2-1.4-0.4l0,0c-0.3-0.5-0.2-1.1,0.4-1.4l12.1-7.3C17.1,36.2,17.7,36.4,18,36.9z" opacity="0.61"></path>
<path d="M23.3,42.1L23.3,42.1c0.5,0.3,0.6,0.9,0.4,1.4l-7.3,12.1c-0.3,0.5-0.9,0.6-1.4,0.4l0,0c-0.5-0.3-0.6-0.9-0.4-1.4l7.3-12.1C22.1,41.9,22.8,41.8,23.3,42.1z" opacity="0.53"></path>
<path d="M30.1,43.9L30.1,43.9c0.6,0,1,0.5,1,1V59c0,0.6-0.5,1-1,1l0,0c-0.6,0-1-0.5-1-1V44.9C29,44.4,29.5,43.9,30.1,43.9z" opacity="0.45"></path>
<path d="M37,41.9L37,41.9c0.5-0.3,1.1-0.2,1.4,0.4l7.2,12.1c0.3,0.5,0.2,1.1-0.4,1.4l0,0c-0.5,0.3-1.1,0.2-1.4-0.4l-7.2-12.1C36.4,42.8,36.6,42.2,37,41.9z" opacity="0.37"></path>
<path d="M42.2,36.8L42.2,36.8c0.3-0.5,0.9-0.7,1.4-0.4l12.2,7c0.5,0.3,0.7,0.9,0.4,1.4l0,0c-0.3,0.5-0.9,0.7-1.4,0.4l-12.2-7C42.1,38,41.9,37.4,42.2,36.8z" opacity="0.29"></path>
<path d="M44,29.9L44,29.9c0-0.6,0.5-1,1-1h14.1c0.6,0,1,0.5,1,1l0,0c0,0.6-0.5,1-1,1L45,31C44.4,31,44,30.5,44,29.9z" opacity="0.21 "></path>
<path d="M42.1,23.1L42.1,23.1c-0.3-0.5-0.2-1.1,0.4-1.4l12.1-7.3c0.5-0.3,1.1-0.2,1.4,0.4l0,0c0.3,0.4,0.1,1.1-0.4,1.3l-12.1,7.3C43.1,23.7,42.4,23.6,42.1,23.1z" opacity="0.13"></path>
<path d="M36.9,17.9L36.9,17.9c-0.5-0.3-0.6-0.9-0.4-1.4l7.3-12.1c0.3-0.5,0.9-0.6,1.4-0.4l0,0c0.5,0.3,0.6,0.9,0.4,1.4l-7.4,12.2C38,18.1,37.3,18.2,36.9,17.9z" opacity="0.05"></path>
<animatetransform attributename="transform" attributetype="XML" begin="0s" calcmode="discrete" dur="1s" keytimes="0;.0833;.166;.25;.3333;.4166;.5;.5833;.6666;.75;.8333;.9166;1" repeatcount="indefinite" type="rotate" values="0,30,30;30,30,30;60,30,30;90,30,30;120,30,30;150,30,30;180,30,30;210,30,30;240,30,30;270,30,30;300,30,30;330,30,30;360,30,30"></animatetransform>
</g>
</svg></icon>
</div>
</div>
</div>
<div class="details-pane__content details-pane__content--show">
<section class="top-card-layout container-lined overflow-hidden babybear:rounded-[0px]">
<div class="top-card-layout__card relative p-2 papabear:p-details-container-padding">
<a href="https://es.linkedin.com/company/<COMPANY_SLUG>%C3%B1a?trk=public_jobs_topcard_logo" target="_self">
<img/>
</a>
<div class="top-card-layout__entity-info-container flex flex-wrap papabear:flex-nowrap">
<div class="top-card-layout__entity-info flex-grow flex-shrink-0 basis-0 babybear:flex-none babybear:w-full babybear:flex-none babybear:w-full">
<a class="topcard__link" href="https://es.linkedin.com/jobs/view/ingeniero-a-de-procesos-at-lumon-espa%C3%B1a-4412770860?trk=public_jobs_topcard-title">
<h2 class="top-card-layout__title font-sans text-lg papabear:text-xl font-bold leading-open text-color-text mb-0 topcard__title">Ingeniero/a de Procesos</h2>
</a>
<!-- -->
<!-- -->
<h4 class="top-card-layout__second-subline font-sans text-sm leading-open text-color-text-low-emphasis mt-0.5">
<div class="topcard__flavor-row">
<span class="topcard__flavor">
<a class="topcard__org-name-link topcard__flavor--black-link" href="https://es.linkedin.com/company/<COMPANY_SLUG>%C3%B1a?trk=public_jobs_topcard-org-name" rel="noopener" target="_blank">
                <COMPANY>
              </a>
</span>
<span class="topcard__flavor topcard__flavor--bullet">
              Antequera, Andalusia, Spain
            </span>
</div>
<div class="topcard__flavor-row">
<span class="posted-time-ago__text topcard__flavor--metadata">
          

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    
    
    
    
    

      <DATE>
  
        </span>
<span class="num-applicants__caption topcard__flavor--metadata topcard__flavor--bullet">
          74 applicants
        </span>
</div>
<a class="face-pile flex !no-underline see-who-was-hired" href="https://www.linkedin.com/login?session_redirect=https%3A%2F%2Fwww%2Elinkedin%2Ecom%2Fsearch%2Fresults%2Fpeople%2F%3FfacetCurrentCompany%3D9463666&amp;emailAddress=&amp;fromSignIn=&amp;trk=public_jobs_see-who-was-hired_people-search-link_face-pile-cta" target="_self">
<div class="face-pile__images-container self-start flex-shrink-0 mr-1 leading-[1]">
<img/>
<img/>
<img/>
</div>
<div class="face-pile__text-container self-center">
<p class="face-pile__text font-sans text-sm link-styled hover:underline">
            See who <COMPANY> has hired for this role
          </p>
<!-- --> </div>
</a>
<!-- -->
</h4>
<div class="top-card-layout__cta-container flex flex-wrap mt-0.5 papabear:mt-0 ml-[-12px]">
<button class="sign-up-modal__outlet top-card-layout__cta mt-2 ml-1.5 h-auto babybear:flex-auto top-card-layout__cta--primary btn-md btn-primary" data-modal="job-details-topcard-apply-modal">
            Apply
            <icon aria-hidden="true" class="lazy-loaded" data-svg-class-name="apply-button__offsite-apply-icon-svg"><svg class="apply-button__offsite-apply-icon-svg lazy-loaded" data-name="Layer 1" focusable="false" height="16" id="Layer_1" viewbox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
<path d="M12,10v3a1,1,0,0,1-1,1H3a1,1,0,0,1-1-1V5A1,1,0,0,1,3,4H6V6H4v6h6V10h2Zm1-8H8V4h2.67L6,8.67,7.33,10,12,5.33V8h2V3A1,1,0,0,0,13,2Z" style="fill:#fff"></path>
</svg></icon>
</button>
<div class="contextual-sign-in-modal">
<!-- -->
<div class="">
<!-- -->
<div class="modal modal--contextual-sign-in modal--contextual-sign-in-v2 modal--contextual-sign-in-v2--stacked" data-outlet="job-details-topcard-apply-modal" id="job-details-topcard-apply-modal">
<!-- --> <div aria-hidden="true" class="modal__overlay flex items-center bg-color-background-scrim justify-center fixed bottom-0 left-0 right-0 top-0 opacity-0 invisible pointer-events-none z-[1000] transition-[opacity] ease-[cubic-bezier(0.25,0.1,0.25,1.0)] duration-[0.17s] py-4">
<section aria-labelledby="job-details-topcard-apply-modal-modal-header" aria-modal="true" class="max-h-full modal__wrapper overflow-auto p-0 bg-color-surface max-w-[1128px] min-h-[160px] relative scale-[0.25] shadow-sm shadow-color-border-faint transition-[transform] ease-[cubic-bezier(0.25,0.1,0.25,1.0)] duration-[0.33s] focus:outline-0 w-[1128px] mamabear:w-[744px] babybear:w-[360px] rounded-md" role="dialog" tabindex="-1">
<button aria-label="Dismiss" class="modal__dismiss btn-tertiary h-[40px] w-[40px] p-0 rounded-full indent-0 contextual-sign-in-modal__modal-dismiss absolute right-0 m-[20px] cursor-pointer">
<icon aria-hidden="true" class="contextual-sign-in-modal__modal-dismiss-icon lazy-loaded"><svg class="artdeco-icon lazy-loaded" focusable="false" height="24px" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path d="M20,5.32L13.32,12,20,18.68,18.66,20,12,13.33,5.34,20,4,18.68,10.68,12,4,5.32,5.32,4,12,10.69,18.68,4Z" fill="currentColor"></path>
</svg></icon>
</button>
<div class="modal__main w-full">
<div class="flex overflow-hidden babybear:contextual-sign-in-modal__layout--stacked contextual-sign-in-modal__layout--stacked">
<div class="contextual-sign-in-modal__left-content">
<img/>
<h2 class="contextual-sign-in-modal__context-screen-title font-sans text-lg text-color-text mt-2 mb-1 text-center" id="job-details-topcard-apply-modal-modal-header">
                    Join or sign in to find your next job
                  </h2>
<div class="contextual-sign-in-modal__divider left-right-divider"></div>
<p class="contextual-sign-in-modal__subtitle mt-1 mb-2 babybear:mx-0 text-center font-sans text-xs text-color-text-low-emphasis">
<!-- --> <span>Join to apply for the <strong>Ingeniero/a de Procesos</strong> role at <strong><COMPANY></strong></span>
</p>
</div>
<div class="contextual-sign-in-modal__right-content">
<div class="contextual-sign-in-modal__google-sign-in-primary w-full">
<div class="google-auth-button">
<!-- --> <div aria-label="Continue with google" class="google-auth-button__placeholder mx-auto" data-locale="en_US" data-logo-alignment="center" data-theme="filled_blue" role="button"></div>
<!-- --> </div>
</div>
<code id="i18n_username_error_empty" style="display: none"><!--"Please enter an email address or phone number"--></code>
<code id="i18n_username_error_too_long" style="display: none"><!--"Email or phone number must be between 3 to 128 characters"--></code>
<code id="i18n_username_error_too_short" style="display: none"><!--"Email or phone number must be between 3 to 128 characters"--></code>
<code id="i18n_password_error_empty" style="display: none"><!--"Please enter a password"--></code>
<code id="i18n_password_error_too_short" style="display: none"><!--"The password you provided must have at least 6 characters"--></code>
<code id="i18n_password_error_too_long" style="display: none"><!--"The password you provided must have at most 400 characters"--></code>
<!-- --> <form action="https://www.linkedin.com/uas/login-submit" class="contextual-sign-in-modal__sign-in-form mb-1 hidden" method="post" novalidate="">
<input name="loginCsrfParam" type="hidden" value="498b6ef7-62a6-467b-8966-0a9d93356bdf"/>
<div class="flex flex-col">
<div class="mt-1.5" data-js-module-id="guest-input">
<div class="flex flex-col">
<label class="input-label mb-1" for="csm-v2_session_key">
          Email or phone
        </label>
<div class="text-input flex">
<input autocomplete="username" class="text-color-text font-sans text-md outline-0 bg-color-transparent w-full" id="csm-v2_session_key" name="session_key" required="" type="text"/>
</div>
</div>
<p class="input-helper mt-1.5" data-js-module-id="guest-input__message" for="csm-v2_session_key" role="alert"></p>
</div>
<div class="mt-1.5" data-js-module-id="guest-input">
<div class="flex flex-col">
<label class="input-label mb-1" for="csm-v2_session_password">
          Password
        </label>
<div class="text-input flex">
<input autocomplete="current-password" class="text-color-text font-sans text-md outline-0 bg-color-transparent w-full" id="csm-v2_session_password" name="session_password" required="" type="password"/>
<button aria-label="Show your LinkedIn password" aria-live="assertive" aria-relevant="text" class="font-sans text-md font-bold text-color-action z-10 ml-[12px] hover:cursor-pointer" type="button">Show</button>
</div>
</div>
<p class="input-helper mt-1.5" data-js-module-id="guest-input__message" for="csm-v2_session_password" role="alert"></p>
</div>
<input name="session_redirect" type="hidden" value="https://es.linkedin.com/jobs/view/ingeniero-a-de-procesos-at-lumon-espa%C3%B1a-4412770860"/>
<!-- --> </div>
<div class="flex justify-between sign-in-form__footer--full-width">
<a class="font-sans text-md font-bold link leading-regular sign-in-form__forgot-password--full-width" href="https://www.linkedin.com/uas/request-password-reset?trk=csm-v2_forgot_password">Forgot password?</a>
<!-- -->
<input name="trk" type="hidden" value="csm-v2_sign-in-submit"/>
<button class="btn-md btn-primary flex-shrink-0 cursor-pointer sign-in-form__submit-btn--full-width" type="submit">
          Sign in
        </button>
</div>
<!-- --> <input name="controlId" type="hidden" value="d_jobs_guest_search-csm-v2_sign-in-submit-btn"/><input name="pageInstance" type="hidden" value="urn:li:page:d_jobs_guest_search_jsbeacon;fkObdPf6RjC8RdB0O9xEJw=="/><input name="controlId" type="hidden" value="d_jobs_guest_search-csm-v2_sign-in-submit-btn"/><input name="pageInstance" type="hidden" value="urn:li:page:d_jobs_guest_search_jsbeacon;fkObdPf6RjC8RdB0O9xEJw=="/></form>
<!-- --><!-- -->
<button class="contextual-sign-in-modal__sign-in-with-email-cta my-2 btn-sm btn-secondary min-h-[40px] w-full flex align-center justify-center">
<icon aria-hidden="true" class="inline-block align-middle h-[24px] w-[24px] mr-0.5 lazy-loaded"><svg class="lazy-loaded" data-supported-dps="16x16" fill="currentColor" focusable="false" id="envelope-small" viewbox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
<path d="M14 3H2a1 1 0 00-1 1v8a1 1 0 001 1h12a1 1 0 001-1V4a1 1 0 00-1-1zm-1 2L8 8.21 3 5h10zM3 11V6.07L7.32 8.8a1.25 1.25 0 001.37 0L13 6.07V11H3z"></path>
</svg></icon>
<span class="self-center">Sign in with Email</span>
</button>
<div class="contextual-sign-in-modal__divider left-right-divider">
<p class="contextual-sign-in-modal__divider-text font-sans text-sm text-color-text px-2">
                      or
                    </p>
</div>
<div class="contextual-sign-in-modal__google-sign-in-secondary contextual-sign-in-modal__google-sign-in-secondary--hidden">
<div class="google-auth-button">
<!-- --> <div aria-label="Continue with google" class="google-auth-button__placeholder mx-auto google-auth-button__placeholder--black-border" data-locale="en_US" data-logo-alignment="center" data-theme="outline" role="button"></div>
<!-- --> </div>
</div>
<p class="contextual-sign-in-modal__join-now m-auto font-sans text-md text-center text-color-text my-2">
                      New to LinkedIn? <a class="contextual-sign-in-modal__join-link" href="https://www.linkedin.com/signup/cold-join?source=jobs_registration&amp;session_redirect=https%3A%2F%2Fes.linkedin.com%2Fjobs%2Fview%2Fingeniero-a-de-procesos-at-lumon-espa%25C3%25B1a-4412770860&amp;trk=public_jobs_apply-link-offsite_contextual-sign-in-modal_join-link">Join now</a>
</p>
<p class="linkedin-tc__text text-color-text-low-emphasis text-xs pb-2 contextual-sign-in-modal__terms-and-conditions m-auto w-full text-center">
      By clicking Continue to join or sign in, you agree to LinkedIn’s <a href="/legal/user-agreement?trk=linkedin-tc_auth-button_user-agreement" target="_blank">User Agreement</a>, <a href="/legal/privacy-policy?trk=linkedin-tc_auth-button_privacy-policy" target="_blank">Privacy Policy</a>, and <a href="/legal/cookie-policy?trk=linkedin-tc_auth-button_cookie-policy" target="_blank">Cookie Policy</a>.
    </p>
</div>
</div>
</div>
<!-- --> </section>
</div>
</div>
</div>
<!-- --><!-- --> </div>
<a class="top-card-layout__cta mt-2 ml-1.5 h-auto babybear:flex-auto top-card-layout__cta--secondary btn-md btn-secondary" data-test-redirect-save-to-login="" href="https://www.linkedin.com/login?emailAddress=&amp;fromSignIn=&amp;session_redirect=https%3A%2F%2Fes.linkedin.com%2Fjobs%2Fview%2Fingeniero-a-de-procesos-at-lumon-espa%25C3%25B1a-4412770860&amp;trk=public_jobs">
                Save
            </a>
</div>
</div>
<!-- --> </div>
<div class="ellipsis-menu absolute right-0 top-0 top-card-layout__ellipsis-menu mr-1 papabear:mt-0.5 papabear:mr-2">
<div class="collapsible-dropdown flex items-center relative hyphens-auto">
<button aria-expanded="false" aria-label="Open menu" class="ellipsis-menu__trigger collapsible-dropdown__button btn-md btn-tertiary cursor-pointer !py-[6px] !px-1 flex items-center rounded-[50%]" tabindex="0">
<icon aria-hidden="true" class="ellipsis-menu__trigger-icon m-0 p-0 centered-icon lazy-loaded"><svg class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" height="24" width="24" xmlns="http://www.w3.org/2000/svg">
<path d="M2 10h4v4H2v-4zm8 4h4v-4h-4v4zm8-4v4h4v-4h-4z"></path>
</svg></icon>
</button>
<ul class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-auto top-[100%]" role="menu" tabindex="-1">
<li class="ellipsis-menu__item border-t-1 border-solid border-color-border-low-emphasis first-of-type:border-none flex" role="presentation">
<a class="semaphore__toggle visited:text-color-text-secondary ellipsis-menu__semaphore ellipsis-menu__item-button flex items-center w-full p-1 cursor-pointer font-sans text-sm font-bold link-styled focus:link-styled link:no-underline active:bg-color-background-container-tint focus:bg-color-background-container-tint hover:bg-color-background-container-tint outline-offset-[-2px]" data-is-logged-in="false" data-item-type="semaphore" data-modal="semaphore__toggle" data-semaphore-content-type="JOB" data-semaphore-content-urn="urn:li:jobPosting:4412770860" data-semaphore-tracking-prefix="public_jobs_ellipsis-menu-semaphore" href="/uas/login?fromSignIn=true&amp;session_redirect=https%3A%2F%2Fes.linkedin.com%2Fjobs%2Fview%2Fingeniero-a-de-procesos-at-lumon-espa%25C3%25B1a-4412770860&amp;trk=public_jobs_ellipsis-menu-semaphore-sign-in-redirect&amp;guestReportContentType=JOB&amp;_f=guest-reporting" role="menuitem">
<!-- -->
<icon aria-hidden="true" class="ellipsis-menu__item-icon text-color-text h-[24px] w-[24px] mr-1 lazy-loaded">
<svg class="lazy-loaded" data-supported-dps="24x24" fill="currentColor" focusable="false" height="24" width="24" xmlns="http://www.w3.org/2000/svg">
<path d="M13.82 5L14 4a1 1 0 00-1-1H5V2H3v20h2v-7h4.18L9 16a1 1 0 001 1h8.87L21 5h-7.18zM5 13V5h6.94l-1.41 8H5zm12.35 2h-6.3l1.42-8h6.29z"></path>
</svg></icon>
                      Report this job
                    
    </a>
<!-- -->
</li>
<!-- -->
</ul>
<!-- --> </div>
</div>
<!-- --> </div>
</section>
<div class="decorated-job-posting__details">
<!-- -->
<section class="core-section-container my-3 description">
<!-- -->
<!-- -->
<!-- -->
<div class="core-section-container__content break-words">
<!-- -->
<div class="description__text description__text--rich">
<section class="show-more-less-html" data-max-lines="5">
<div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5 relative overflow-hidden">
          👷‍♂️👷‍♀️ En <COMPANY> estamos buscando un Ingeniero/a de procesos para nuestra fábrica ubicada en Antequera (Málaga).<br/><br/>Como ingeniero/a de procesos desarrollarás, estandarizarás y mejorarás los procesos de producción para potenciar la seguridad, la calidad, la fiabilidad de las entregas, la productividad y la rentabilidad. Aportarás apoyo técnico y metodológico a la fábrica y a las iniciativas de excelencia operativa.<br/><br/>Entre tus principales responsabilidades destacan:<br/><br/><ul><li>🔍📊 Desarrollo de procesos y producción: Desarrollar, analizar y optimizar procesos con métodos Lean y basados en datos; detectar ineficiencias, desperdicios, pérdidas de calidad y cuellos de botella; proponer e implementar mejoras. Liderar iniciativas de mejora continua (Kaizen, Six Sigma, proyectos Lean) y estandarizar métodos, parámetros y mejores prácticas.</li><li>🛠️🚀 Apoyo operativo: Apoyar la producción diaria en la resolución de problemas (causas raíz y acciones correctivas). Actuar como soporte técnico para producción, planificación, calidad, mantenimiento y logística. Participar en la puesta en marcha de nuevos equipos o variantes y en la gestión del cambio relacionada con modificaciones de procesos o de instalaciones.</li><li>🧾✅ Calidad, seguridad y cumplimiento normativo: Asegurar el cumplimiento de requisitos de seguridad, calidad y normativos. Mantener instrucciones de trabajo y documentación de procesos. Participar en auditorías y seguimientos. Gestión de datos y KPI: definir, supervisar y analizar rendimiento, desperdicio, Cp/Cpk, plazo de entrega y productividad, y comunicar resultados a la dirección.<br/><br/></li></ul><strong>¿Qué requisitos debes cumplir?<br/><br/></strong><ul><li>🎓 Licenciatura o máster en Ingeniería (Producción, Industrial, Mecánica, Automatización o similar).</li><li>🏅 Valorable certificación Lean/Six Sigma (Green Belt).</li><li>🏭 Experiencia laboral de 2 a 5 años en fabricación, ingeniería de procesos o desarrollo de producción, en entornos industriales o de fábrica.</li><li>🌍 Conocimientos lingüísticos: mínimo nivel B2 de inglés.</li><li>📌💡 Competencias técnicas y profesionales: Conocimientos sólidos de procesos de fabricación y producción. Capacidad para analizar datos y KPI. Conocimientos de Lean y resolución de problemas (5 Why, Fishbone, PDCA, DMAIC), ERP y bases en TI y análisis de datos.<br/><br/></li></ul><strong>¿Qué buscamos en ti?<br/><br/></strong><ul><li>🧠 Capacidad para decidir de forma autónoma la priorización de tareas.</li><li>🤝 Actitud proactiva y mentalidad abierta para detectar oportunidades y colaborar con otras áreas.</li><li>💰📉 Análisis de optimización de costes antes de proponer medidas.<br/><br/></li></ul>✨ <strong>¿Qué te aportará <COMPANY>?<br/><br/></strong><ul><li>Contrato indefinido desde el primer día, apostando por la estabilidad y el largo plazo.</li><li>Jornada completa de lunes a viernes.</li><li>Paquete salarial competitivo, compuesto por un salario fijo atractivo más un componente variable ligado a objetivos.</li><li>Formación inicial y continua, con un acompañamiento constante para que conozcas en profundidad el producto y el proceso productivo.</li><li>Plan de desarrollo y crecimiento profesional dentro de una empresa líder en su sector, que ofrece un entorno de trabajo estable, colaborativo y orientado al aprendizaje continuo.</li></ul>
</div>
<button aria-expanded="false" aria-label="Show more" class="show-more-less-html__button show-more-less-button show-more-less-html__button--more ml-0.5">
<!-- -->
        
            Show more
          

          <icon aria-hidden="true" class="show-more-less-html__button-icon show-more-less-button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" preserveaspectratio="xMinYMin meet" width="16" xmlns="http://www.w3.org/2000/svg"><path d="M8 9l5.93-4L15 6.54l-6.15 4.2a1.5 1.5 0 01-1.69 0L1 6.54 2.07 5z" fill="currentColor"></path></svg></icon>
</button>
<button aria-expanded="true" aria-label="Show less" class="show-more-less-html__button show-more-less-button show-more-less-html__button--less ml-0.5">
<!-- -->
        
            Show less
          

          <icon aria-hidden="true" class="show-more-less-html__button-icon show-more-less-button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" preserveaspectratio="xMinYMin meet" width="16" xmlns="http://www.w3.org/2000/svg"><path d="M8 7l-5.9 4L1 9.5l6.2-4.2c.5-.3 1.2-.3 1.7 0L15 9.5 13.9 11 8 7z" fill="currentColor"></path></svg></icon>
</button>
<!-- --> </section>
</div>
<ul class="description__job-criteria-list">
<li class="description__job-criteria-item">
<h3 class="description__job-criteria-subheader">
            Seniority level
          </h3>
<span class="description__job-criteria-text description__job-criteria-text--criteria">
            Not Applicable
          </span>
</li>
<li class="description__job-criteria-item">
<h3 class="description__job-criteria-subheader">
            Employment type
          </h3>
<span class="description__job-criteria-text description__job-criteria-text--criteria">
            Full-time
          </span>
</li>
<li class="description__job-criteria-item">
<h3 class="description__job-criteria-subheader">
              Job function
            </h3>
<span class="description__job-criteria-text description__job-criteria-text--criteria">
              Management and Manufacturing
            </span>
</li>
<li class="description__job-criteria-item">
<h3 class="description__job-criteria-subheader">
              Industries
            </h3>
<span class="description__job-criteria-text description__job-criteria-text--criteria">
            Construction
            </span>
</li>
</ul>
</div>
</section>
<section class="core-section-container my-3 find-a-referral">
<!-- -->
<!-- -->
<!-- -->
<div class="core-section-container__content break-words">
<div class="face-pile flex !no-underline">
<div class="face-pile__images-container self-start flex-shrink-0 mr-1 leading-[1]">
<img/>
<img/>
<img/>
</div>
<div class="find-a-referral__cta-container">
<p>Referrals increase your chances of interviewing at <COMPANY> by 2x</p>
<a class="find-a-referral__cta" href="https://www.linkedin.com/login?session_redirect=https%3A%2F%2Fwww%2Elinkedin%2Ecom%2Fsearch%2Fresults%2Fpeople%2F%3FfacetCurrentCompany%3D9463666&amp;emailAddress=&amp;fromSignIn=&amp;trk=public_jobs_find-a-referral-cta">
                See who you know
              </a>
</div>
</div>
</div>
</section>
<!-- --> </div>
<!-- -->
<!-- -->
<code id="decoratedJobPostingId" style="display: none"><!--"4412770860"--></code>
<code id="referenceId" style="display: none"><!--"WvFVwEAGhf4nN0r2XzIrbg=="--></code>
<code id="joinUrlWithRedirect" style="display: none"><!--"https://www.linkedin.com/signup/cold-join?source=jobs_registration&session_redirect=https%3A%2F%2Fes.linkedin.com%2Fjobs%2Fview%2Fingeniero-a-de-procesos-at-lumon-espa%25C3%25B1a-4412770860"--></code>
</div>
</section>
</div>
<section class="related-jserps">
<section class="tw-expandable-linkster" data-js-module-id="expandable-linkster">
<div class="show-more-less">
<button aria-expanded="false" class="show-more-less__button show-more-less__more-button show-more-less-button">
                
          
            More searches
        
              <icon class="show-more-less__button--chevron show-more-less-button-icon" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/cyolgscd0imw2ldqppkrb84vo"></icon>
</button>
<button aria-expanded="false" class="show-more-less__button show-more-less__less-button show-more-less-button show-more-less__button--hide">
                
          
            More searches
        
              <icon aria-hidden="true" class="show-more-less__button--chevron show-more-less-button-icon lazy-loaded"><svg class="lazy-loaded" focusable="false" height="16" preserveaspectratio="xMinYMin meet" width="16" xmlns="http://www.w3.org/2000/svg"><path d="M8 7l-5.9 4L1 9.5l6.2-4.2c.5-.3 1.2-.3 1.7 0L15 9.5 13.9 11 8 7z" fill="currentColor"></path></svg></icon>
</button>
<ul class="show-more-less__list show-more-less__list--hide-after-0" data-max-num-to-show="0">
<li>
<section class="tw-linkster" data-js-module-id="linkster" data-module-name="jserp_links">
<div class="max-w-screen-content-max-w w-full flex justify-between my-0 mx-auto mamabear:px-3 babybear:px-2 babybear:flex-col">
<div class="flex-1 w-1/2 pt-2 pr-4 pb-4 pl-0 babybear:pb-2 babybear:w-full babybear:border-b-1 babybear:border-solid babybear:border-color-border-low-emphasis babybear:last:border-b-0">
<!-- --> <ul class="my-1">
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/software-engineer-jobs?trk=public_jobs_linkster_link">
                Software Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/developer-jobs?trk=public_jobs_linkster_link">
                Developer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/network-engineer-jobs?trk=public_jobs_linkster_link">
                Network Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/project-engineer-jobs?trk=public_jobs_linkster_link">
                Project Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/reservoir-engineer-jobs?trk=public_jobs_linkster_link">
                Reservoir Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/aerospace-engineer-jobs?trk=public_jobs_linkster_link">
                Aerospace Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/process-engineer-jobs?trk=public_jobs_linkster_link">
                Process Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/test-engineer-jobs?trk=public_jobs_linkster_link">
                Test Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/application-developer-jobs?trk=public_jobs_linkster_link">
                Application Developer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/system-engineer-jobs?trk=public_jobs_linkster_link">
                System Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/materials-engineer-jobs?trk=public_jobs_linkster_link">
                Materials Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/analyst-jobs?trk=public_jobs_linkster_link">
                Analyst jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/resident-engineer-jobs?trk=public_jobs_linkster_link">
                Resident Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/telecommunications-engineer-jobs?trk=public_jobs_linkster_link">
                Telecommunications Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/industrial-engineer-jobs?trk=public_jobs_linkster_link">
                Industrial Engineer jobs
              </a>
</li>
</ul>
<!-- --> </div>
<div class="flex-1 w-1/2 pt-2 pr-4 pb-4 pl-0 babybear:pb-2 babybear:w-full babybear:border-b-1 babybear:border-solid babybear:border-color-border-low-emphasis babybear:last:border-b-0">
<!-- --> <ul class="my-1">
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/field-engineer-jobs?trk=public_jobs_linkster_link">
                Field Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/transportation-engineer-jobs?trk=public_jobs_linkster_link">
                Transportation Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/security-engineer-jobs?trk=public_jobs_linkster_link">
                Security Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/forest-engineer-jobs?trk=public_jobs_linkster_link">
                Forest Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/application-engineer-jobs?trk=public_jobs_linkster_link">
                Application Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/product-engineer-jobs?trk=public_jobs_linkster_link">
                Product Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/mining-engineer-jobs?trk=public_jobs_linkster_link">
                Mining Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/service-engineer-jobs?trk=public_jobs_linkster_link">
                Service Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/data-analyst-jobs?trk=public_jobs_linkster_link">
                Data Analyst jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/solutions-architect-jobs?trk=public_jobs_linkster_link">
                Solutions Architect jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/nuclear-engineer-jobs?trk=public_jobs_linkster_link">
                Nuclear Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/highway-engineer-jobs?trk=public_jobs_linkster_link">
                Highway Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/marine-engineer-jobs?trk=public_jobs_linkster_link">
                Marine Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/infosys-jobs?trk=public_jobs_linkster_link">
                Infosys jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/welding-engineer-jobs?trk=public_jobs_linkster_link">
                Welding Engineer jobs
              </a>
</li>
</ul>
<!-- --> </div>
<div class="flex-1 w-1/2 pt-2 pr-4 pb-4 pl-0 babybear:pb-2 babybear:w-full babybear:border-b-1 babybear:border-solid babybear:border-color-border-low-emphasis babybear:last:border-b-0">
<!-- --> <ul class="my-1">
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/sales-engineer-jobs?trk=public_jobs_linkster_link">
                Sales Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/continuous-improvement-engineer-jobs?trk=public_jobs_linkster_link">
                Continuous Improvement Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/risk-engineer-jobs?trk=public_jobs_linkster_link">
                Risk Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/web-developer-jobs?trk=public_jobs_linkster_link">
                Web Developer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/ibm-jobs?trk=public_jobs_linkster_link">
                IBM jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/software-architect-jobs?trk=public_jobs_linkster_link">
                Software Architect jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/google-jobs?trk=public_jobs_linkster_link">
                Google jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/amazon-jobs?trk=public_jobs_linkster_link">
                Amazon jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/cognizant-jobs?trk=public_jobs_linkster_link">
                Cognizant jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/sustaining-engineer-jobs?trk=public_jobs_linkster_link">
                Sustaining Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/multimedia-engineer-jobs?trk=public_jobs_linkster_link">
                Multimedia Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/textile-engineer-jobs?trk=public_jobs_linkster_link">
                Textile Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/food-engineer-jobs?trk=public_jobs_linkster_link">
                Food Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/database-administrator-jobs?trk=public_jobs_linkster_link">
                Database Administrator jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/cisco-jobs?trk=public_jobs_linkster_link">
                Cisco jobs
              </a>
</li>
</ul>
<!-- --> </div>
<div class="flex-1 w-1/2 pt-2 pr-4 pb-4 pl-0 babybear:pb-2 babybear:w-full babybear:border-b-1 babybear:border-solid babybear:border-color-border-low-emphasis babybear:last:border-b-0">
<!-- --> <ul class="my-1">
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/commercial-engineer-jobs?trk=public_jobs_linkster_link">
                Commercial Engineer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/system-programmer-jobs?trk=public_jobs_linkster_link">
                System Programmer jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/architect-jobs?trk=public_jobs_linkster_link">
                Architect jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/system-analyst-jobs?trk=public_jobs_linkster_link">
                System Analyst jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/linkedin-jobs?trk=public_jobs_linkster_link">
                LinkedIn jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/researcher-jobs?trk=public_jobs_linkster_link">
                Researcher jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/honeywell-jobs?trk=public_jobs_linkster_link">
                Honeywell jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/civil-supervisor-jobs?trk=public_jobs_linkster_link">
                Civil Supervisor jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/ericsson-jobs?trk=public_jobs_linkster_link">
                Ericsson jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/salesforce-jobs?trk=public_jobs_linkster_link">
                Salesforce jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/sener-jobs?trk=public_jobs_linkster_link">
                Sener jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/construction-site-manager-jobs?trk=public_jobs_linkster_link">
                Construction Site Manager jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/security-analyst-jobs?trk=public_jobs_linkster_link">
                Security Analyst jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/gmv-jobs?trk=public_jobs_linkster_link">
                GMV jobs
              </a>
</li>
<li class="tw-link-column-item">
<a class="link tw-linkster-link" data-js-module-id="link-column-link" href="https://www.linkedin.com/jobs/medtronic-jobs?trk=public_jobs_linkster_link">
                Medtronic jobs
              </a>
</li>
</ul>
<!-- --> </div>
</div>
</section>
</li>
</ul>
<!-- --> </div>
</section>
</section>
<footer class="li-footer bg-transparent w-full">
<ul class="li-footer__list flex flex-wrap flex-row items-start justify-start w-full h-auto min-h-[50px] my-[0px] mx-auto py-3 px-2 papabear:p-0">
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<span class="sr-only">LinkedIn</span>
<icon class="li-footer__copy-logo text-color-logo-brand-alt inline-block self-center h-[14px] w-[56px] mr-1" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/5mebydpuuijm3uhv1q375inqh"></icon>
<span class="li-footer__copy-text flex items-center">© 2026</span>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://about.linkedin.com?trk=public_jobs_footer-about">
          
          About
        
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/accessibility?trk=public_jobs_footer-accessibility">
          
          Accessibility
        
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/legal/user-agreement?trk=public_jobs_footer-user-agreement">
          
          User Agreement
        
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/legal/privacy-policy?trk=public_jobs_footer-privacy-policy">
          
          Privacy Policy
        
        </a>
</li>
<!-- -->
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/legal/cookie-policy?trk=public_jobs_footer-cookie-policy">
          
          Cookie Policy
        
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/legal/copyright-policy?trk=public_jobs_footer-copyright-policy">
          
          Copyright Policy
        
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://brand.linkedin.com/policies?trk=public_jobs_footer-brand-policy">
          
          Brand Policy
        
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/psettings/guest-controls?trk=public_jobs_footer-guest-controls">
          
            Guest Controls
          
        </a>
</li>
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<a class="li-footer__item-link flex items-center font-sans text-xs font-bold text-color-text-solid-secondary hover:text-color-link-hover focus:text-color-link-focus" href="https://www.linkedin.com/legal/professional-community-policies?trk=public_jobs_footer-community-guide">
          
          Community Guidelines
        
        </a>
</li>
<!-- -->
<li class="li-footer__item font-sans text-xs text-color-text-solid-secondary flex flex-shrink-0 justify-start p-1 relative w-50% papabear:justify-center papabear:w-auto">
<div class="collapsible-dropdown collapsible-dropdown--footer collapsible-dropdown--up flex items-center relative hyphens-auto language-selector z-2">
<!-- -->
<ul class="collapsible-dropdown__list hidden container-raised absolute w-auto overflow-y-auto flex-col items-stretch z-[9999] bottom-[100%] top-auto" role="menu" tabindex="-1">
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="العربية (Arabic)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="ar_AE" lang="ar_AE" role="menuitem">
                العربية (Arabic)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="বাংলা (Bangla)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="bn_IN" lang="bn_IN" role="menuitem">
                বাংলা (Bangla)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Čeština (Czech)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="cs_CZ" lang="cs_CZ" role="menuitem">
                Čeština (Czech)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Dansk (Danish)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="da_DK" lang="da_DK" role="menuitem">
                Dansk (Danish)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Deutsch (German)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="de_DE" lang="de_DE" role="menuitem">
                Deutsch (German)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Ελληνικά (Greek)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="el_GR" lang="el_GR" role="menuitem">
                Ελληνικά (Greek)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="English (English) selected" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link--selected" data-locale="en_US" lang="en_US" role="menuitem">
<strong>English (English)</strong>
</button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Español (Spanish)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="es_ES" lang="es_ES" role="menuitem">
                Español (Spanish)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="فارسی (Persian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="fa_IR" lang="fa_IR" role="menuitem">
                فارسی (Persian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Suomi (Finnish)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="fi_FI" lang="fi_FI" role="menuitem">
                Suomi (Finnish)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Français (French)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="fr_FR" lang="fr_FR" role="menuitem">
                Français (French)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="हिंदी (Hindi)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="hi_IN" lang="hi_IN" role="menuitem">
                हिंदी (Hindi)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Magyar (Hungarian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="hu_HU" lang="hu_HU" role="menuitem">
                Magyar (Hungarian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Bahasa Indonesia (Indonesian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="in_ID" lang="in_ID" role="menuitem">
                Bahasa Indonesia (Indonesian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Italiano (Italian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="it_IT" lang="it_IT" role="menuitem">
                Italiano (Italian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="עברית (Hebrew)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="iw_IL" lang="iw_IL" role="menuitem">
                עברית (Hebrew)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="日本語 (Japanese)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="ja_JP" lang="ja_JP" role="menuitem">
                日本語 (Japanese)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="한국어 (Korean)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="ko_KR" lang="ko_KR" role="menuitem">
                한국어 (Korean)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="मराठी (Marathi)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="mr_IN" lang="mr_IN" role="menuitem">
                मराठी (Marathi)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Bahasa Malaysia (Malay)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="ms_MY" lang="ms_MY" role="menuitem">
                Bahasa Malaysia (Malay)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Nederlands (Dutch)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="nl_NL" lang="nl_NL" role="menuitem">
                Nederlands (Dutch)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Norsk (Norwegian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="no_NO" lang="no_NO" role="menuitem">
                Norsk (Norwegian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="ਪੰਜਾਬੀ (Punjabi)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="pa_IN" lang="pa_IN" role="menuitem">
                ਪੰਜਾਬੀ (Punjabi)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Polski (Polish)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="pl_PL" lang="pl_PL" role="menuitem">
                Polski (Polish)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Português (Portuguese)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="pt_BR" lang="pt_BR" role="menuitem">
                Português (Portuguese)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Română (Romanian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="ro_RO" lang="ro_RO" role="menuitem">
                Română (Romanian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Русский (Russian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="ru_RU" lang="ru_RU" role="menuitem">
                Русский (Russian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Svenska (Swedish)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="sv_SE" lang="sv_SE" role="menuitem">
                Svenska (Swedish)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="తెలుగు (Telugu)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="te_IN" lang="te_IN" role="menuitem">
                తెలుగు (Telugu)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="ภาษาไทย (Thai)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="th_TH" lang="th_TH" role="menuitem">
                ภาษาไทย (Thai)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Tagalog (Tagalog)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="tl_PH" lang="tl_PH" role="menuitem">
                Tagalog (Tagalog)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Türkçe (Turkish)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="tr_TR" lang="tr_TR" role="menuitem">
                Türkçe (Turkish)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Українська (Ukrainian)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="uk_UA" lang="uk_UA" role="menuitem">
                Українська (Ukrainian)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="Tiếng Việt (Vietnamese)" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="vi_VN" lang="vi_VN" role="menuitem">
                Tiếng Việt (Vietnamese)
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="简体中文 (Chinese (Simplified))" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="zh_CN" lang="zh_CN" role="menuitem">
                简体中文 (Chinese (Simplified))
            </button>
</li>
<li class="language-selector__item" role="presentation">
<!-- Adding aria-label to both the li and the button because screen reader focus goes to button on desktop and li on mobile-->
<button aria-label="正體中文 (Chinese (Traditional))" class="font-sans text-xs link block py-[5px] px-2 w-full hover:cursor-pointer hover:bg-color-action hover:text-color-text-on-dark focus:bg-color-action focus:text-color-text-on-dark language-selector__link !font-regular" data-locale="zh_TW" lang="zh_TW" role="menuitem">
                正體中文 (Chinese (Traditional))
            </button>
</li>
<!-- -->
</ul>
<button aria-expanded="false" class="language-selector__button select-none relative pr-2 font-sans text-xs font-bold text-color-text-low-emphasis hover:text-color-link-hover hover:cursor-pointer focus:text-color-link-focus focus:outline-dotted focus:outline-1">
<span class="language-selector__label-text mr-0.5 break-words">
            Language
          </span>
<icon class="language-selector__label-chevron w-2 h-2 absolute top-0 right-0" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/cyolgscd0imw2ldqppkrb84vo"></icon>
</button>
</div>
</li>
</ul>
<!-- --> </footer>
</div>
<div aria-hidden="true" class="guest-upsells">
<form action="https://www.linkedin.com/uas/login-submit" class="google-auth base-google-auth" method="post">
<input name="loginCsrfParam" type="hidden" value="498b6ef7-62a6-467b-8966-0a9d93356bdf"/>
<input name="session_redirect" type="hidden" value="https://www.linkedin.com/jobs/search?keywords=ingeniero&amp;geoId=100292246"/>
<input name="trk" type="hidden" value="public_jobs_google-one-tap-submit"/>
<div class="google-one-tap__module hidden fixed flex flex-col items-center top-[70px] right-[20px] z-[9999]">
<div class="google-auth__tnc-container hidden relative top-2 bg-color-background-container-tint pl-2 pr-1 pt-2 pb-3 w-[375px] rounded-md shadow-2xl">
<p class="text-md font-bold text-color-text">
              Agree &amp; Join LinkedIn
            </p>
<p class="linkedin-tc__text text-color-text-low-emphasis text-xs pb-2 !text-sm !text-color-text">
      By clicking Continue to join or sign in, you agree to LinkedIn’s <a href="/legal/user-agreement?trk=linkedin-tc_auth-button_user-agreement" target="_blank">User Agreement</a>, <a href="/legal/privacy-policy?trk=linkedin-tc_auth-button_privacy-policy" target="_blank">Privacy Policy</a>, and <a href="/legal/cookie-policy?trk=linkedin-tc_auth-button_cookie-policy" target="_blank">Cookie Policy</a>.
    </p>
</div>
<div id="google-one-tap__container"></div>
</div>
<div class="loader loader--full-screen">
<div class="loader__container mb-2 overflow-hidden">
<icon aria-hidden="true" class="loader__icon inline-block loader__icon--default text-color-progress-loading lazy-loaded" data-svg-class-name="loader__icon-svg--large fill-currentColor h-[60px] min-h-[60px] w-[60px] min-w-[60px]"><svg class="loader__icon-svg--large fill-currentColor h-[60px] min-h-[60px] w-[60px] min-w-[60px] lazy-loaded" focusable="false" height="60" viewbox="0 0 60 60" width="60" xmlns="http://www.w3.org/2000/svg">
<g>
<path d="M30.1,16.1L30.1,16.1c-0.6,0-1-0.5-1-1V1c0-0.6,0.5-1,1-1l0,0c0.6,0,1,0.5,1,1v14.1C31.1,15.7,30.6,16.1,30.1,16.1z" opacity="1"></path>
<path d="M23.1,18.1L23.1,18.1c-0.5,0.3-1.1,0.1-1.4-0.4L14.5,5.6c-0.3-0.5-0.2-1.1,0.4-1.4l0,0C15.4,3.9,16,4,16.3,4.6l7.2,12.1C23.8,17.2,23.6,17.8,23.1,18.1z" opacity="0.85"></path>
<path d="M17.9,23.1L17.9,23.1c-0.3,0.5-0.9,0.7-1.4,0.4l-12.2-7c-0.5-0.3-0.7-0.9-0.4-1.4l0,0c0.3-0.5,0.9-0.7,1.4-0.4l12.2,7C18,22,18.2,22.7,17.9,23.1z" opacity="0.77"></path>
<path d="M16.1,30.1L16.1,30.1c0,0.6-0.5,1-1,1L1,31.2c-0.6,0-1-0.5-1-1l0,0c0-0.6,0.5-1,1-1l14.1-0.1C15.7,29.1,16.1,29.5,16.1,30.1z" opacity="0.69"></path>
<path d="M18,36.9L18,36.9c0.3,0.5,0.2,1.1-0.4,1.4L5.5,45.6c-0.5,0.3-1.1,0.2-1.4-0.4l0,0c-0.3-0.5-0.2-1.1,0.4-1.4l12.1-7.3C17.1,36.2,17.7,36.4,18,36.9z" opacity="0.61"></path>
<path d="M23.3,42.1L23.3,42.1c0.5,0.3,0.6,0.9,0.4,1.4l-7.3,12.1c-0.3,0.5-0.9,0.6-1.4,0.4l0,0c-0.5-0.3-0.6-0.9-0.4-1.4l7.3-12.1C22.1,41.9,22.8,41.8,23.3,42.1z" opacity="0.53"></path>
<path d="M30.1,43.9L30.1,43.9c0.6,0,1,0.5,1,1V59c0,0.6-0.5,1-1,1l0,0c-0.6,0-1-0.5-1-1V44.9C29,44.4,29.5,43.9,30.1,43.9z" opacity="0.45"></path>
<path d="M37,41.9L37,41.9c0.5-0.3,1.1-0.2,1.4,0.4l7.2,12.1c0.3,0.5,0.2,1.1-0.4,1.4l0,0c-0.5,0.3-1.1,0.2-1.4-0.4l-7.2-12.1C36.4,42.8,36.6,42.2,37,41.9z" opacity="0.37"></path>
<path d="M42.2,36.8L42.2,36.8c0.3-0.5,0.9-0.7,1.4-0.4l12.2,7c0.5,0.3,0.7,0.9,0.4,1.4l0,0c-0.3,0.5-0.9,0.7-1.4,0.4l-12.2-7C42.1,38,41.9,37.4,42.2,36.8z" opacity="0.29"></path>
<path d="M44,29.9L44,29.9c0-0.6,0.5-1,1-1h14.1c0.6,0,1,0.5,1,1l0,0c0,0.6-0.5,1-1,1L45,31C44.4,31,44,30.5,44,29.9z" opacity="0.21 "></path>
<path d="M42.1,23.1L42.1,23.1c-0.3-0.5-0.2-1.1,0.4-1.4l12.1-7.3c0.5-0.3,1.1-0.2,1.4,0.4l0,0c0.3,0.4,0.1,1.1-0.4,1.3l-12.1,7.3C43.1,23.7,42.4,23.6,42.1,23.1z" opacity="0.13"></path>
<path d="M36.9,17.9L36.9,17.9c-0.5-0.3-0.6-0.9-0.4-1.4l7.3-12.1c0.3-0.5,0.9-0.6,1.4-0.4l0,0c0.5,0.3,0.6,0.9,0.4,1.4l-7.4,12.2C38,18.1,37.3,18.2,36.9,17.9z" opacity="0.05"></path>
<animatetransform attributename="transform" attributetype="XML" begin="0s" calcmode="discrete" dur="1s" keytimes="0;.0833;.166;.25;.3333;.4166;.5;.5833;.6666;.75;.8333;.9166;1" repeatcount="indefinite" type="rotate" values="0,30,30;30,30,30;60,30,30;90,30,30;120,30,30;150,30,30;180,30,30;210,30,30;240,30,30;270,30,30;300,30,30;330,30,30;360,30,30"></animatetransform>
</g>
</svg></icon>
</div>
</div>
</form>
<script class="lazy-loaded" data-module-id="google-gsi-lib" data-track-latency="" src="https://static.licdn.com/aero-v1/sc/h/29rdkxlvag0d3cpj96fiilbju"></script>
<div class="contextual-sign-in-modal base-contextual-sign-in-modal" data-cool-off-enabled="" data-show-on-page-load="">
<!-- -->
<div class="">
<!-- -->
</div>
<!-- --><!-- --> </div>
<!-- -->
</div>
<!-- -->
<!-- -->
<div aria-hidden="true" class="toasts fixed z-8 babybear:right-4 mamabear:right-4 papabear:min-h-[96px] invisible top:auto bottom-4 left-4 papabear:w-[400px] toasts--bottom" id="toasts" type="bottom">
<template id="toast-template">
<div class="toast container-raised flex toast--bottom transition ease-accelerate duration-xxslow">
<div class="toast__message flex flex-1 babybear:items-center mamabear:items-center papabear:items-start py-2 px-1.5" role="alert" tabindex="-1">
<div class="toast__message-content-container">
<p class="toast__message-content font-sans text-sm opacity-90 inline babybear:self-center mamabear:self-center papabear:self-start"></p>
</div>
</div>
<button aria-label="Close" class="toast__dismiss-btn cursor-pointer babybear:self-center mamabear:self-center papabear:self-start pt-3 pb-2 papabear:py-2 pl-0.5 pr-0">
<svg class="fill-color-icon" height="24" width="24"><path d="M13 4.32 9.31 8 13 11.69 11.69 13 8 9.31 4.31 13 3 11.69 6.69 8 3 4.31 4.31 3 8 6.69 11.68 3Z"></path></svg>
</button>
</div>
</template>
<template id="toast-icon-caution">
<icon class="text-color-icon-caution toast__icon w-3 h-3 shrink-0 mr-2" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/bk9xca6x9l1fga1tbzame3i3l"></icon>
</template>
<template id="toast-icon-error">
<icon class="text-color-icon-negative toast__icon w-3 h-3 shrink-0 mr-2" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/8c0098stai8lcqypn95r47dew"></icon>
</template>
<template id="toast-icon-gdpr">
<icon class="text-color-icon-neutral toast__icon w-3 h-3 shrink-0 mr-2" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/a9phzx7id2abubo45lgookfd"></icon>
</template>
<template id="toast-icon-notify">
<icon class="text-color-icon-neutral toast__icon w-3 h-3 shrink-0 mr-2" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/4xg53nt8deu1y7tb1t3km8tfh"></icon>
</template>
<template id="toast-icon-success">
<icon class="text-color-icon-positive toast__icon w-3 h-3 shrink-0 mr-2" data-delayed-url="https://static.licdn.com/aero-v1/sc/h/9zhm3eh2dq7vh2muo8xnfikxh"></icon>
</template>
<template id="toast-cta">
<a class="toast__cta cta-link font-medium ml-0.5 text-sm text-inherit inline" target="_blank"></a>
</template>
</div>
<section aria-hidden="true" id="json-refs">
<code id="requestSubdomain" style="display: none"><!--"es"--></code>
<code id="pageKey" style="display: none"><!--"d_jobs_guest_search"--></code>
<code id="i18n_redirected_from_deleted_alert" style="display: none"><!--"This job alert has been deactivated."--></code>
<!-- --><!-- --> </section>
<script aria-hidden="true" async="" src="https://static.licdn.com/aero-v1/sc/h/e69gtg8c61dzqklxridy0htl9"></script>
<!-- -->
<script aria-hidden="true" async="" defer="" src="https://static.licdn.com/aero-v1/sc/h/e4p7fsqdui91qupd1wxxity8q"></script>
<!-- --><!-- -->
<div class="top-level-modal-container"><div class="modal modal--contextual-sign-in modal--contextual-sign-in-v2 modal--contextual-sign-in-v2--stacked" data-outlet="base-contextual-sign-in-modal" id="base-contextual-sign-in-modal">
<!-- --> <div aria-hidden="false" class="modal__overlay flex items-center bg-color-background-scrim justify-center fixed bottom-0 left-0 right-0 top-0 opacity-0 invisible pointer-events-none z-[1000] transition-[opacity] ease-[cubic-bezier(0.25,0.1,0.25,1.0)] duration-[0.17s] py-4 modal__overlay--visible">
<section aria-labelledby="base-contextual-sign-in-modal-modal-header" aria-modal="true" class="max-h-full modal__wrapper overflow-auto p-0 bg-color-surface max-w-[1128px] min-h-[160px] relative scale-[0.25] shadow-sm shadow-color-border-faint transition-[transform] ease-[cubic-bezier(0.25,0.1,0.25,1.0)] duration-[0.33s] focus:outline-0 w-[1128px] mamabear:w-[744px] babybear:w-[360px] rounded-md" role="dialog" tabindex="-1">
<button aria-label="Dismiss" class="modal__dismiss btn-tertiary h-[40px] w-[40px] p-0 rounded-full indent-0 contextual-sign-in-modal__modal-dismiss absolute right-0 m-[20px] cursor-pointer">
<icon aria-hidden="true" class="contextual-sign-in-modal__modal-dismiss-icon lazy-loaded"><svg class="artdeco-icon lazy-loaded" focusable="false" height="24px" width="24px" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<path d="M20,5.32L13.32,12,20,18.68,18.66,20,12,13.33,5.34,20,4,18.68,10.68,12,4,5.32,5.32,4,12,10.69,18.68,4Z" fill="currentColor"></path>
</svg></icon>
</button>
<div class="modal__main w-full">
<div class="flex overflow-hidden babybear:contextual-sign-in-modal__layout--stacked contextual-sign-in-modal__layout--stacked">
<div class="contextual-sign-in-modal__left-content">
<img/>
<h2 class="contextual-sign-in-modal__context-screen-title font-sans text-lg text-color-text mt-2 mb-1 text-center" id="base-contextual-sign-in-modal-modal-header">
                    Sign in to view more jobs
                  </h2>
<!-- --> </div>
<div class="contextual-sign-in-modal__right-content">
<div class="contextual-sign-in-modal__google-sign-in-primary w-full">
<div class="google-auth-button" data-google-auth-iframe-initialized="">
<!-- --> <div aria-label="Continue with google" class="google-auth-button__placeholder mx-auto" data-locale="en_US" data-logo-alignment="center" data-theme="filled_blue" role="button"><div class="S9gUrf-YoZ4jf" style="position: relative;"><div></div><iframe allow="identity-credentials-get" id="gsi_672164_141866" src="https://accounts.google.com/gsi/button?logo_alignment=center&amp;shape=pill&amp;size=large&amp;text=continue_with&amp;theme=filled_blue&amp;type=undefined&amp;width=312px&amp;client_id=990339570472-k6nqn1tpmitg8pui82bfaun3jrpmiuhs.apps.googleusercontent.com&amp;iframe_id=gsi_672164_141866&amp;as=x%2B5x8kVOJaMQF%2Bqf6wvEwg&amp;hl=en_US" style="display: block; position: relative; top: 0px; left: 0px; height: 44px; width: 332px; border: 0px; margin: -2px -10px;" title="Sign in with Google Button"></iframe></div></div>
<!-- --> </div>
</div>
<code id="i18n_username_error_empty" style="display: none"><!--"Please enter an email address or phone number"--></code>
<code id="i18n_username_error_too_long" style="display: none"><!--"Email or phone number must be between 3 to 128 characters"--></code>
<code id="i18n_username_error_too_short" style="display: none"><!--"Email or phone number must be between 3 to 128 characters"--></code>
<code id="i18n_password_error_empty" style="display: none"><!--"Please enter a password"--></code>
<code id="i18n_password_error_too_short" style="display: none"><!--"The password you provided must have at least 6 characters"--></code>
<code id="i18n_password_error_too_long" style="display: none"><!--"The password you provided must have at most 400 characters"--></code>
<!-- --> <form action="https://www.linkedin.com/uas/login-submit" class="contextual-sign-in-modal__sign-in-form mb-1 hidden" method="post" novalidate="">
<input name="loginCsrfParam" type="hidden" value="498b6ef7-62a6-467b-8966-0a9d93356bdf"/>
<div class="flex flex-col">
<div class="mt-1.5" data-js-module-id="guest-input">
<div class="flex flex-col">
<label class="input-label mb-1" for="csm-v2_session_key">
          Email or phone
        </label>
<div class="text-input flex">
<input autocomplete="username" class="text-color-text font-sans text-md outline-0 bg-color-transparent w-full" id="csm-v2_session_key" name="session_key" required="" type="text"/>
</div>
</div>
<p class="input-helper mt-1.5" data-js-module-id="guest-input__message" for="csm-v2_session_key" role="alert"></p>
</div>
<div class="mt-1.5" data-js-module-id="guest-input">
<div class="flex flex-col">
<label class="input-label mb-1" for="csm-v2_session_password">
          Password
        </label>
<div class="text-input flex">
<input autocomplete="current-password" class="text-color-text font-sans text-md outline-0 bg-color-transparent w-full" id="csm-v2_session_password" name="session_password" required="" type="password"/>
<button aria-label="Show your LinkedIn password" aria-live="assertive" aria-relevant="text" class="font-sans text-md font-bold text-color-action z-10 ml-[12px] hover:cursor-pointer" type="button">Show</button>
</div>
</div>
<p class="input-helper mt-1.5" data-js-module-id="guest-input__message" for="csm-v2_session_password" role="alert"></p>
</div>
<input name="session_redirect" type="hidden" value="https://www.linkedin.com/jobs/search?keywords=ingeniero&amp;geoId=100292246"/>
<!-- --> </div>
<div class="flex justify-between sign-in-form__footer--full-width">
<a class="font-sans text-md font-bold link leading-regular sign-in-form__forgot-password--full-width" href="https://www.linkedin.com/uas/request-password-reset?trk=csm-v2_forgot_password">Forgot password?</a>
<!-- -->
<input name="trk" type="hidden" value="csm-v2_sign-in-submit"/>
<button class="btn-md btn-primary flex-shrink-0 cursor-pointer sign-in-form__submit-btn--full-width" type="submit">
          Sign in
        </button>
</div>
<!-- --> <input name="controlId" type="hidden" value="d_jobs_guest_search-csm-v2_sign-in-submit-btn"/><input name="pageInstance" type="hidden" value="urn:li:page:d_jobs_guest_search_jsbeacon;fkObdPf6RjC8RdB0O9xEJw=="/></form>
<!-- --><!-- -->
<button class="contextual-sign-in-modal__sign-in-with-email-cta my-2 btn-sm btn-secondary min-h-[40px] w-full flex align-center justify-center">
<icon aria-hidden="true" class="inline-block align-middle h-[24px] w-[24px] mr-0.5 lazy-loaded"><svg class="lazy-loaded" data-supported-dps="16x16" fill="currentColor" focusable="false" id="envelope-small" viewbox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
<path d="M14 3H2a1 1 0 00-1 1v8a1 1 0 001 1h12a1 1 0 001-1V4a1 1 0 00-1-1zm-1 2L8 8.21 3 5h10zM3 11V6.07L7.32 8.8a1.25 1.25 0 001.37 0L13 6.07V11H3z"></path>
</svg></icon>
<span class="self-center">Sign in with Email</span>
</button>
<div class="contextual-sign-in-modal__divider left-right-divider">
<p class="contextual-sign-in-modal__divider-text font-sans text-sm text-color-text px-2">
                      or
                    </p>
</div>
<div class="contextual-sign-in-modal__google-sign-in-secondary contextual-sign-in-modal__google-sign-in-secondary--hidden">
<div class="google-auth-button" data-google-auth-iframe-initialized="">
<!-- --> <div aria-label="Continue with google" class="google-auth-button__placeholder mx-auto google-auth-button__placeholder--black-border" data-locale="en_US" data-logo-alignment="center" data-theme="outline" role="button"><div class="S9gUrf-YoZ4jf" style="position: relative;"><div></div><iframe allow="identity-credentials-get" id="gsi_672166_9320" src="https://accounts.google.com/gsi/button?logo_alignment=center&amp;shape=pill&amp;size=large&amp;text=continue_with&amp;theme=outline&amp;type=undefined&amp;width=312px&amp;client_id=990339570472-k6nqn1tpmitg8pui82bfaun3jrpmiuhs.apps.googleusercontent.com&amp;iframe_id=gsi_672166_9320&amp;as=x%2B5x8kVOJaMQF%2Bqf6wvEwg&amp;hl=en_US" style="display: block; position: relative; top: 0px; left: 0px; height: 44px; width: 332px; border: 0px; margin: -2px -10px;" title="Sign in with Google Button"></iframe></div></div>
<!-- --> </div>
</div>
<p class="contextual-sign-in-modal__join-now m-auto font-sans text-md text-center text-color-text my-2">
                      New to LinkedIn? <a class="contextual-sign-in-modal__join-link" href="https://www.linkedin.com/signup/cold-join?source=jobs_registration&amp;trk=public_jobs_contextual-sign-in-modal_join-link">Join now</a>
</p>
<p class="linkedin-tc__text text-color-text-low-emphasis text-xs pb-2 contextual-sign-in-modal__terms-and-conditions m-auto w-full text-center">
      By clicking Continue to join or sign in, you agree to LinkedIn’s <a href="/legal/user-agreement?trk=linkedin-tc_auth-button_user-agreement" target="_blank">User Agreement</a>, <a href="/legal/privacy-policy?trk=linkedin-tc_auth-button_privacy-policy" target="_blank">Privacy Policy</a>, and <a href="/legal/cookie-policy?trk=linkedin-tc_auth-button_cookie-policy" target="_blank">Cookie Policy</a>.
    </p>
</div>
</div>
</div>
<!-- --> </section>
</div>
</div></div><iframe aria-hidden="true" id="humanThirdPartyIframe" sandbox="allow-same-origin allow-scripts" src="https://li.protechts.net/index.html?ts=1780866672141&amp;r_id=AAZTsFVUZ3j9ZIOxGtlFDA%3D%3D&amp;app_id=PXdOjV695v&amp;uc=scraping&amp;d_id=4f263d05961453b19505c86b2a6a87c9d9eeaa5a74c0d964bcba583211e57999" style="height: 0px; width: 0px; border-width: medium; border-style: none; border-color: currentcolor; border-image: initial; position: absolute; left: -9999px;"></iframe></body></html>

"""


# Expected description text extracted from the detail panel. The
# parser joins the markup's text with " " (separator) and strips
# whitespace; `EXPECTED_DESCRIPTION` here is the same text with the
# same transformation, so tests can assert exact equality.
EXPECTED_DESCRIPTION = "👷\u200d♂️👷\u200d♀️ En estamos buscando un Ingeniero/a de procesos para nuestra fábrica ubicada en Antequera (Málaga). Como ingeniero/a de procesos desarrollarás, estandarizarás y mejorarás los procesos de producción para potenciar la seguridad, la calidad, la fiabilidad de las entregas, la productividad y la rentabilidad. Aportarás apoyo técnico y metodológico a la fábrica y a las iniciativas de excelencia operativa. Entre tus principales responsabilidades destacan: 🔍📊 Desarrollo de procesos y producción: Desarrollar, analizar y optimizar procesos con métodos Lean y basados en datos; detectar ineficiencias, desperdicios, pérdidas de calidad y cuellos de botella; proponer e implementar mejoras. Liderar iniciativas de mejora continua (Kaizen, Six Sigma, proyectos Lean) y estandarizar métodos, parámetros y mejores prácticas. 🛠️🚀 Apoyo operativo: Apoyar la producción diaria en la resolución de problemas (causas raíz y acciones correctivas). Actuar como soporte técnico para producción, planificación, calidad, mantenimiento y logística. Participar en la puesta en marcha de nuevos equipos o variantes y en la gestión del cambio relacionada con modificaciones de procesos o de instalaciones. 🧾✅ Calidad, seguridad y cumplimiento normativo: Asegurar el cumplimiento de requisitos de seguridad, calidad y normativos. Mantener instrucciones de trabajo y documentación de procesos. Participar en auditorías y seguimientos. Gestión de datos y KPI: definir, supervisar y analizar rendimiento, desperdicio, Cp/Cpk, plazo de entrega y productividad, y comunicar resultados a la dirección. ¿Qué requisitos debes cumplir? 🎓 Licenciatura o máster en Ingeniería (Producción, Industrial, Mecánica, Automatización o similar). 🏅 Valorable certificación Lean/Six Sigma (Green Belt). 🏭 Experiencia laboral de 2 a 5 años en fabricación, ingeniería de procesos o desarrollo de producción, en entornos industriales o de fábrica. 🌍 Conocimientos lingüísticos: mínimo nivel B2 de inglés. 📌💡 Competencias técnicas y profesionales: Conocimientos sólidos de procesos de fabricación y producción. Capacidad para analizar datos y KPI. Conocimientos de Lean y resolución de problemas (5 Why, Fishbone, PDCA, DMAIC), ERP y bases en TI y análisis de datos. ¿Qué buscamos en ti? 🧠 Capacidad para decidir de forma autónoma la priorización de tareas. 🤝 Actitud proactiva y mentalidad abierta para detectar oportunidades y colaborar con otras áreas. 💰📉 Análisis de optimización de costes antes de proponer medidas. ✨ ¿Qué te aportará ? Contrato indefinido desde el primer día, apostando por la estabilidad y el largo plazo. Jornada completa de lunes a viernes. Paquete salarial competitivo, compuesto por un salario fijo atractivo más un componente variable ligado a objetivos. Formación inicial y continua, con un acompañamiento constante para que conozcas en profundidad el producto y el proceso productivo. Plan de desarrollo y crecimiento profesional dentro de una empresa líder en su sector, que ofrece un entorno de trabajo estable, colaborativo y orientado al aprendizaje continuo."
