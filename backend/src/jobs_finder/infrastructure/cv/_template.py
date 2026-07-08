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

import re
from dataclasses import dataclass, field
from html import escape as _html_escape
from urllib.parse import urlparse


def derive_chip_label(url: str) -> str:
    """Derive a short, human-readable chip label from a URL.

    Algorithm (per design §1.1):
      1. If the URL is unparseable, return "" (never raise).
      2. Lowercase the hostname; strip a leading "www.".
      3. Look the hostname up in a KNOWN platform map.
      4. If not in the map, return the first label of the hostname,
         capitalized (e.g. "user.example.com" → "User").
      5. http:// and https:// are equivalent — the scheme doesn't
         change the label.

    Used by the parser (legacy `url` → synthesized single-link) and
    the renderer (chip fallback when the LLM emits an empty label).
    """
    if not url:
        return ""
    try:
        host = (urlparse(url).netloc or "").lower()
    except (ValueError, TypeError):
        return ""
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    # Map of well-known code-forge / package-registry / media hosts to
    # their brand-spelling label. Hostname is matched after the www.
    # strip so https://www.github.com and https://github.com both
    # resolve to "GitHub".
    known = {
        "github.com": "GitHub",
        "gitlab.com": "GitLab",
        "bitbucket.org": "Bitbucket",
        "npmjs.com": "npm",
        "npmjs.org": "npm",
        "storybook.js.org": "Storybook",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "linkedin.com": "LinkedIn",
        "medium.com": "Medium",
        "dev.to": "DEV",
    }
    if host in known:
        return known[host]
    # First label of the hostname, capitalized. Handles
    # "user.example.com" → "User" and "docs.example.com" → "Docs".
    first_label = host.split(".")[0]
    return first_label.capitalize() if first_label else ""


@dataclass
class ProjectLink:
    """A single labeled external link attached to a project.

    Multiple `ProjectLink`s per project (e.g. GitHub + Storybook +
    npm) are rendered as independently-clickable chips in BOTH
    renderers (Python HTML + TS PDF).

    `url` may be an empty string when the original CV's PDF has a
    visual label (e.g. "Github link") but no real hyperlink annotation
    pointing to a URL — in that case the renderer draws a label-only
    chip (not clickable) so the user still SEES the link exists in
    the original CV, even though no URL target is available.

    Mirrors `frontend/src/lib/llm/prompts.ts` `AdaptedCVProjectLink`.
    """

    label: str
    url: str = ""


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

    The `links` field holds the multi-link chip data the renderer
    iterates over (one `<a>` / `drawLinkAnnotation` per link). The
    legacy `url` field is retained for backward compatibility with
    any LLM output that still emits the singular URL shape — the
    parser synthesizes a one-entry `links` from it on the way in
    (see `parse_adapted_cv_response`).
    """

    name: str
    description: str = ""
    technologies: list[str] = field(default_factory=list)
    url: str | None = None
    links: list[ProjectLink] = field(default_factory=list)


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
    certifications: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    photo_base64: str | None = None

    def to_html(self) -> str:
        """Render the CV as a full HTML document."""
        skills_section = self._render_skills()
        experience_section = self._render_experience()
        education_section = self._render_education()
        projects_section = self._render_projects()
        certifications_section = self._render_certifications()

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

  a {{
    color: inherit;
    text-decoration: none;
  }}

  a::after {{
    content: none;
  }}

  /* Project-name anchor: scoped so chip anchors below can keep
     their own visible affordance (border + fill). Without scoping,
     the bare `a` selector at the top of the stylesheet would also
     match `.project-link-chip` and hide the chip's border. */
  .project-name a {{
    color: inherit;
    text-decoration: none;
  }}

  /* Project link chips — one per `ProjectLink` in the project's
     `links[]` array. Each chip is its own clickable region in the
     rendered PDF/HTML (REQ-PJL-003). The border + subtle fill is
     the visual affordance that says "this is clickable"; the chip
     text is the link label. */
  .project-links-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 4pt;
    margin: 3pt 0 4pt 0;
  }}

  .project-link-chip {{
    display: inline-block;
    padding: 1pt 6pt;
    border: 0.5pt solid #888;
    background-color: #f4f4f4;
    border-radius: 8pt;
    font-size: 8pt;
    font-style: italic;
    color: #000;
    text-decoration: none;
    line-height: 1.4;
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

{certifications_section}

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
            exp_desc_html = exp.description
            if exp.description:
                exp_desc_html = re.sub(
                    r"(https?://[^\s]+)",
                    r'<a href="\1">\1</a>',
                    exp.description,
                )
            items += f"""
<div class="experience-item">
  <div class="exp-header">
    <span class="exp-company">{exp.company}</span>
    <span class="exp-date">{exp.start_date} – {exp.end_date}</span>
  </div>
  <div class="exp-title">{exp.title}{location_html}</div>
  <div class="exp-description">{exp_desc_html}</div>
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
            desc_html = ""
            if proj.description:
                # Auto-link any HTTP/HTTPS URLs in the description text
                # (preserved per spec REQ-PJL-007 — handles accidental
                # bare URLs in the body that the LLM copies verbatim).
                linked_desc = re.sub(
                    r"(https?://[^\s]+)",
                    r'<a href="\1">\1</a>',
                    proj.description,
                )
                desc_html = f"<div class='project-description'>{linked_desc}</div>"

            # Resolve the per-project link set, in priority order:
            #   1. `proj.links[]` if non-empty (the new shape).
            #   2. Synthesize a single link from legacy `proj.url`
            #      (so a `ProjectEntry` constructed without going
            #      through the parser still renders a chip).
            #   3. Empty list — no chip row.
            effective_links: list[ProjectLink] = list(proj.links)
            if not effective_links and proj.url:
                effective_links = [ProjectLink(label=derive_chip_label(proj.url), url=proj.url)]

            # Project-name anchor uses the first link's URL (or
            # legacy `url`) — the "primary" link. The chip row
            # below carries every link as its own clickable region
            # (REQ-PJL-003).
            primary_url = effective_links[0].url if effective_links else None
            name_html = f'<a href="{primary_url}">{proj.name}</a>' if primary_url else proj.name

            chip_html = ""
            if effective_links:
                chip_items = "".join(
                    # Clickable chip when URL is non-empty, label-only
                    # span when URL is empty (the original CV had a
                    # visual label but no real hyperlink annotation).
                    f'<a class="project-link-chip" href="{link.url}">'
                    f"{_html_escape(link.label) or _html_escape(link.url)}"
                    f"</a>"
                    if link.url
                    else f'<span class="project-link-chip project-link-chip--no-url">'
                    f"{_html_escape(link.label)}"
                    f"</span>"
                    for link in effective_links
                )
                chip_html = f'<div class="project-links-row">{chip_items}</div>'

            items += f"""
<div class="project-item">
  <div class="project-name">{name_html}</div>
  {chip_html}
  {desc_html}
  {tech_html}
</div>"""
        return (
            f'<div class="section">'
            f'<div class="section-title">Proyectos Personales</div>'
            f"{items}</div>"
        )

    def _render_certifications(self) -> str:
        # Mirrors the TypeScript renderer's 'Certificaciones' section.
        # Items come from a 'Certificaciones' / 'Certificaciones y
        # Competencias' / 'Licencias' section in the original CV —
        # licenses, courses, and training programs.
        if not self.certifications:
            return ""
        items = "".join(f"<div class='cert-item'>• {cert}</div>" for cert in self.certifications)
        return f'<div class="section"><div class="section-title">Certificaciones</div>{items}</div>'

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
