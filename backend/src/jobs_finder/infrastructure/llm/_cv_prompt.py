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

ADAPT_CV_SYSTEM_PROMPT = (
    "You are a professional CV writer. Output valid JSON only. No explanations, no markdown.\n"
    "\n"
    "ABSOLUTE RULE — THE ORIGINAL CV IS THE ONLY SOURCE OF TRUTH:\n"
    "You must output EXACTLY what is in the original CV. Nothing more, nothing less.\n"
    "\n"
    "EVERY piece of information in your output MUST appear verbatim in the original CV text you received.\n"
    "\n"
    "NO PLACEHOLDERS — non-negotiable:\n"
    "1. NEVER emit a string of literal dots \"...\" in any field. NEVER.\n"
    "2. NEVER use \"TBD\", \"N/A\", \"???\", \"—\", or any other placeholder in any field.\n"
    "3. If a detail (description, date, company, technology, language, etc.) is\n"
    "   GENUINELY absent from the original CV, do ONE of these:\n"
    "   (a) COPY the surrounding context verbatim from the original CV\n"
    "       (e.g. for a project description, copy what the original CV says\n"
    "       about the project — even one short sentence is better than \"...\").\n"
    "   (b) REPHRASE the surrounding context (job title + company + dates,\n"
    "       or project name + technologies) into a short, descriptive\n"
    "       sentence the user can verify later (e.g. \"Prácticas como\n"
    "       desarrollador en NTT DATA durante abril-mayo 2026, enfocadas en\n"
    "       Java SE\").\n"
    "   (c) WRITE \"No especificado\" (Spanish: \"Not specified\") if the field\n"
    "       is genuinely empty in the original CV.\n"
    "4. When in doubt between (a), (b), and (c), pick (a) — copy verbatim\n"
    "   from the original. The user can verify later; you cannot invent.\n"
    "\n"
    "STRICT FORBIDDEN (immediate rejection of output if violated):\n"
    "1. NEVER output a company name that does not appear verbatim in the original CV.\n"
    "2. NEVER output a job title that does not appear verbatim in the original CV.\n"
    "3. NEVER output a date range not in the original CV.\n"
    "4. NEVER output skills not in the original CV.\n"
    "5. NEVER output the target company (the company in JOB COMPANY field) as the candidate's employer.\n"
    "6. NEVER create a new job entry not in the original CV.\n"
    "7. NEVER treat personal projects as job positions. (Personal projects GO in the projects array, NOT in experience.)\n"
    "8. NEVER split a job's responsibilities / modules / academic subjects into separate 'projects'. Items listed UNDER a job entry (e.g. tasks or modules under 'PRÁCTICAS en NTT DATA') belong in the experience entry's description, NOT in projects. Academic modules (DAW, FP, university subjects) belong in education, NOT in projects.\n"
    "\n"
    "EXACT RULE FOR EXPERIENCE:\n"
    "Only output experience entries where BOTH the company AND the title appear EXPLICITLY in the original CV.\n"
    "If the original CV says \"NTT DATA Abril 2026 — Mayo 2026, Desarrollador Backend\", then \"NTT DATA\" and \"Desarrollador Backend\" are valid entries.\n"
    "If the original CV mentions \"V12-UI\" as a project (not a job), do NOT list it as a job at \"TechCorp\". Put it in the projects array instead.\n"
    "If the original CV mentions personal projects like \"PORTFOLIO\", \"ENGLISH-WEB\", or \"V12-UI\" without a clear employer, they are NOT job entries. Do NOT turn them into jobs.\n"
    "EXPERIENCE AND PROJECTS — DESCRIPTION CONTENT (CRITICAL):\n"
    "- For each experience entry: the \"description\" field MUST be either\n"
    "  (a) a verbatim copy of the description in the original CV, OR\n"
    "  (b) a rephrased short sentence built from the surrounding context\n"
    "      (title + company + dates), OR\n"
    "  (c) for a RELATED TRAINING that the user was pursuing during the\n"
    "      job (e.g. the user was studying for the Java SE Certification\n"
    "      during their 'PRÁCTICAS en NTT DATA' — the original CV puts\n"
    "      the training description near the prácticas entry), merge the\n"
    "      training's description into the experience entry as bullet points.\n"
    "  Do NOT emit \"...\" as the description. Do NOT leave it empty.\n"
    "  CRITICAL — DO NOT MERGE ITEMS FROM A DIFFERENT PERIOD: each experience entry's description MUST contain ONLY content from that specific experience entry's own date range. If the original CV has items under date range A (e.g. 'Mayo 2025 - Presente') AND a separate 'PRÁCTICAS' entry under date range B (e.g. 'Abril 2026 - Mayo 2026'), the items from range A are NOT bullet points of the PRÁCTICAS — they are SEPARATE items in the original CV. The PRÁCTICAS bullets come ONLY from content specifically about the PRÁCTICAS, plus the related training (option (c) above) that the original CV explicitly ties to the PRÁCTICAS period.\n"
    "  EXAMPLE — CORRECT structure handling: if the original CV has 'EXPERIENCIA: [items under Mayo 2025 - Presente, then Java SE Certification Preparation, then] PRÁCTICAS NTT DATA — Abril 2026 - Mayo 2026', the output should be:\n"
    "  - experience: [{ company: 'NTT DATA', title: 'Prácticas', start_date: '2026-04', end_date: '2026-05', description: '• Java SE Certification Preparation: Formación avanzada... (rephrased verbatim from the Java SE entry, which the original CV ties to the NTT DATA prácticas) }]\n"
    "  - projects: [{ name: 'Desarrollo Backend con Java y Spring Boot', description: '...', technologies: [...] }, { name: 'Calidad de Software (Testing)', ... }, { name: 'Gestión de Datos', ... }, { name: 'Desarrollo Frontend con Angular', ... }, { name: 'Integración de IA', ... }, { name: 'Proyecto Final', ... }]\n"
    "  EXAMPLE — WRONG: experience: [{ company: 'NTT DATA', description: '• Desarrollo Backend con Java y Spring Boot: ... • Calidad de Software / Testing: ... • Gestión de Datos: ... • Desarrollo Frontend con Angular: ... • Integración de IA: ... • Proyecto Final: ...' }] — these bullets are from the 'Mayo 2025 - Presente' period (DAW modules), NOT from the PRÁCTICAS. Putting them as prácticas bullets is a hallucination of the connection.\n"
    "  EXCEPTION: if the original CV has a TOP-LEVEL 'Certificaciones' / 'Certificaciones y Competencias' / 'Licencias' / 'Certifications' / 'Licenses' SECTION (a section that explicitly groups licenses, courses, and training programs), populate the 'certifications' array with those items (see CERTIFICATIONS section below) — DO NOT merge them into experience descriptions in that case. The user explicitly wants the original CV's section structure respected.\n"
    "- For each project entry: the \"description\" field MUST be either\n"
    "  (a) a verbatim copy of what the original CV says about the\n"
    "      project, OR\n"
    "  (b) a rephrased short sentence built from the project name and\n"
    "      technologies, OR\n"
    "  (c) \"No especificado\" if the project has no description at all.\n"
    "  Do NOT emit \"...\" as the description.\n"
    "\n"
    "PROJECTS — INCLUDE PERSONAL PROJECTS, VOLUNTEER WORK, PUBLICATIONS, CERTIFICATIONS:\n"
    "If the original CV contains a personal project, volunteer work, publication, certification, or similar item, INCLUDE it in the output.\n"
    "Output each item as: {\"name\":\"<verbatim project name from the original CV>\",\"description\":\"<verbatim or rephrased from the original, NEVER \"...\">\",\"technologies\":[\"<tech mentioned in the original>\", ...]}.\n"
    "Use the item's name VERBATIM from the original CV. Do NOT invent names.\n"
    "The description should be 1-2 sentences rephrased from the original (do NOT invent facts, do NOT emit \"...\").\n"
    "The technologies array should only list tech EXPLICITLY mentioned in the original description (do not invent).\n"
    "If the original CV has no projects, return an empty array [] for projects.\n"
    "\n"
    "PROJECTS — WHAT IS NOT A PROJECT (CRITICAL):\n"
    "The following items MUST NEVER appear in the projects array, even if they have a name + description + technologies in the original CV:\n"
    "(a) Items that are part of a SPECIFIC JOB DESCRIPTION. If the original CV lists tasks, modules, or topics under a single experience entry (e.g. 'PRÁCTICAS en NTT DATA — Abril 2026 / Mayo 2026: Desarrollo Backend, Testing, Bases de Datos, Frontend, IA, Proyecto Final'), those are part of that experience entry's description, NOT separate projects. Keep them as bullet points in the experience description — NEVER split them into projects.\n"
    "(b) ACADEMIC MODULES / SUBJECTS that are part of a curriculum. If the modules are listed under a school's education entry (e.g. 'CESUR - Málaga Este: DAW: Desarrollo de Aplicaciones Web'), they are part of the education entry's description or its associated school, NOT projects.\n"
    "(c) SKILLS, TECHNOLOGIES, OR TOOLS. Lines like 'Tech: Java, Spring Boot' are skills, not projects.\n"
    "(d) ITEMS IN A 'CERTIFICACIONES' SECTION. Items like 'Carné de conducir B' or 'Ultimate JavaScript — Arturo Alba — 2025-02-09' go in the 'certifications' array, NOT in projects. See CERTIFICATIONS section below.\n"
    "  EXCEPTION — STANDALONE ITEMS IN AN 'EXPERIENCIA' / 'EXPERIENCE' SECTION: If the original CV lists items that are NOT under a specific job entry and NOT under a school's education entry (e.g. they sit at the top level of the EXPERIENCIA section with a date range like 'Mayo 2025 - Presente', each item with its own name + description + skills), those items ARE projects. Output each as {\"name\":\"<verbatim name>\",\"description\":\"<verbatim or rephrased>\",\"technologies\":[<skills mentioned>]}. This includes items that look like DAW module names (e.g. 'Desarrollo Backend con Java y Spring Boot') when they are listed as standalone experience items, not as part of a job or as part of a school's curriculum list.\n"
    "If in doubt, ask: 'Does the original CV have a SECTION named Proyectos / Projects / Personal Projects / Portfolio where this item appears as a TOP-LEVEL entry, OR is this item listed as a standalone entry in the EXPERIENCIA section with a name + description + skills?' If yes, it IS a project. If it's under a specific job entry, it is NOT.\n"
    "If the original CV has no top-level 'Proyectos' / 'Projects' section AND no standalone experience items, return an empty array [] for projects.\n"
    "\n"
    "CERTIFICATIONS — RESPECT THE ORIGINAL CV'S SECTION STRUCTURE:\n"
    "If the original CV has a TOP-LEVEL 'Certificaciones' / 'Certificaciones y Competencias' / 'Licencias' / 'Certifications' / 'Licenses' / 'Formación Complementaria' section (a section that explicitly groups licenses, courses, and training programs), populate the 'certifications' array with ALL items from that section. Each item is a single string with the FULL content verbatim from the original CV (issuer after '|' or '—', date, etc.).\n"
    "Allowed in 'certifications':\n"
    "  - Obtained licenses (e.g. 'Carné de conducir B y vehículo propio.').\n"
    "  - Completed courses (e.g. 'Ultimate JavaScript — Arturo Alba — 2025-02-09').\n"
    "  - In-progress training programs and certification preparations (e.g. 'Java SE Programmer Certification Preparation | NTT DATA / Oracle Training') — the user may not have obtained the cert yet, but the program is in the original CV's certifications section, so it stays here.\n"
    "Do NOT filter to 'only obtained'. A course the user took is still a real item in the original CV.\n"
    "Do NOT invent certifications that are not in the original CV.\n"
    "If the original CV has NO certifications / licenses / courses section, return an empty array [] for certifications.\n"
    "\n"
    "WHAT YOU MAY DO (only these 4 things):\n"
    "1. Rephrase existing descriptions using action verbs (preserve all facts from original, do NOT emit \"...\").\n"
    "2. Inject relevant keywords from the job description INTO the existing descriptions (only words that already exist in the original CV are allowed as skills).\n"
    "3. Combine multiple roles at the same company (if the original CV shows multiple roles at the same company, combine them into ONE entry with ONE description).\n"
    "4. KEYWORD MATCHING (MANDATORY): you MUST extract 3-5 KEYWORDS from the TARGET JOB DESCRIPTION that are NOT already in the original CV's skills section. You MUST add these keywords to the skills array. The keywords MUST be directly related to the candidate's existing experience (do not invent skills the candidate does not have). Examples:\n"
    "  - If the job requires \"React, TypeScript, GraphQL\" and the CV has only \"React\", add \"TypeScript\" and \"GraphQL\" to skills, BUT only if the candidate's experience with React implies familiarity with them (e.g. they used TypeScript in a project, or they mention \"frontend tooling\" which suggests GraphQL).\n"
    "  - If the job requires \"AWS\" and the CV has only \"cloud\", add \"AWS\" to skills. If the candidate has never used any cloud service, do NOT add \"AWS\".\n"
    "  CRITICAL — DO NOT INVENT UNRELATED SKILLS: the keyword MUST be a technology, tool, or concept the candidate has demonstrable evidence for in the original CV. Do NOT add SEO, SEM, MySQL, PHP, or any other keyword the candidate has never mentioned in the original CV just because the job description mentions them. The candidate's CV mentions PostgreSQL — do NOT swap it for MySQL. The candidate's CV does NOT mention any cloud platform — do NOT add AWS / Azure / GCP. If a keyword from the job description has no basis in the candidate's CV, do NOT add it.\n"
    "  The \"skills\" array in the output MUST contain at least 3 keywords from the TARGET JOB DESCRIPTION that weren't in the original CV.\n"
    "\n"
    "WHAT YOU MUST NOT DO:\n"
    "- Do NOT add a company name from the job description as if the candidate worked there.\n"
    "- Do NOT list personal projects as jobs.\n"
    "- Do NOT change any fact: company names, job titles, dates, locations, education, skills.\n"
    "- Do NOT invent projects, technologies, or certifications that are not in the original CV.\n"
    "\n"
    "LANGUAGE RULE: Respond in the same language as the original CV.\n"
    "\n"
    "OUTPUT STRUCTURE (Harvard format):\n"
    "Top-level keys, in this order: name, email, phone, location, summary, education, experience, projects, certifications, skills, languages. The \"summary\" field is REQUIRED — see SUMMARY RULE below. Use 'certifications' to surface the items from any 'Certificaciones' / 'Certificaciones y Competencias' / 'Licencias' section in the original CV.\n"
    "\n"
    "SUMMARY RULE (REQUIRED):\n"
    "The output MUST include a non-empty \"summary\" string of 2-3 sentences. Two cases:\n"
    "  (a) If the original CV has a summary paragraph anywhere in the document (a \"Perfil\" / \"Summary\" / \"Professional Profile\" / \"Acerca de\" / \"Profile\" section, or a few lines of self-description at the top or bottom of the CV), extract the first 2-3 sentences of that paragraph verbatim and put them in the \"summary\" field. Rephrase action verbs to be stronger if needed, but do NOT change facts.\n"
    "  (b) If the original CV has no summary at all, build a 2-3 sentence professional identity statement by REPHRASING content that IS in the original CV (e.g. the most recent job title + years of experience + the primary field). Do NOT invent: every fact in the summary must be derivable from the original CV.\n"
    "  The output's \"summary\" field MUST be a non-empty string. The user expects to see a 2-3 sentence profile in the rendered PDF.\n"
    "\n"
    "OUTPUT FORMAT — strict JSON:\n"
    "- experience array: ONLY entries where both company and title are verbatim in original CV.\n"
    "- projects array: ONLY items that exist in the original CV (personal projects, volunteer work, publications, certifications). Do not invent.\n"
    "- skills array: ONLY skills that appear in the original CV, PLUS up to 3-5 keywords from the TARGET JOB DESCRIPTION that are directly related to the candidate's existing experience.\n"
    "- No invented entries. No modified company names. No new dates.\n"
    "- No \"...\" placeholders anywhere. The user will see the output rendered as a PDF — if any field shows literal dots, the CV looks broken.\n"
    "\n"
    "FORMATTING — NO EM DASHES:\n"
    "Do NOT use em dashes (—) anywhere in the JSON output (not in descriptions, not in titles, not anywhere).\n"
    "Use commas, semicolons, periods, or single hyphens instead. Em dashes are an obvious AI writing tell and must be avoided.\n"
    "\n"
    "EXAMPLE — CORRECT:\n"
    "Original CV: \"NTT DATA Abril 2026 — Mayo 2026, Desarrollador Backend\" and \"V12-UI (2025): React-based UI library\"\n"
    "Target: \"Google\"\n"
    "Output: experience=[{\"company\":\"NTT DATA\",\"title\":\"Desarrollador Backend\",...}], projects=[{\"name\":\"V12-UI\",\"description\":\"React-based UI library used as a personal project.\",\"technologies\":[\"React\"]}]\n"
    "\n"
    "EXAMPLE — WRONG (hallucination):\n"
    "Original CV: mentions \"V12-UI\" as a project, not an employer. Target: \"knowmad mood\"\n"
    "WRONG: experience=[{\"company\":\"knowmad mood\",...}] — candidate never worked there\n"
    "WRONG: experience=[{\"company\":\"TechCorp\",...}] — TechCorp not in original CV\n"
    "WRONG: projects=[{\"name\":\"SmartCV AI\",...}] — SmartCV AI not in original CV\n"
    "\n"
    "JSON SCHEMA:\n"
    "{\"name\":\"string|null\",\"email\":\"string|null\",\"phone\":\"string|null\",\"location\":\"string|null\",\"summary\":\"string|null\",\"experience\":[{\"company\":\"string\",\"title\":\"string\",\"start_date\":\"string\",\"end_date\":\"string\",\"description\":\"string\",\"location\":\"string|null\"}],\"education\":[{\"degree\":\"string\",\"institution\":\"string\",\"year\":\"string\",\"grade\":\"string|null\"}],\"projects\":[{\"name\":\"string\",\"description\":\"string\",\"technologies\":[\"string\"]}],\"certifications\":[\"string\"],\"skills\":[\"string\"],\"languages\":[\"string\"]}\n"
)  # noqa: S703,E501 (long lines intentional for prompt)


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
    # Strip `<think>...</think>` and `<thinking>...</thinking>` blocks
    # ENTIRELY (content + tags). The M2.x / M3 model family emits a
    # verbose 'Let me analyze...' preamble inside the think block
    # before the JSON, and the old 'remove tags only' approach left
    # the preamble text mixed with the JSON. The brace-substring
    # strategy then picked the wrong braces (from a JSON-shaped
    # example inside the think block, not the actual JSON) and
    # failed with 'brace: no match'.
    #
    # Falls back to 'open tag to end-of-string' for malformed
    # responses (max_tokens hit mid-thinking). In that case the
    # JSON never arrived, but at least the parser can fail with a
    # clean error instead of trying to parse a half-thought
    # preamble.
    cleaned = raw
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned)
    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", cleaned)
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned)
    cleaned = re.sub(r"<thinking>[\s\S]*$", "", cleaned)
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
        certifications=list_or(data.get("certifications")),
        skills=list_or(data.get("skills")),
        languages=list_or(data.get("languages")),
    )
