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

from ..cv._template import AdaptedCV, EducationEntry, ExperienceEntry

ADAPT_CV_SYSTEM_PROMPT = """\
You are a professional CV writer. You MUST respond with ONLY valid JSON.
No explanations, no markdown, no narrative text before or after.

EXAMPLE OF EXPECTED OUTPUT:
Input: "John Doe, developer at TechCorp, Python, Java"
Output: {"name":"John Doe","email":"","phone":"","location":"","summary":"Developer at TechCorp.","experience":[{"company":"TechCorp","title":"Developer","start_date":"","end_date":"","description":"Developer.","location":""}],"education":[],"skills":["Python","Java"],"languages":[]}

CRITICAL RULES:
1. Your output must be parseable by json.loads() — nothing else.
2. Return ONLY the JSON object. No text before or after.
3. Use null for missing string fields, [] for missing arrays.
4. Do not invent information. Only use what is in the original CV.
5. Reorder and rephrase existing content to match the job description.

JSON SCHEMA:
{"name":"string|null","email":"string|null","phone":"string|null","location":"string|null","summary":"string|null","experience":[{"company":"string","title":"string","start_date":"string","end_date":"string","description":"string","location":"string|null"}],"education":[{"degree":"string","institution":"string","year":"string","grade":"string|null"}],"skills":["string"],"languages":["string"]}
"""  # noqa: S703,E501 (long lines intentional for prompt)


def build_adapt_cv_user_message(
    cv_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
) -> str:
    """Build the user message for the CV adaptation call."""
    return (
        f"ORIGINAL CV:\n{cv_text[:8000]}\n\n"
        f"JOB TITLE: {job_title}\n"
        f"JOB COMPANY: {job_company}\n"
        f"JOB DESCRIPTION:\n{job_description[:4000]}\n\n"
        f"Adapt this CV to the job offer. Follow all rules. Return ONLY JSON."
    )


def parse_adapted_cv_response(raw: str) -> AdaptedCV:
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

    return AdaptedCV(
        name=str_or(data.get("name"), "Sin nombre"),
        email=str_or(data.get("email"), ""),
        phone=str_or(data.get("phone"), ""),
        location=str_or(data.get("location"), ""),
        summary=str_or(data.get("summary"), ""),
        experience=experience,
        education=education,
        skills=list_or(data.get("skills")),
        languages=list_or(data.get("languages")),
    )
