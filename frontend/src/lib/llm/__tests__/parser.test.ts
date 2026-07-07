// Tests for the LLM response parsers.
//
// Mirrors the behavior of `parse_adapted_cv_response` and the
// `parse_user_message` validation in
// `backend/src/jobs_finder/infrastructure/llm/_prompt.py` and
// `_cv_prompt.py`. The 3 parsing strategies (direct / markdown /
// brace-substring) are pinned here so any regression in the
// defensive parser is caught by CI.

import { describe, it, expect } from "vitest";
import {
  parseAdaptedCVResponse,
  parseChatFilterResponse,
  AdaptedCVParseError,
  ChatFilterParseError,
} from "../parser";

describe("parseAdaptedCVResponse", () => {
  it("parses a clean JSON object (strategy 1: direct)", () => {
    const raw = JSON.stringify({
      name: "Ada Lovelace",
      email: "ada@example.com",
      phone: "+34 600 000 000",
      location: "Madrid",
      summary: "Senior engineer with 10 years experience.",
      experience: [
        {
          company: "Acme",
          title: "Senior Engineer",
          start_date: "2020-01",
          end_date: "2026-01",
          description: "Built systems",
          location: "Madrid",
        },
      ],
      education: [
        {
          degree: "MSc Computer Science",
          institution: "UPM",
          year: "2018",
          grade: "9.0",
        },
      ],
      projects: [
        {
          name: "V12-UI",
          description: "React UI library",
          technologies: ["React", "TypeScript"],
        },
        {
          name: "PORTFOLIO",
          description: "",
          technologies: [],
        },
      ],
      skills: ["TypeScript", "React", "Node.js"],
      languages: ["Spanish", "English"],
    });

    const cv = parseAdaptedCVResponse(raw);

    expect(cv.name).toBe("Ada Lovelace");
    expect(cv.experience).toHaveLength(1);
    expect(cv.experience[0]?.company).toBe("Acme");
    expect(cv.education[0]?.grade).toBe("9.0");
    expect(cv.projects).toHaveLength(2);
    expect(cv.projects[0]?.name).toBe("V12-UI");
    expect(cv.projects[0]?.technologies).toEqual(["React", "TypeScript"]);
    expect(cv.projects[1]?.name).toBe("PORTFOLIO");
    expect(cv.projects[1]?.technologies).toEqual([]);
    expect(cv.skills).toEqual(["TypeScript", "React", "Node.js"]);
  });

  it("extracts projects with name, description, technologies", () => {
    const raw = JSON.stringify({
      name: "John",
      projects: [
        { name: "V12-UI", description: "Personal project", technologies: ["React"] },
        { name: "Portfolio", description: "Static site", technologies: [] },
      ],
    });
    const result = parseAdaptedCVResponse(raw);
    expect(result.projects).toHaveLength(2);
    expect(result.projects[0]?.name).toBe("V12-UI");
    expect(result.projects[0]?.description).toBe("Personal project");
    expect(result.projects[0]?.technologies).toEqual(["React"]);
    expect(result.projects[1]?.name).toBe("Portfolio");
    expect(result.projects[1]?.technologies).toEqual([]);
  });

  it("defaults projects to [] when missing or not an array", () => {
    const missing = parseAdaptedCVResponse(JSON.stringify({ name: "Ada" }));
    expect(missing.projects).toEqual([]);

    const wrongType = parseAdaptedCVResponse(
      JSON.stringify({ name: "Ada", projects: "not-an-array" }),
    );
    expect(wrongType.projects).toEqual([]);
  });

  it("drops project entries with empty names (defensive parsing)", () => {
    const raw = JSON.stringify({
      name: "Ada",
      projects: [
        { name: "V12-UI", description: "ok", technologies: ["React"] },
        { name: "", description: "should be dropped", technologies: [] },
        { name: null, description: "should also be dropped", technologies: [] },
      ],
    });
    const cv = parseAdaptedCVResponse(raw);
    expect(cv.projects).toHaveLength(1);
    expect(cv.projects[0]?.name).toBe("V12-UI");
  });

  it("extracts JSON from a markdown ```json``` block (strategy 2)", () => {
    const raw = "Here is the result:\n\n```json\n" +
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: ["TS"],
        languages: [],
      }) +
      "\n```\n";

    const cv = parseAdaptedCVResponse(raw);
    expect(cv.name).toBe("Ada");
    expect(cv.skills).toEqual(["TS"]);
  });

  it("extracts JSON from a generic ``` code block (strategy 2)", () => {
    const raw = "```\n" +
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }) +
      "\n```";

    const cv = parseAdaptedCVResponse(raw);
    expect(cv.name).toBe("Ada");
  });

  it("extracts JSON via brace-substring fallback (strategy 3)", () => {
    const raw = "Some prose before " +
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }) +
      " and prose after";

    const cv = parseAdaptedCVResponse(raw);
    expect(cv.name).toBe("Ada");
  });

  it("strips <think> / <thinking> tags before parsing", () => {
    const raw = "<think>reasoning</think>" +
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      });

    const cv = parseAdaptedCVResponse(raw);
    expect(cv.name).toBe("Ada");
  });

  it("strips <thinking> tags (closing + opening variants)", () => {
    const raw = "<thinking>thoughts</thinking>" +
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      });

    const cv = parseAdaptedCVResponse(raw);
    expect(cv.name).toBe("Ada");
  });

  it("defaults name to 'Sin nombre' when missing", () => {
    const cv = parseAdaptedCVResponse(
      JSON.stringify({ experience: [], education: [], skills: [], languages: [] }),
    );
    expect(cv.name).toBe("Sin nombre");
  });

  it("defaults end_date to 'Presente' when missing", () => {
    const cv = parseAdaptedCVResponse(
      JSON.stringify({
        name: "Ada",
        experience: [
          { company: "Acme", title: "Engineer", start_date: "2020-01" },
        ],
        education: [],
        skills: [],
        languages: [],
      }),
    );
    expect(cv.experience[0]?.end_date).toBe("Presente");
  });

  it("converts null location / grade to null (not empty string)", () => {
    const cv = parseAdaptedCVResponse(
      JSON.stringify({
        name: "Ada",
        experience: [
          { company: "Acme", title: "Engineer", start_date: "2020", end_date: "2026", location: null },
        ],
        education: [
          { degree: "MSc", institution: "UPM", year: "2018", grade: null },
        ],
        skills: [],
        languages: [],
      }),
    );
    expect(cv.experience[0]?.location).toBeNull();
    expect(cv.education[0]?.grade).toBeNull();
  });

  it("handles missing arrays (experience / education / projects / skills / languages)", () => {
    const cv = parseAdaptedCVResponse(JSON.stringify({ name: "Ada" }));
    expect(cv.experience).toEqual([]);
    expect(cv.education).toEqual([]);
    expect(cv.projects).toEqual([]);
    expect(cv.skills).toEqual([]);
    expect(cv.languages).toEqual([]);
  });

  it("defaults photo to null when missing from the LLM response", () => {
    // The LLM is instructed to emit `photo: null` (it does NOT have
    // access to the source image bytes). The route handler is
    // responsible for overlaying the extracted image afterward via
    // `finalCv = { ...adaptedCv, photo: extractedPhoto }`.
    const cv = parseAdaptedCVResponse(
      JSON.stringify({ name: "Ada", experience: [], education: [], skills: [], languages: [] }),
    );
    expect(cv.photo).toBeNull();
  });

  it("passes through a photo value when the LLM emits one", () => {
    // Defensive: if a model ever DOES emit a photo string, the
    // parser preserves it as-is. The route handler still
    // overrides it, but the parser must not silently drop the
    // field (it would otherwise look like data loss in CI).
    const dataUrl = "data:image/jpeg;base64,/9j/4AAQ";
    const cv = parseAdaptedCVResponse(
      JSON.stringify({ name: "Ada", photo: dataUrl }),
    );
    expect(cv.photo).toBe(dataUrl);
  });

  it("coerces a non-string photo to null (defensive parsing)", () => {
    const cv = parseAdaptedCVResponse(
      JSON.stringify({ name: "Ada", photo: { not: "a string" } }),
    );
    expect(cv.photo).toBeNull();
  });

  it("throws AdaptedCVParseError on non-JSON garbage", () => {
    expect(() => parseAdaptedCVResponse("not json at all")).toThrow(
      AdaptedCVParseError,
    );
  });

  it("throws on response with no JSON object at all", () => {
    expect(() => parseAdaptedCVResponse("plain text, no braces")).toThrow(
      AdaptedCVParseError,
    );
  });

  it("the error message does NOT echo the full LLM response (no leak)", () => {
    // AGENTS.md rule #24: route handlers MUST NOT interpolate raw
    // exception details into user-facing messages. The parser is
    // a server-side helper but the error message IS surfaced to
    // the user via HTTPException.detail — so we trim the preview.
    try {
      parseAdaptedCVResponse("x".repeat(1000));
    } catch (e) {
      const msg = (e as Error).message;
      expect(msg.length).toBeLessThan(500);
      expect(msg).not.toContain("x".repeat(200));
    }
  });
});

