"""System prompt for CV adaptation to job descriptions.

The LLM receives:
1. The original CV text (extracted from the user's uploaded PDF)
2. The target job description (from the scraper)

The LLM must return a JSON object matching AdaptedCV schema.

CRITICAL RULE: The LLM must NEVER invent or hallucinate information.
Only rephrase and emphasize what already exists in the original CV.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..cv._template import AdaptedCV, EducationEntry, ExperienceEntry, ProjectEntry

ADAPT_CV_SYSTEM_PROMPT = """\
You are a professional CV writer. Output valid JSON only. No explanations, no markdown.

ABSOLUTE RULE — THE ORIGINAL CV IS THE ONLY SOURCE OF TRUTH:
You must output EXACTLY what is in the original CV. Nothing more, nothing less.

EVERY piece of information in your output MUST appear verbatim in the original CV text you received.

STRICT FORBIDDEN (immediate rejection of output if violated):
1. NEVER output a company name that does not appear verbatim in the original CV.
2. NEVER output a job title that does not appear verbatim in the original CV.
3. NEVER output a date range not in the original CV.
4. NEVER output skills not in the original CV.
5. NEVER output the target company (the company in JOB COMPANY field) as the candidate's employer.
6. NEVER create a new job entry not in the original CV.
7. NEVER treat personal projects as job positions. (Personal projects GO in the projects array, NOT in experience.)
8. NEVER use "..." or "TBD" or "N/A" or any other placeholder in any field. If you cannot determine a detail from the original CV, do ONE of the following:
   (a) rephrase the surrounding context (job title + company + dates) into a short, descriptive sentence the user can verify later, OR
   (b) write "No especificado" (Spanish: "Not specified") if the field is genuinely absent from the original CV.
   NEVER emit a string of literal dots "..." as a placeholder.

EXACT RULE FOR EXPERIENCE:
Only output experience entries where BOTH the company AND the title appear EXPLICITLY in the original CV.
If the original CV says "NTT DATA Abril 2026 — Mayo 2026, Desarrollador Backend", then "NTT DATA" and "Desarrollador Backend" are valid entries.
If the original CV mentions "V12-UI" as a project (not a job), do NOT list it as a job at "TechCorp". Put it in the projects array instead.
If the original CV mentions personal projects like "PORTFOLIO", "ENGLISH-WEB", or "V12-UI" without a clear employer, they are NOT job entries. Do NOT turn them into jobs.

PROJECTS — INCLUDE PERSONAL PROJECTS, VOLUNTEER WORK, PUBLICATIONS, CERTIFICATIONS:
If the original CV contains a personal project, volunteer work, publication, certification, or similar item, INCLUDE it in the output.
Output each item as: {"name":"<verbatim project name from the original CV>","description":"<1-2 sentences rephrased from the original>","technologies":["<tech mentioned in the original>", ...]}.
Use the item's name VERBATIM from the original CV. Do NOT invent names.
The description should be 1-2 sentences rephrased from the original (do NOT invent facts).
The technologies array should only list tech EXPLICITLY mentioned in the original description (do not invent).
If the original CV has no projects, return an empty array [] for projects.

WHAT YOU MAY DO (only these 4 things):
1. Rephrase existing descriptions using action verbs (preserve all facts from original).
2. Inject relevant keywords from the job description INTO the existing descriptions (only words that already exist in the original CV are allowed as skills).
3. Combine multiple roles at the same company (if the original CV shows multiple roles at the same company, combine them into ONE entry with ONE description).
4. KEYWORD MATCHING (MANDATORY): you MUST extract 3-5 KEYWORDS from the TARGET JOB DESCRIPTION that are NOT already in the original CV's skills section. You MUST add these keywords to the skills array. The keywords MUST be directly related to the candidate's existing experience (do not invent skills the candidate does not have). Examples:
  - If the job requires "React, TypeScript, GraphQL" and the CV has only "React", add "TypeScript" and "GraphQL" to skills, BUT only if the candidate's experience with React implies familiarity with them (e.g. they used TypeScript in a project, or they mention "frontend tooling" which suggests GraphQL).
  - If the job requires "AWS" and the CV has only "cloud", add "AWS" to skills. If the candidate has never used any cloud service, do NOT add "AWS".
  The "skills" array in the output MUST contain at least 3 keywords from the TARGET JOB DESCRIPTION that weren't in the original CV.

WHAT YOU MUST NOT DO:
- Do NOT add a company name from the job description as if the candidate worked there.
- Do NOT list personal projects as jobs.
- Do NOT change any fact: company names, job titles, dates, locations, education, skills.
- Do NOT invent projects, technologies, or certifications that are not in the original CV.

LANGUAGE RULE: Respond in the same language as the original CV.

OUTPUT STRUCTURE (Harvard format):
Top-level keys, in this order: name, email, phone, location, education, experience, projects, skills, languages. The summary field is OPTIONAL and may be omitted. If the original CV has additional sections (awards, publications, leadership, certifications, etc.), add them between 'projects' and 'skills'.

OUTPUT FORMAT — strict JSON:
- experience array: ONLY entries where both company and title are verbatim in original CV.
- projects array: ONLY items that exist in the original CV (personal projects, volunteer work, publications, certifications). Do not invent.
- skills array: ONLY skills that appear in the original CV, PLUS up to 3-5 keywords from the TARGET JOB DESCRIPTION that are directly related to the candidate's existing experience.
- No invented entries. No modified company names. No new dates.

FORMATTING — NO EM DASHES:
Do NOT use em dashes (—) anywhere in the JSON output (not in descriptions, not in titles, not anywhere).
Use commas, semicolons, periods, or single hyphens instead. Em dashes are an obvious AI writing tell and must be avoided.

