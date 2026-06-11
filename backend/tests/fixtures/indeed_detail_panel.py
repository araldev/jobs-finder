"""Indeed detail panel HTML fixture (after clicking a card) used by parser tests.

Spec: REQ-PARSER-INDEED-DETAIL-001 (pinned by `jobs-finder-camino-1`,
Camino 1).

This fixture is a REAL capture of the `#jobDescriptionText` element
that Indeed renders when a user clicks on a job card on the SERP. The
capture was performed on 2026-06-11 against es.indeed.com by clicking
the first result card for `q=python&l=madrid` and reading the resulting
detail panel HTML via `page.locator("#jobDescriptionText").evaluate(
"el => el.outerHTML")`.

Sanctioned by AGENTS.md rule #1 (one-time manual Playwright capture; the
HTML is committed, the capture script is not).

EMPIRICAL FINDING (Camino 1):
Indeed renders the full job description in a separate detail panel when
the user clicks a card. The SERP-side `belowJobSnippet` block on the
new layout is EMPTY (the real capture shows it has no `<li>` bullets).
The full description lives in:

    <div id="jobDescriptionText" class="jobsearch-JobComponent-description ...">
      <div>
        <h2><b>Descripción:</b></h2>
        <p>...</p>
        <ul><li>...</li></ul>
      </div>
    </div>

The `parse_indeed_detail_description` parser reads this element and
returns the text content (with `<br>` -> " " and `<li>` joined with
" | ") so the LLM downstream gets a single scrubbable string.

VERIFICATION
The captured panel is ~3600 bytes and contains the full description for
a Spanish AI Specialist / Python job post (the first result on the
es.indeed.com SERP for `q=python&l=madrid` at capture time).
"""

PANEL_HTML = """\
<div id="jobDescriptionText" class="jobsearch-JobComponent-description css-jsfa0i eu4oa1w0"><div>
 <h2><b>Descripción:</b></h2>
 <p></p>
 <p>Buscamos incorporar un/a Especialista en Inteligencia Artificial con experiencia en Python, orientado/a a la implementación práctica de soluciones y automatización mediante IA. La persona seleccionada formará parte de un equipo técnico enfocado en desarrollar y poner en marcha casos de uso reales, contribuyendo a la mejora de procesos y toma de decisiones basada en datos.</p>
 <p></p>
 <p><br>
   Funciones principales:</p>
 <p></p>
 <ul>
  <li>Diseño e implementación de casos de uso de Inteligencia Artificial aplicados al negocio.</li>
  <li>Desarrollo y despliegue de modelos de machine learning y soluciones basadas en IA.</li>
  <li>Automatización de procesos mediante herramientas y frameworks de IA.</li>
  <li>Integración de modelos con sistemas existentes y bases de datos sectoriales.</li>
  <li>Análisis, tratamiento y explotación de datos para generar valor.</li>
  <li>Colaboración con equipos técnicos y de negocio para identificar oportunidades de aplicación de IA.</li>
 </ul>
 <br>
 <p></p>
 <h2><b>Requisitos:</b></h2>
 <p></p>
 <p>Requisitos:</p>
 <p></p>
 <ul>
  <li>Experiencia en desarrollo con Python.</li>
  <li>Conocimientos en machine learning y/o inteligencia artificial aplicada.</li>
  <li>Experiencia en manejo de bases de datos (SQL y/o NoSQL), idealmente en entornos sectoriales.</li>
  <li>Capacidad para implementar soluciones prácticas (no es necesario perfil de arquitectura).</li>
  <li>Experiencia en automatización de procesos.</li>
  <li>Valorable conocimiento de herramientas de IA generativa, LLMs o frameworks modernos.</li>
 </ul>Se valorará: 
 <br>
 <ul>
  <li>Experiencia en despliegue de modelos en producción.</li>
  <li>Conocimientos de cloud (AWS, GCP o Azure).</li>
  <li>Experiencia en integración de APIs y microservicios.</li>
  <li>Capacidad analítica y orientación a resultados.</li>
 </ul>
 <p>Qué ofrecemos:</p>
 <p>Trabajo 100% remoto</p>
 <p>Participación en proyectos innovadores de IA aplicada.</p>
 <p>Entorno dinámico y orientado a la tecnología.</p>
 <p>Oportunidades de crecimiento y desarrollo profesional.</p>
 <p>Flexibilidad y condiciones competitivas según experiencia.</p>
 <p></p>
 <p><br>
   LAUDE apuesta firmemente por la igualdad de trato y la igualdad de oportunidades entre todas las personas en el empleo y la ocupación. Todas las ofertas de empleo se basan en la igualdad y la no discriminación por motivos de sexo, raza, ideología o cualquier otro motivo.</p>
 <p>LAUDE respeta el principio de inclusión en los procedimientos de selección y ofrece a todas las personas candidatas las mismas oportunidades para demostrar sus competencias en igualdad de condiciones, identificando y eliminando barreras y obstáculos que puedan surgir debido a una discapacidad o problema de salud.”</p>
 <p>“Commitment to gender equality: This company is firmly committed to equal treatment and equal opportunities for women and men in employment and occupation. All offers of employment are based on equality and non-discrimination on the basis of sex, race, ideology or any other grounds.</p>
 <p>Commitment to diversity and inclusion: A disability or health problem should not be a barrier to participation in a selection process. LAUDE respects the principle of inclusion in selection procedures and offers all candidates equal opportunities to demonstrate their competencies on equal terms, identifying and removing barriers and obstacles that may arise due to a disability or health problem.”</p>
</div>
<p></p></div>"""