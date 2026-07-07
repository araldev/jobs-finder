"""HTML template for the adapted CV in Harvard/ATS-friendly format.

Design principles:
- Sans-serif font (Arial or Liberation Sans) — standard in ATS systems
- Black text on white background — maximum readability
- Clear section headers with bold — scannable by algorithms
- No tables, no graphics, no columns — ATS parsers struggle with these
- Contact info always at top in a single line
- Consistent spacing and margins (A4)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExperienceEntry:
    """A single work experience entry."""

    company: str
    title: str
    start_date: str
    end_date: str  # "Presente" or a date
    description: str
    location: str | None = None


@dataclass
class EducationEntry:
    """A single education entry."""

    degree: str
    institution: str
    year: str
    grade: str | None = None


@dataclass
class ProjectEntry:
    """A single personal project / volunteer / publication / certification entry.

    Mirrors `frontend/src/lib/llm/prompts.ts` `AdaptedCVProject`. The LLM
    uses this to surface items from the original CV that don't fit the
    `ExperienceEntry` shape (personal projects, open-source contributions,
    certifications, etc.).
    """

    name: str
    description: str = ""
    technologies: list[str] = field(default_factory=list)


@dataclass
class AdaptedCV:
    """Structured adapted CV ready for rendering."""

    name: str
    email: str
    phone: str
    location: str
    summary: str  # Professional summary, 2-3 sentences
    experience: list[ExperienceEntry] = field(default_factory=list)
    education: list[EducationEntry] = field(default_factory=list)
    projects: list[ProjectEntry] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    photo_base64: str | None = None

    def to_html(self) -> str:
        """Render the CV as a full HTML document."""
        skills_section = self._render_skills()
        experience_section = self._render_experience()
        education_section = self._render_education()
        projects_section = self._render_projects()

        photo_html = ""
        if self.photo_base64:
            photo_html = f"""
            <img src="{self.photo_base64}"
                 alt="Foto"
                 class="photo" />
            """

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<title>{self.name} - CV</title>
<style>
  @page {{
    size: A4;
    margin: 15mm 15mm 15mm 20mm;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: Arial, "Liberation Sans", Helvetica, sans-serif;
    font-size: 10pt;
    line-height: 1.4;
    color: #111;
    background: #fff;
  }}

  .header {{
    display: flex;
    align-items: flex-start;
    gap: 12pt;
    padding-bottom: 8pt;
    border-bottom: 1pt solid #222;
    margin-bottom: 10pt;
  }}

  .header-text {{
    flex: 1;
  }}

  h1 {{
    font-size: 18pt;
    font-weight: bold;
    letter-spacing: 0.5pt;
    margin-bottom: 3pt;
  }}

  .contact-line {{
    font-size: 9pt;
    color: #333;
  }}

  .contact-line span {{
    margin-right: 10pt;
  }}

  .photo {{
    width: 28mm;
    height: 32mm;
    object-fit: cover;
    border-radius: 2pt;
    border: 0.5pt solid #ccc;
    flex-shrink: 0;
  }}

  .section {{
    margin-bottom: 8pt;
  }}

  .section-title {{
    font-size: 10pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
    color: #000;
    border-bottom: 0.5pt solid #888;
    padding-bottom: 2pt;
    margin-bottom: 5pt;
  }}

  .summary {{
    font-size: 9.5pt;
    color: #222;
    line-height: 1.45;
  }}

  .experience-item {{
    margin-bottom: 7pt;
    page-break-inside: avoid;
  }}

  .exp-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 1pt;
  }}

  .exp-company {{
    font-weight: bold;
    font-size: 10pt;
  }}

  .exp-date {{
    font-size: 9pt;
    color: #555;
  }}

  .exp-title {{
    font-size: 9.5pt;
    color: #333;
    font-style: italic;
    margin-bottom: 2pt;
  }}

  .exp-location {{
    font-size: 9pt;
    color: #666;
  }}

  .exp-description {{
    font-size: 9pt;
    color: #222;
    line-height: 1.4;
    margin-top: 2pt;
  }}

  .project-item {{
    margin-bottom: 6pt;
    page-break-inside: avoid;
  }}

  .project-name {{
    font-weight: bold;
    font-size: 10pt;
  }}

  .project-description {{
    font-size: 9pt;
    color: #222;
    line-height: 1.4;
    margin-top: 1pt;
  }}

  .project-tech {{
    font-size: 9pt;
    color: #555;
    margin-top: 1pt;
  }}

  .edu-item {{
    margin-bottom: 5pt;
    page-break-inside: avoid;
  }}

  .edu-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}

  .edu-degree {{
    font-weight: bold;
    font-size: 10pt;
  }}

  .edu-year {{
    font-size: 9pt;
    color: #555;
  }}

  .edu-institution {{
    font-size: 9pt;
    color: #333;
  }}

  .skills-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 3pt 8pt;
  }}

  .skill-tag {{
    font-size: 9pt;
    color: #222;
  }}

  .skill-tag strong {{
    font-weight: bold;
  }}

  .languages-list {{
    font-size: 9pt;
    color: #222;
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-text">
    <h1>{self.name}</h1>
    <div class="contact-line">
      <span>📧 {self.email}</span>
      <span>📱 {self.phone}</span>
      <span>📍 {self.location}</span>
    </div>
  </div>
  {photo_html}
</div>

<div class="section">
  <div class="section-title">Perfil Profesional</div>
  <p class="summary">{self.summary}</p>
</div>

<div class="section">
  <div class="section-title">Educación</div>
  {education_section}
</div>

{experience_section}

{projects_section}

{skills_section}

</body>
</html>"""  # noqa: S703 (line length intentional for HTML template)

    def _render_experience(self) -> str:
        if not self.experience:
            return ""
        items = ""
        for exp in self.experience:
            location_html = (
                f', <span class="exp-location">{exp.location}</span>' if exp.location else ""
            )
            items += f"""
<div class="experience-item">
  <div class="exp-header">
    <span class="exp-company">{exp.company}</span>
    <span class="exp-date">{exp.start_date} – {exp.end_date}</span>
  </div>
  <div class="exp-title">{exp.title}{location_html}</div>
  <div class="exp-description">{exp.description}</div>
</div>"""
        return (
            f'<div class="section">'
            f'<div class="section-title">Experiencia Profesional</div>'
            f"{items}</div>"
        )

    def _render_education(self) -> str:
        if not self.education:
            return ""
        items = ""
        for edu in self.education:
            grade_html = f", {edu.grade}" if edu.grade else ""
            items += f"""
<div class="edu-item">
  <div class="edu-header">
    <span class="edu-degree">{edu.degree}{grade_html}</span>
    <span class="edu-year">{edu.year}</span>
  </div>
  <div class="edu-institution">{edu.institution}</div>
</div>"""
        return items

    def _render_projects(self) -> str:
        if not self.projects:
            return ""
        items = ""
        for proj in self.projects:
            tech_html = (
                f"<div class='project-tech'>Tecnologías: {', '.join(proj.technologies)}</div>"
                if proj.technologies
                else ""
            )
            desc_html = (
                f"<div class='project-description'>{proj.description}</div>"
                if proj.description
                else ""
            )
            items += f"""
<div class="project-item">
  <div class="project-name">{proj.name}</div>
  {desc_html}
  {tech_html}
</div>"""
        return (
            f'<div class="section">'
            f'<div class="section-title">Proyectos Personales</div>'
            f"{items}</div>"
        )

    def _render_skills(self) -> str:
        if not self.skills and not self.languages:
            return ""
        skills_html = ""
        if self.skills:
            tags = " &nbsp;·&nbsp; ".join(
                f"<span class='skill-tag'><strong>{s}</strong></span>" for s in self.skills
            )
            skills_html += f"<div class='skills-grid'>{tags}</div>"
        languages_html = ""
        if self.languages:
            languages_html = (
                f"<div class='languages-list'>"
                f"<strong>Idiomas:</strong> {', '.join(self.languages)}"
                f"</div>"
            )
        return f"""
<div class="section">
  <div class="section-title">Habilidades</div>
  {skills_html}
  {languages_html}
</div>"""
