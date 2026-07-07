// Response parser for the CV-adaptation LLM call.
//
// Mirrors the defensive parsing strategy in
// `backend/src/jobs_finder/infrastructure/llm/_cv_prompt.parse_adapted_cv_response`:
// try 3 strategies in order — direct JSON parse, JSON in markdown code
// block, first-brace substring. Each strategy is tried before
// raising, so the caller gets a structured `AdaptedCV` whenever the
// LLM emits ANY JSON object matching the schema (even with markdown
// wrappers or trailing prose).
//
// Thinking-block stripping (the M2.x model family emits
// `<think>...</think>` tags) is also mirrored here.

import type { AdaptedCV, AdaptedCVProject } from "./prompts";

export class AdaptedCVParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AdaptedCVParseError";
  }
}

const THINKING_TAGS = [
  "<think>",
  "</thinking>",
  "</think>",
  "<thinking>",
  "</thinking>",
];

const MARKDOWN_JSON_PATTERNS = [
  /```json\s*(\{[\s\S]*?\})\s*```/,
  /```\s*(\{[\s\S]*?\})\s*```/,
];

function stripThinkingBlocks(raw: string): string {
  let cleaned = raw;
  for (const tag of THINKING_TAGS) {
    cleaned = cleaned.split(tag).join("");
  }
  return cleaned.trim();
}

function tryParseJson(text: string): unknown | undefined {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function extractFirstBraced(text: string): unknown | undefined {
  const first = text.indexOf("{");
  const last = text.lastIndexOf("}");
  if (first === -1 || last === -1 || last <= first) return undefined;
  return tryParseJson(text.slice(first, last + 1));
}

function extractMarkdownJson(text: string): unknown | undefined {
  for (const pattern of MARKDOWN_JSON_PATTERNS) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const result = tryParseJson(match[1]);
      if (result !== undefined) return result;
    }
  }
  return undefined;
}

function strOr(value: unknown, fallback = ""): string {
  return value === null || value === undefined ? fallback : String(value);
}

function photoOr(value: unknown): string | null {
  // The LLM is supposed to emit `photo: null` (the route handler
  // overlays the extracted image). If the model emits a non-string
  // value (an object, array, number), we coerce to `null` rather
  // than to a string — preserves the "no photo" signal and avoids
  // surfacing malformed values to the renderer.
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  return null;
}

function listOr(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((v) => String(v));
  }
  return [];
}

function projectsOr(value: unknown): AdaptedCVProject[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((p) => {
      const proj = (p ?? {}) as Record<string, unknown>;
      return {
        name: strOr(proj.name),
        description: strOr(proj.description, ""),
        technologies: listOr(proj.technologies),
      };
    })
    .filter((p) => p.name.length > 0);
}

export function parseAdaptedCVResponse(raw: string): AdaptedCV {
  const cleaned = stripThinkingBlocks(raw);
  const errors: string[] = [];

  // Strategy 1: direct parse
  let data: unknown;
  try {
    data = JSON.parse(cleaned);
  } catch (e) {
    errors.push(`direct: ${(e as Error).message}`);
  }

  // Strategy 2: extract from markdown code block
  if (data === undefined || data === null) {
    const fromMd = extractMarkdownJson(cleaned);
    if (fromMd !== undefined) {
      data = fromMd;
    } else {
      errors.push("markdown: no match");
    }
  }

  // Strategy 3: find first { and last } and try that substring
  if (data === undefined || data === null) {
    const fromBrace = extractFirstBraced(cleaned);
    if (fromBrace !== undefined) {
      data = fromBrace;
    } else {
      errors.push("brace: no match");
    }
  }

  if (data === undefined || data === null || typeof data !== "object" || Array.isArray(data)) {
    // Server-side debug log: a truncated preview of the raw LLM
    // response so we can see what the model is actually emitting
    // (the user-facing error message below intentionally does NOT
    // echo this — AGENTS.md rule #24). Help debug future MiniMax
    // JSON-formatting quirks without leaking the payload to the
    // client.
    console.error(
      "parser: LLM returned non-JSON. Tried strategies:",
      errors.join("; "),
      "Raw preview:",
      raw.slice(0, 500),
    );
    // AGENTS.md rule #24 — the error message MUST NOT echo the raw
    // LLM response. The "Tried: ..." line names the strategies that
    // failed (helps debugging) but does NOT include the response
    // payload. The caller maps this to a 422 with a static message.
    throw new AdaptedCVParseError(
      `LLM response is not a JSON object (tried: ${errors.join("; ")}).`,
    );
  }

  const obj = data as Record<string, unknown>;

  const experience = Array.isArray(obj.experience)
    ? obj.experience.map((e) => {
        const exp = (e ?? {}) as Record<string, unknown>;
        return {
          company: strOr(exp.company),
          title: strOr(exp.title),
          start_date: strOr(exp.start_date, ""),
          end_date: strOr(exp.end_date, "Presente"),
          description: strOr(exp.description, ""),
          location: exp.location ? strOr(exp.location) : null,
        };
      })
    : [];

  const education = Array.isArray(obj.education)
    ? obj.education.map((e) => {
        const edu = (e ?? {}) as Record<string, unknown>;
        return {
          degree: strOr(edu.degree),
          institution: strOr(edu.institution),
          year: strOr(edu.year, ""),
          grade: edu.grade ? strOr(edu.grade) : null,
        };
      })
    : [];

  const projects = projectsOr(obj.projects);

  return {
    name: strOr(obj.name, "Sin nombre"),
    email: strOr(obj.email, ""),
    phone: strOr(obj.phone, ""),
    location: strOr(obj.location, ""),
    summary: strOr(obj.summary, ""),
    experience,
    education,
    projects,
    skills: listOr(obj.skills),
    languages: listOr(obj.languages),
    photo: photoOr(obj.photo),
  };
}

// ── Chat-filter response parser ──────────────────────────────────
//
// Mirrors `_prompt.parse_user_message` validation: the LLM returns a
// JSON object with `matching_ids: string[]` and `explanation: string`.
// Any deviation throws — the caller maps the error to an SSE `error`
// event with code `llm_parse`.

export interface ChatFilterResult {
  matching_ids: string[];
  explanation: string;
}

export class ChatFilterParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatFilterParseError";
  }
}

export function parseChatFilterResponse(raw: string): ChatFilterResult {
  const cleaned = raw.trim();
  let data: unknown;

  // Try direct JSON parse first.
  try {
    data = JSON.parse(cleaned);
  } catch {
    // Fallback: find first { and last }.
    const first = cleaned.indexOf("{");
    const last = cleaned.lastIndexOf("}");
    if (first === -1 || last === -1 || last <= first) {
      // AGENTS.md rule #24 — error message MUST NOT echo the raw
      // LLM response payload. Caller maps this to a 502 with a
      // static "LLM response could not be parsed" detail.
      throw new ChatFilterParseError("LLM response is not a JSON object");
    }
    try {
      data = JSON.parse(cleaned.slice(first, last + 1));
    } catch {
      throw new ChatFilterParseError("LLM response is not a JSON object");
    }
  }

  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new ChatFilterParseError("LLM response is not a JSON object");
  }

  const obj = data as Record<string, unknown>;
  const matching_ids = Array.isArray(obj.matching_ids)
    ? obj.matching_ids.map((id) => String(id))
    : [];
  const explanation = typeof obj.explanation === "string" ? obj.explanation : "";

  return { matching_ids, explanation };
}