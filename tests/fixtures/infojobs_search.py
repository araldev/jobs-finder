"""InfoJobs search results HTML fixture used by parser tests.

Spec: REQ-J-001 / REQ-J-005.

`SEARCH_PAGE_HTML` is a SYNTHETIC placeholder. It mirrors the
InfoJobs SERP DOM observed via `webfetch` during the proposal phase
of the `infojobs_platform` change. T-010 (later batch) replaces the
placeholder with REAL captured HTML from
`https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid` taken
with `playwright-stealth`; any selector assumption that disagrees
with the real DOM is fixed in the parser, not the test.

`BLOCKED_PAGE_HTML` is a synthetic Distil + Geetest fixture retained
for the `is_infojobs_blocked` tests. The page embeds BOTH canonical
anti-bot signals (the Distil title AND a Geetest iframe) so the
detector's "any one is sufficient" contract is satisfied even if
either signal changes in the future.

Card shape (placeholder, from the InfoJobs SERP observation):
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-{id}">
              <h2 class="ij-OfferCardContent-description-title">{title}</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">{company}</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">{location}</li>
            <li class="ij-OfferCardContent-description-list-item">{salary_or_other}</li>
          </ul>
          <div class="ij-OfferCardContent-date">{date_text}</div>
        </div>
      </div>
    </li>

The id is extracted from the title-anchor `href` (`/oferta-{id}`).
InfoJobs DOES render an inline posted-date on the card (the design
calls this out explicitly). The placeholder uses Spanish
relative-time strings (`Hoy`, `Hace 2 horas`, `hace 30+ días`,
`Hace 3 días`, `Recién publicado`) — same grammar as the Indeed
parser — and the parser's `_parse_relative_date` mirrors Indeed's
implementation. The T-010 real capture may need to update the date
selector if the live DOM uses a different class.
"""

from __future__ import annotations

# 15 cards: 3 each of 5 required date strings.
#
# Layout: (id, title, company, location, date_text). The ids are
# 7-character alphanumeric slugs (mirroring a realistic InfoJobs
# offer id shape) and the href pattern is
# `/ofertas-trabajo/oferta-<id>`. Titles/companies/locations are
# deterministic so the parser tests can pin exact field values.
_CARDS: list[tuple[str, str, str, str, str]] = [
    # Hoy (3 cards)
    (
        "abc123001",
        "Senior Python Developer",
        "InfoJobs Co 1",
        "Madrid, Spain",
        "Hoy",
    ),
    (
        "abc123002",
        "Python Backend Engineer",
        "InfoJobs Co 2",
        "Barcelona, Spain",
        "Hoy",
    ),
    (
        "abc123003",
        "Data Engineer Python",
        "InfoJobs Co 3",
        "Valencia, Spain",
        "Hoy",
    ),
    # Hace 2 horas (3 cards)
    (
        "abc123004",
        "Junior Python Developer",
        "InfoJobs Co 4",
        "Sevilla, Spain",
        "Hace 2 horas",
    ),
    (
        "abc123005",
        "Python Full-Stack",
        "InfoJobs Co 5",
        "Bilbao, Spain",
        "Hace 2 horas",
    ),
    (
        "abc123006",
        "DevOps Python",
        "InfoJobs Co 6",
        "Zaragoza, Spain",
        "Hace 2 horas",
    ),
    # hace 30+ días (3 cards)
    (
        "abc123007",
        "Python Architect",
        "InfoJobs Co 7",
        "Málaga, Spain",
        "hace 30+ días",
    ),
    (
        "abc123008",
        "QA Automation Python",
        "InfoJobs Co 8",
        "Granada, Spain",
        "hace 30+ días",
    ),
    (
        "abc123009",
        "Python SRE",
        "InfoJobs Co 9",
        "Alicante, Spain",
        "hace 30+ días",
    ),
    # Hace 3 días (3 cards)
    (
        "abc123010",
        "Machine Learning Engineer",
        "InfoJobs Co 10",
        "Murcia, Spain",
        "Hace 3 días",
    ),
    (
        "abc123011",
        "Python Microservices",
        "InfoJobs Co 11",
        "Valladolid, Spain",
        "Hace 3 días",
    ),
    (
        "abc123012",
        "Backend Python Developer",
        "InfoJobs Co 12",
        "Salamanca, Spain",
        "Hace 3 días",
    ),
    # Recién publicado (3 cards)
    (
        "abc123013",
        "Python Tech Lead",
        "InfoJobs Co 13",
        "Córdoba, Spain",
        "Recién publicado",
    ),
    (
        "abc123014",
        "Python Data Scientist",
        "InfoJobs Co 14",
        "A Coruña, Spain",
        "Recién publicado",
    ),
    (
        "abc123015",
        "Python Backend (Remote)",
        "InfoJobs Co 15",
        "Remote, Spain",
        "Recién publicado",
    ),
]