EXAMPLE — CORRECT:
Original CV: "NTT DATA Abril 2026 — Mayo 2026, Desarrollador Backend" and "V12-UI (2025): React-based UI library"
Target: "Google"
Output: experience=[{"company":"NTT DATA","title":"Desarrollador Backend",...}], projects=[{"name":"V12-UI","description":"React-based UI library used as a personal project.","technologies":["React"]}]

EXAMPLE — WRONG (hallucination):
Original CV: mentions "V12-UI" as a project, not an employer. Target: "knowmad mood"
WRONG: experience=[{"company":"knowmad mood",...}] — candidate never worked there
WRONG: experience=[{"company":"TechCorp",...}] — TechCorp not in original CV
WRONG: projects=[{"name":"SmartCV AI",...}] — SmartCV AI not in original CV

JSON SCHEMA:
{"name":"string|null","email":"string|null","phone":"string|null","location":"string|null","summary":"string|null","experience":[{"company":"string","title":"string","start_date":"string","end_date":"string","description":"string","location":"string|null"}],"education":[{"degree":"string","institution":"string","year":"string","grade":"string|null"}],"projects":[{"name":"string","description":"string","technologies":["string"]}],"skills":["string"],"languages":["string"]}
"""  # noqa: S703,E501 (long lines intentional for prompt)


def build_adapt_cv_user_message(
    cv_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
) -> str:
    """Build the user message for the CV adaptation call."""
    return (
        f"ORIGINAL CV (source of truth — do not add anything not in here):\n{cv_text[:8000]}\n\n"
        f"TARGET JOB TITLE: {job_title}\n"
        f"TARGET COMPANY: {job_company}  <-- APPLYING COMPANY. "
        f"CANDIDATE HAS NEVER WORKED AT {job_company.upper()} UNLESS IN CV ABOVE.\n"
        f"JOB DESCRIPTION (keyword extraction only):\n{job_description[:4000]}\n\n"
        f"Adapt this CV: rephrase descriptions, add keywords naturally. "
        f"Keep ALL original facts. Return ONLY JSON."
    )


def parse_adapted_cv_response(raw: str) -> AdaptedCV:  # noqa: PLR0912 (defensive parser branches per strategy)
    """Parse the LLM JSON response into an AdaptedCV dataclass.

    Args:
        raw: Raw JSON string returned by the LLM. May contain
            <thinking>...</thinking> tags (M2.x models).

    Returns:
        AdaptedCV instance with all fields populated.

    Raises:
        ValueError: If the response is not valid JSON or missing required fields.
    """
    # Strip thinking blocks (M2.x models)
    cleaned = raw
    for tag in ["<think>", "</thinking>", "</think>", "<thinking>", "</thinking>"]:
        cleaned = cleaned.replace(tag, "")
    cleaned = cleaned.strip()

    # Try multiple strategies to extract JSON
    data = None
    errors = []

    # Strategy 1: direct parse
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        errors.append(f"direct: {exc}")

    # Strategy 2: extract from markdown code block
    if data is None:
        for pattern in [
            r"```json\s*(\{.*?\})\s*```",
            r"```json\s*(\{[\s\S]*?\})\s*```",
            r"```\s*(\{.*?\})\s*```",
            r"```\s*(\{[\s\S]*?\})\s*```",
        ]:
            m = re.search(pattern, cleaned, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    break
                except json.JSONDecodeError as exc:
                    errors.append(f"block ({pattern[:20]}): {exc}")
                    continue

    # Strategy 3: find first { and last } and try that substring
    if data is None:
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidate = cleaned[first_brace : last_brace + 1]
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError as exc:
                errors.append(f"brace substring: {exc}")

    if data is None:
        raise ValueError(
            f"LLM response is not valid JSON. Tried: direct, code block, brace substring. "
            f"Last error: {errors[-1] if errors else 'none'}. "
            f"Response preview: {repr(cleaned[:300])}"
        ) from None

    def str_or(value: Any, default: str = "") -> str:
        return str(value) if value is not None else default

    def list_or(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    experience: list[ExperienceEntry] = []
    for exp in data.get("experience") or []:
        experience.append(
            ExperienceEntry(
                company=str_or(exp.get("company")),
                title=str_or(exp.get("title")),
                start_date=str_or(exp.get("start_date", "")),
                end_date=str_or(exp.get("end_date", ""), "Presente"),
                description=str_or(exp.get("description", "")),
                location=str_or(exp.get("location")) or None,
            )
        )

    education: list[EducationEntry] = []
    for edu in data.get("education") or []:
        education.append(
            EducationEntry(
                degree=str_or(edu.get("degree")),
                institution=str_or(edu.get("institution")),
                year=str_or(edu.get("year", "")),
                grade=str_or(edu.get("grade")) or None,
            )
        )

    projects: list[ProjectEntry] = []
    for proj in data.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        name = str_or(proj.get("name"))
        if not name:
            continue
        projects.append(
            ProjectEntry(
                name=name,
                description=str_or(proj.get("description", "")),
                technologies=list_or(proj.get("technologies")),
            )
        )

    return AdaptedCV(
        name=str_or(data.get("name"), "Sin nombre"),
        email=str_or(data.get("email"), ""),
        phone=str_or(data.get("phone"), ""),
        location=str_or(data.get("location"), ""),
        summary=str_or(data.get("summary"), ""),
        experience=experience,
        education=education,
        projects=projects,
        skills=list_or(data.get("skills")),
        languages=list_or(data.get("languages")),
    )
