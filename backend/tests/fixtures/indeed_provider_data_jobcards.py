"""Indeed `providerData["mosaic-provider-jobcards"]` JSON fixture.

Spec: REQ-PARSER-INDEED-SNIPPET-001 (Camino 1, 2026-06-12).

Real capture from es.indeed.com SERP for `q=python&l=madrid`,
performed 2026-06-12 via a sanctioned one-time Playwright
capture (per AGENTS.md rule #1). The fixture exposes:

1. `PROVIDER_DATA_JSON` — the parsed Python dict from the
   jobcards provider's JSON object. 3 job entries (the first
   3 from the live capture) with `jobkey`, `title`, `company`,
   `snippet` fields. Useful for tests that need to inspect
   the JSON structure directly.

2. `PAGE_HTML` — a minimal HTML page that contains the JSON
   inline (in a `<script>` tag) with the exact anchor the
   parser looks for. The parser scans the raw page HTML and
   matches the anchor via `str.find`, so the surrounding
   HTML structure is irrelevant — only the anchor + JSON
   shape matter. Used by tests for
   `extract_indeed_snippets_from_provider_data()`.

3. `SNIPPET_JOBKEYS` — the list of `jobkey` values in the
   fixture (in order). Useful for assertions.
"""

PROVIDER_DATA_JSON = {'metaData': {'isJpBundle': False}, 'mosaicProviderJobCardsModel': {'jobListings': [{'jobkey': 'dba0611af22b2374', 'title': 'Especialista en IA con Python', 'company': '', 'snippet': '<ul style="list-style-type:circle;margin-top: 0px;margin-bottom: 0px;padding-left:20px;">\n <li>Buscamos incorporar un/a Especialista en Inteligencia Artificial con experiencia en <b>Python</b>, orientado/a a la implementación práctica de soluciones y…</li>\n</ul>'}, {'jobkey': '7bc5f5f2d189a262', 'title': 'Desarrollador/a Python Junior', 'company': '', 'snippet': '<ul style="list-style-type:circle;margin-top: 0px;margin-bottom: 0px;padding-left:20px;">\n <li>Estamos en busca de profesionales que no solo busquen un empleo, sino que aspiren a integrarse en equipos que lideran la transformación en sectores estratégicos…</li>\n</ul>'}, {'jobkey': '74e944b8e04bff12', 'title': 'Desarrollador Python', 'company': '', 'snippet': '<ul style="list-style-type:circle;margin-top: 0px;margin-bottom: 0px;padding-left:20px;">\n <li>Experiencia demostrable como Desarrollador <b>Python</b> o Full Stack Developer, con especialización en el backend basado en Python.</li>\n</ul>'}]}}

PAGE_HTML = '<html><head><script>\nwindow.mosaic.providerData["mosaic-provider-jobcards"]={"metaData":{"isJpBundle":false},"mosaicProviderJobCardsModel":{"jobListings":[{"jobkey":"dba0611af22b2374","title":"Especialista en IA con Python","company":"","snippet":"<ul style=\\"list-style-type:circle;margin-top: 0px;margin-bottom: 0px;padding-left:20px;\\">\\n <li>Buscamos incorporar un/a Especialista en Inteligencia Artificial con experiencia en <b>Python</b>, orientado/a a la implementación práctica de soluciones y…</li>\\n</ul>"},{"jobkey":"7bc5f5f2d189a262","title":"Desarrollador/a Python Junior","company":"","snippet":"<ul style=\\"list-style-type:circle;margin-top: 0px;margin-bottom: 0px;padding-left:20px;\\">\\n <li>Estamos en busca de profesionales que no solo busquen un empleo, sino que aspiren a integrarse en equipos que lideran la transformación en sectores estratégicos…</li>\\n</ul>"},{"jobkey":"74e944b8e04bff12","title":"Desarrollador Python","company":"","snippet":"<ul style=\\"list-style-type:circle;margin-top: 0px;margin-bottom: 0px;padding-left:20px;\\">\\n <li>Experiencia demostrable como Desarrollador <b>Python</b> o Full Stack Developer, con especialización en el backend basado en Python.</li>\\n</ul>"}]}};\n</script></head></html>'

SNIPPET_JOBKEYS = ['dba0611af22b2374', '7bc5f5f2d189a262', '74e944b8e04bff12']
