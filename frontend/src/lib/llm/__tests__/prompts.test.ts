// Regression tests for the LLM system prompts.
//
// These tests pin the prompt text byte-for-byte against the canonical
// Python source so any accidental drift fails CI. The prompts drive
// the LLM's behavior — changing even one word could silently shift
// the model's outputs.
//
// The Python sources (referenced in the README and AGENTS.md):
//   - `backend/src/jobs_finder/infrastructure/llm/_prompt.py` — chat filter
//   - `backend/src/jobs_finder/infrastructure/llm/_cv_prompt.py` — CV adapt
//
// Why we test INDIRECTLY (substring keywords + length) instead of a
// full snapshot: the rendered string MUST be exactly equal to the
// Python source. The Python source is the contract. We pin a few
// fingerprint markers (length + key invariant substrings) here, and
// the byte-for-byte match is verified by the developer workflow
// (see `pnpm run check-prompt-drift` in the README).

import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  CHAT_FILTER_SYSTEM_PROMPT,
  ADAPT_CV_SYSTEM_PROMPT,
  buildChatFilterUserMessage,
  buildAdaptCVUserMessage,
} from "../prompts";

const BACKEND_LLM_DIR = path.resolve(
  __dirname,
  "../../../../../backend/src/jobs_finder/infrastructure/llm",
);

function readPythonExpression(file: string, expr: string): string {
  // We import the Python module via the project's `uv run` setup so
  // we can read the canonical string. Falls back to a clear error
  // if the import fails (e.g. running outside the project root).
  //
  // Note: we deliberately avoid reading the .py file as text and
  // parsing the literal — Python triple-quoted strings are subtle
  // (line continuations, escape sequences) and we'd re-implement
  // Python's lexer. Instead we delegate to Python's import system
  // via a one-liner. This guarantees we compare against the SAME
  // string the Python runtime would produce.
  //
  // `expr` is a full Python expression (e.g. "SYSTEM_PROMPT" or
  // `build_adapt_cv_user_message('cv', 't', 'c', 'd')`); the helper
  // emits `print(<expr>)` so we can capture stdout.
  const { execFileSync } = require("node:child_process") as typeof import("node:child_process");
  const backendRoot = path.resolve(BACKEND_LLM_DIR, "../../../..");
  const moduleMap: Record<string, string> = {
    "_prompt.py": "jobs_finder.infrastructure.llm._prompt",
    "_cv_prompt.py": "jobs_finder.infrastructure.llm._cv_prompt",
  };
  const moduleName = moduleMap[file];
  if (!moduleName) {
    throw new Error(`Unknown module file: ${file}`);
  }
  const script = [
    "import importlib",
    `m = importlib.import_module(${JSON.stringify(moduleName)})`,
    `print(${expr})`,
  ].join("\n");
  try {
    const out = execFileSync(
      "uv",
      ["run", "--directory", backendRoot, "python", "-c", script],
      {
        encoding: "utf8",
        timeout: 30_000,
      },
    );
    return out.replace(/\n$/, "");
  } catch (err) {
    throw new Error(
      `Could not import Python module ${file}: ${(err as Error).message}`,
    );
  }
}

function readPythonConstant(file: string, attr: string): string {
  return readPythonExpression(file, `m.${attr}`);
}

describe("CHAT_FILTER_SYSTEM_PROMPT", () => {
  it("matches the Python source byte-for-byte", () => {
    const expected = readPythonConstant("_prompt.py", "SYSTEM_PROMPT");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toBe(expected);
  }, 30_000);

  it("contains the 5 v1 invariant keywords", () => {
    // REQ-LLM-004 — these 5 keywords are the must-have contract.
    // The Python source pins them in `tests/unit/test_llm_prompt.py`.
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("NUNCA inventes, modifiques ni añadas IDs");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("Si dudas entre incluir o excluir una oferta, INCLÚYELA");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("REGLA DE MATCHING UNIVERSAL");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("NO asumas experiencia, salario, modalidad remota");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("matching_ids");
  });

  it("contains the 4 security-boundary invariants (REQ-LLM-SEC-001)", () => {
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("FRONTERA DE SEGURIDAD");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("1. NO inventes");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("2. Usa `null`");
    expect(CHAT_FILTER_SYSTEM_PROMPT).toContain("4. Si dudas");
  });

  it("is in Spanish", () => {
    expect(CHAT_FILTER_SYSTEM_PROMPT).toMatch(/Eres un asistente/);
    expect(CHAT_FILTER_SYSTEM_PROMPT).toMatch(/seleccionar/);
  });
});