def _render_cards() -> str:
    """Render the synthetic card list as a search-results page body."""
    parts: list[str] = []
    for job_id, title, company, location, date_text in _CARDS:
        parts.append(
            f"""
      <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
        <div class="ij-OfferCardContent">
          <div class="ij-OfferCardContent-description">
            <div class="ij-OfferCardContent-description-head">
              <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-{job_id}">
                <h2 class="ij-OfferCardContent-description-title">{title}</h2>
              </a>
            </div>
            <div class="ij-OfferCardContent-description-subtitle">{company}</div>
            <ul class="ij-OfferCardContent-description-list">
              <li class="ij-OfferCardContent-description-list-item">{location}</li>
              <li class="ij-OfferCardContent-description-list-item">Salario no disponible</li>
            </ul>
            <div class="ij-OfferCardContent-date">{date_text}</div>
          </div>
        </div>
      </li>"""
        )
    return "\n".join(parts)


SEARCH_PAGE_HTML = """<!DOCTYPE html>
<html dir="ltr" lang="es">
<head>
  <meta charset="utf-8">
  <title>Ofertas de trabajo de python en Madrid | InfoJobs</title>
  <meta name="description" content="Encuentra ofertas de trabajo de python en Madrid provincia en el portal de empleo InfoJobs.">
  <link rel="canonical" href="https://www.infojobs.net/ofertas-trabajo?q=python&amp;l=madrid">
</head>
<body>
  <main>
    <h1>python en Madrid — 1.234 ofertas de empleo</h1>
    <ul class="ij-List ij-OfferList">
{_CARDS_BODY}
    </ul>
  </main>
</body>
</html>
""".replace("{_CARDS_BODY}", _render_cards())


# ---------------------------------------------------------------------------
# Blocked-page fixture (synthetic Distil + Geetest).
#
# The page embeds BOTH canonical anti-bot signals so the detector's
# "any one is sufficient" contract is satisfied. A future InfoJobs
# copy change that flips the title OR removes the iframe does not
# silently disable the detector — at least one signal is always
# present.
# ---------------------------------------------------------------------------

BLOCKED_PAGE_HTML = """<!DOCTYPE html>
<html dir="ltr" lang="es">
<head>
  <meta charset="utf-8">
  <title>No podemos identificar tu navegador</title>
  <meta name="robots" content="noindex">
</head>
<body>
  <h1>Verificando tu navegador antes de acceder a InfoJobs</h1>
  <p>Este proceso es automático. El navegador está siendo verificado.</p>
  <p>Por favor, espera unos segundos...</p>

  <!-- Geetest anti-bot iframe (Distil + Geetest layered protection). -->
  <iframe src="https://api.geetest.com/get.php?gt=infojobs&amp;challenge=test" width="0" height="0" frameborder="0"></iframe>

  <noscript>
    <p>Por favor, habilita JavaScript y las cookies para continuar.</p>
  </noscript>
</body>
</html>
"""