describe("parseChatFilterResponse", () => {
  it("parses a valid {matching_ids, explanation} payload", () => {
    const raw = JSON.stringify({
      matching_ids: ["id1", "id5"],
      explanation: "Selected 2 of 20 jobs matching 'react'.",
    });

    const r = parseChatFilterResponse(raw);
    expect(r.matching_ids).toEqual(["id1", "id5"]);
    expect(r.explanation).toMatch(/Selected/);
  });

  it("returns empty matching_ids when none match", () => {
    const raw = JSON.stringify({
      matching_ids: [],
      explanation: "No offers match your intent.",
    });

    const r = parseChatFilterResponse(raw);
    expect(r.matching_ids).toEqual([]);
    expect(r.explanation).toMatch(/No offers/);
  });

  it("coerces non-string IDs to strings", () => {
    const raw = JSON.stringify({
      matching_ids: [1, 2, "three"],
      explanation: "ok",
    });

    const r = parseChatFilterResponse(raw);
    expect(r.matching_ids).toEqual(["1", "2", "three"]);
  });

  it("defaults missing explanation to empty string", () => {
    const raw = JSON.stringify({ matching_ids: ["id1"] });
    const r = parseChatFilterResponse(raw);
    expect(r.explanation).toBe("");
  });

  it("extracts JSON via brace-substring fallback", () => {
    const raw = "Some prose " + JSON.stringify({
      matching_ids: ["id1"],
      explanation: "ok",
    }) + " more prose";
    const r = parseChatFilterResponse(raw);
    expect(r.matching_ids).toEqual(["id1"]);
  });

  it("throws ChatFilterParseError on non-JSON garbage", () => {
    expect(() => parseChatFilterResponse("garbage")).toThrow(
      ChatFilterParseError,
    );
  });

  it("throws on a JSON array (must be object)", () => {
    expect(() => parseChatFilterResponse("[]")).toThrow(ChatFilterParseError);
  });

  it("the error message does NOT echo the full LLM response", () => {
    try {
      parseChatFilterResponse("x".repeat(1000));
    } catch (e) {
      const msg = (e as Error).message;
      expect(msg.length).toBeLessThan(500);
      expect(msg).not.toContain("x".repeat(200));
    }
  });
});