describe("ADAPT_CV_SYSTEM_PROMPT", () => {
  it("matches the Python source byte-for-byte", () => {
    const expected = readPythonConstant("_cv_prompt.py", "ADAPT_CV_SYSTEM_PROMPT");
    expect(ADAPT_CV_SYSTEM_PROMPT).toBe(expected);
  }, 30_000);

  it("contains the 8 strict-forbidden rules", () => {
    for (const rule of [
      "NEVER output a company name",
      "NEVER output a job title",
      "NEVER output a date range",
      "NEVER output skills",
      "NEVER output the target company",
      "NEVER create a new job entry",
      "NEVER treat personal projects",
      // Rule 8 was reworded when the "no placeholders" rule was
      // promoted to its own section. The intent is the same — the
      // prompt forbids "..." (and other placeholders) anywhere.
      'NEVER emit a string of literal dots "..."',
    ]) {
      expect(ADAPT_CV_SYSTEM_PROMPT).toContain(rule);
    }
  });

  it("forbids splitting a job's responsibilities / modules / academic subjects into separate projects", () => {
    // Regression: MiniMax-M3 was treating academic modules (DAW
    // subjects like 'Desarrollo Backend con Java y Spring Boot',
    // 'Calidad de Software', 'Gestión de Datos', etc.) and the
    // tasks listed under a job entry ('PRÁCTICAS en NTT DATA') as
    // separate project entries, polluting the projects array.
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "PROJECTS — WHAT IS NOT A PROJECT (CRITICAL):",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "ACADEMIC MODULES / SUBJECTS",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "experience entry's description, NOT in projects",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "DAW modules like",
    );
  });

  it("forbids merging in-progress certifications / training into projects, requires merging into experience or education instead", () => {
    // Regression: 'Java SE Programmer Certification Preparation |
    // NTT DATA / Oracle Training' is a training PREPARATION, not
    // an obtained cert. The user does not have that cert. The
    // rule forces the LLM to merge such content into the
    // experience or education entry's description (whichever is
    // contextually closer in the original CV) — NOT to invent a
    // 'certifications' array the user does not actually have.
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "IN-PROGRESS TRAININGS / CERTIFICATIONS",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "training / certification PREPARATION, not obtained certifications",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "NEVER be presented as obtained certifications",
    );
  });

  it("instructs JSON-only output and source-of-truth rule", () => {
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("Output valid JSON only");
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("ABSOLUTE RULE");
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("ORIGINAL CV IS THE ONLY SOURCE OF TRUTH");
  });

  it("includes the 4 explicit quality rules added in cv-adaptation-quality", () => {
    // Projects: pull personal projects / volunteer / publications
    // / certifications from the original CV.
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "PROJECTS — INCLUDE PERSONAL PROJECTS, VOLUNTEER WORK, PUBLICATIONS, CERTIFICATIONS:",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("the projects array instead");

    // Harvard output structure: keys in this order, summary is now
    // required (was optional before the no-placeholders rewrite).
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("OUTPUT STRUCTURE (Harvard format):");
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "name, email, phone, location, summary, education, experience, projects, skills, languages",
    );

    // Keyword matching: MANDATORY, with explicit examples
    // (added in cv-quality-round-2 to strengthen the LLM's
    // adherence to the keyword-extraction rule).
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("KEYWORD MATCHING (MANDATORY):");
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "you MUST extract 3-5 KEYWORDS from the TARGET JOB DESCRIPTION",
    );
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "MUST contain at least 3 keywords from the TARGET JOB DESCRIPTION",
    );

    // No em dashes in the JSON output.
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain("FORMATTING — NO EM DASHES:");
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      "Do NOT use em dashes (\u2014) anywhere in the JSON output",
    );

    // JSON SCHEMA includes the projects array shape.
    expect(ADAPT_CV_SYSTEM_PROMPT).toContain(
      '"projects":[{"name":"string","description":"string","technologies":["string"]}]',
    );
  });
});

