"""
LinkedIn detail panel HTML fixture.

Captured 2026-06-11 against linkedin.com /jobs/view/4304525450
(a real "Desarrollador Python Junior" job post at Sigma AI).
The panel is the <section class="show-more-less-html"> that
LinkedIn renders on the detail page. The full description lives
inside <div class="show-more-less-html__markup">.

Parser reference: parse_description() in linkedin/parsers.py
(line 166). It accepts either the panel element or its inner
markup div, and returns the text content (with separator=" "
and strip=True).
"""

PANEL_HTML = """\
<section class="show-more-less-html" data-max-lines="5">
        <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5
            relative overflow-hidden">
          <strong>🌟Únete a Sigma.AI – Dando forma al futuro de la Inteligencia Artificial🌍<br><br></strong><strong>🔹 ¿Qué es Sigma?<br><br></strong>Sigma AI es una empresa tecnológica global donde trabajamos para construir una inteligencia artificial más útil, inclusiva y responsable. Colaboramos con algunas de las empresas tecnológicas más innovadoras del mundo, ayudándolas a desarrollar IA a través de datos de alta calidad y procesos sólidos. Llevamos más de 30 años en el sector, con oficinas en España, Estados Unidos y Reino Unido trabajando con más de 600 idiomas.<br><br><strong>💼 ¿Qué harás en este rol?<br><br></strong>Estamos buscando a alguien que sea capaz de entender procesos de trabajo y tenga la capacidad de plantear posibles mejoras realizando automatizaciones.<br><br>Para realizar dichas automatizaciones, se necesita una mínima experiencia desarrollando scripts en Python, usar herramientas como RPAs para automatizar sobre herramientas web y ser capaz de procesar y analizar datos. Todo ello en entornos de servidores Linux.<br><br><strong>✅Requisitos generales<br><br></strong><ul><li>Mínimo 2 años de experiencia en roles de desarrollador de Python.</li><li>Conocimientos en Pandas.</li><li>Conocimiento y experiencia en Selenium o alguna otra herramienta de automatización web. Idealmente conocer el RPA de Rocketbot</li><li>Experiencia básica en Linux.</li><li>Nivel de inglés intermedio o superior (para leer documentación y colaborar con equipos internacionales).<br><br></li></ul><strong>👍Tus principales responsabilidades serán:<br><br></strong><ul><li>Escribir y mantener scripts en Python para automatizar procesos.</li><li>Utilizar Selenium para interactuar con páginas web (por ejemplo, para hacer scraping o automatizar tareas repetitivas).</li><li>Mantener y desarrollar nuevos automatismos sobre procesos de trabajo con Rocketbot.</li><li>Trabajar con Pandas para analizar y transformar datos.</li><li>Ejecutar scripts en servidores Linux (por ejemplo, conectarte por terminal y lanzar un script).</li><li>Colaborar con el equipo en proyectos que combinan automatización y análisis de datos.<br><br></li></ul><strong>Adicionales:<br><br></strong><ul><li>MATLAB (aunque no es obligatorio).</li><li>Proyectos de scraping o automatización de tareas.</li><li>Conocimiento de Zapier (no obligatorio)</li><li>Power BI<br><br></li></ul>🚫 <strong>Notas Importantes:<br><br></strong>Sigma.AI no contrata a través de terceros. Ningún agente, intermediario o tercero está autorizado para representar, beneficiarse o participar de ninguna manera en esta relación. En este sentido, el candidato acepta proporcionar cualquier documentación o información que la empresa solicite razonablemente para verificar su identidad y credenciales. Si el candidato no proporciona pruebas suficientes de su identidad a satisfacción de Sigma, la empresa podrá retener o cancelar cualquier oferta hecha al candidato.<br><br>La empresa puede utilizar o apoyarse en sistemas de inteligencia artificial en sus procesos de selección. Dicho procesamiento se realiza de manera ética, transparente y conforme a la ley. El propósito es evaluar las pruebas enviadas durante el proceso de selección (por ejemplo, el contenido transcrito proporcionado por el candidato). La base legal para procesar tus datos es la relación precontractual entre las partes y/o la prestación de los servicios solicitados.<br><br>💬 <strong>¿Necesitas Ayuda?<br><br></strong>Estamos aquí para resolver cualquier duda o inquietud.<br><br>Únete a nosotros y forma parte de algo global, innovador e impactante.<br><br><strong>Sigma.AI – Datos bien hechos.</strong>
        </div>

        

    
    
    

    <button class="show-more-less-html__button show-more-less-button
        show-more-less-html__button--more
        ml-0.5" data-tracking-control-name="public_jobs_show-more-html-btn" aria-label="Show more" aria-expanded="false">
<!---->
        
            Show more
          

          <icon class="show-more-less-html__button-icon show-more-less-button-icon lazy-loaded" aria-hidden="true" aria-busy="false"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" preserveAspectRatio="xMinYMin meet" focusable="false" class="lazy-loaded" aria-busy="false"><path d="M8 9l5.93-4L15 6.54l-6.15 4.2a1.5 1.5 0 01-1.69 0L1 6.54 2.07 5z" fill="currentColor"></path></svg></icon>
    </button>
  

        

    
    
    

    <button class="show-more-less-html__button show-more-less-button
        show-more-less-html__button--less
        ml-0.5" data-tracking-control-name="public_jobs_show-less-html-btn" aria-label="Show less" aria-expanded="true">
<!---->
        
            Show less
          

          <icon class="show-more-less-html__button-icon show-more-less-button-icon lazy-loaded" aria-hidden="true" aria-busy="false"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" preserveAspectRatio="xMinYMin meet" focusable="false" class="lazy-loaded" aria-busy="false"><path d="M8 7l-5.9 4L1 9.5l6.2-4.2c.5-.3 1.2-.3 1.7 0L15 9.5 13.9 11 8 7z" fill="currentColor"></path></svg></icon>
    </button>
  
<!---->    </section>
"""