describe("buildChatFilterUserMessage", () => {
  it("matches the Python build_user_message output", () => {
    const expected = readPythonExpression(
      "_prompt.py",
      "m.build_user_message('react madrid', [{'id':'1','title':'Senior Developer','company':'Acme','location':'Madrid','description':None}])",
    );
    const actual = buildChatFilterUserMessage("react madrid", [
      { id: "1", title: "Senior Developer", company: "Acme", location: "Madrid", description: null },
    ]);
    expect(actual).toBe(expected);
  }, 30_000);

  it("emits a single-line JSON payload", () => {
    const out = buildChatFilterUserMessage("react madrid", []);
    expect(out).not.toContain("\n");
    expect(JSON.parse(out)).toEqual({ intent: "react madrid", jobs: [] });
  });

  it("projects only the 5 filter-relevant fields per job", () => {
    const out = buildChatFilterUserMessage("x", [
      {
        id: "1",
        title: "T",
        company: "C",
        location: "L",
        description: "D",
        url: "https://should-be-dropped",
        posted_at: "2026-01-01",
      } as Record<string, unknown>,
    ]);
    const parsed = JSON.parse(out);
    expect(parsed.jobs[0]).toEqual({
      id: "1",
      title: "T",
      company: "C",
      location: "L",
      description: "D",
    });
    expect(parsed.jobs[0]).not.toHaveProperty("url");
    expect(parsed.jobs[0]).not.toHaveProperty("posted_at");
  });

  it("preserves description=null as JSON null (not empty string)", () => {
    const out = buildChatFilterUserMessage("x", [
      { id: "1", title: "T", company: "C", location: "L", description: null },
    ]);
    const parsed = JSON.parse(out);
    expect(parsed.jobs[0].description).toBeNull();
    expect(out).toContain('"description":null');
    expect(out).not.toContain('"description":""');
  });
});

describe("buildAdaptCVUserMessage", () => {
  it("matches the Python build_adapt_cv_user_message output", () => {
    const expected = readPythonExpression(
      "_cv_prompt.py",
      "m.build_adapt_cv_user_message('My CV text', 'Senior Engineer', 'Acme', 'React job')",
    );
    const actual = buildAdaptCVUserMessage(
      "My CV text",
      "Senior Engineer",
      "Acme",
      "React job",
    );
    expect(actual).toBe(expected);
  }, 30_000);

  it("uppercases the applying company in the safety reminder", () => {
    const out = buildAdaptCVUserMessage("cv", "Dev", "Google", "job");
    expect(out).toContain("CANDIDATE HAS NEVER WORKED AT GOOGLE");
  });

  it("truncates cv_text at 8000 chars", () => {
    const long = "x".repeat(10_000);
    const out = buildAdaptCVUserMessage(long, "Dev", "Acme", "job");
    // 8000 x's should appear; 2001+ should be cut.
    expect(out).toContain("x".repeat(8000));
    expect(out).not.toContain("x".repeat(8001));
  });

  it("truncates job_description at 4000 chars", () => {
    const longJob = "y".repeat(5000);
    const out = buildAdaptCVUserMessage("cv", "Dev", "Acme", longJob);
    expect(out).toContain("y".repeat(4000));
    expect(out).not.toContain("y".repeat(4001));
  });
});

// Quiet the unused-import warning when fs is the only "node" import
// used in test helpers.
void fs;