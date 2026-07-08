/** @vitest-environment node */
import { describe, expect, it } from "vitest";

import type { AdaptedCV } from "@/lib/llm/prompts";
import {
  buildUrlMap,
  findUrlForLabel,
  normalizeLabel,
  substituteHyperlinksInCv,
} from "@/lib/llm/substitute-hyperlinks";

const baseCv: AdaptedCV = {
  name: "Arturo",
  email: "a@b.c",
  phone: "+34",
  location: "M",
  summary: "S",
  experience: [],
  education: [],
  projects: [],
  certifications: [],
  skills: [],
  languages: [],
  photo: null,
};

describe("normalizeLabel", () => {
  it("lowercases and trims", () => {
    expect(normalizeLabel("  GitHub  ")).toBe("github");
  });
  it("strips common suffixes", () => {
    expect(normalizeLabel("Github link")).toBe("github");
    expect(normalizeLabel("Storybook URL")).toBe("storybook");
    expect(normalizeLabel("Demo here")).toBe("demo");
  });
  it("strips common prefixes", () => {
    expect(normalizeLabel("Go to Github")).toBe("github");
    expect(normalizeLabel("See Demo")).toBe("demo");
  });
  it("collapses internal whitespace", () => {
    expect(normalizeLabel("My   Demo   Link")).toBe("my demo");
  });
  it("returns empty for empty input", () => {
    expect(normalizeLabel("")).toBe("");
    expect(normalizeLabel("   ")).toBe("");
  });
});

describe("buildUrlMap", () => {
  it("normalizes keys and deduplicates via last-write-wins", () => {
    const map = buildUrlMap([
      { label: "Github", url: "https://a.com" },
      { label: "github link", url: "https://b.com" },
      { label: "Storybook", url: "https://sb.io" },
    ]);
    expect(map.get("github")).toBe("https://b.com"); // last wins
    expect(map.get("storybook")).toBe("https://sb.io");
  });
  it("skips empty labels", () => {
    const map = buildUrlMap([
      { label: "", url: "https://a.com" },
      { label: "Real", url: "https://b.com" },
    ]);
    expect(map.size).toBe(1);
    expect(map.get("real")).toBe("https://b.com");
  });
});

describe("findUrlForLabel", () => {
  it("exact normalized match", () => {
    const map = buildUrlMap([{ label: "Github", url: "https://g.com/v" }]);
    expect(findUrlForLabel("github", map)).toBe("https://g.com/v");
  });
  it("substring both directions (label contains pdf-label)", () => {
    const map = buildUrlMap([{ label: "Github link", url: "https://g.com" }]);
    expect(findUrlForLabel("github", map)).toBe("https://g.com");
  });
  it("substring both directions (pdf-label contains label)", () => {
    const map = buildUrlMap([{ label: "GitHub", url: "https://g.com" }]);
    expect(findUrlForLabel("GitHub repo", map)).toBe("https://g.com");
  });
  it("token Jaccard overlap > 0.5", () => {
    const map = buildUrlMap([{ label: "V12-UI demo", url: "https://d.com" }]);
    expect(findUrlForLabel("demo link", map)).toBe("https://d.com");
  });
  it("returns null when no strategy hits", () => {
    const map = buildUrlMap([{ label: "Github", url: "https://g.com" }]);
    expect(findUrlForLabel("Storybook", map)).toBeNull();
  });
  it("returns null for empty label", () => {
    const map = buildUrlMap([{ label: "Github", url: "https://g.com" }]);
    expect(findUrlForLabel("", map)).toBeNull();
  });
  it("returns null for empty map", () => {
    expect(findUrlForLabel("Github", new Map())).toBeNull();
  });
});

describe("substituteHyperlinksInCv", () => {
  it("is a no-op when hyperlinks is empty", () => {
    const cv: AdaptedCV = {
      ...baseCv,
      projects: [
        {
          name: "V12-UI",
          description: "x",
          technologies: ["React"],
          links: [{ label: "Github link", url: "https://wrong.com" }],
        },
      ],
    };
    const out = substituteHyperlinksInCv(cv, []);
    // Same reference (not modified, no copy).
    expect(out).toBe(cv);
  });

  it("substitutes LLM-invented URLs with the real ones from the MAP", () => {
    const cv: AdaptedCV = {
      ...baseCv,
      projects: [
        {
          name: "V12-UI",
          description: "x",
          technologies: ["React"],
          links: [{ label: "Github link", url: "https://wrong.com" }],
        },
      ],
    };
    const out = substituteHyperlinksInCv(cv, [
      { label: "Github link", url: "https://github.com/u/v", page: 1 },
    ]);
    expect(out.projects[0]?.links[0]).toEqual({
      label: "Github link",
      url: "https://github.com/u/v",
    });
  });

  it("is idempotent when LLM already emitted the real URL", () => {
    const cv: AdaptedCV = {
      ...baseCv,
      projects: [
        {
          name: "V12-UI",
          description: "x",
          technologies: ["React"],
          links: [{ label: "Github link", url: "https://github.com/u/v" }],
        },
      ],
    };
    const out = substituteHyperlinksInCv(cv, [
      { label: "Github link", url: "https://github.com/u/v", page: 1 },
    ]);
    expect(out.projects[0]?.links[0]).toEqual({
      label: "Github link",
      url: "https://github.com/u/v",
    });
  });

  it("keeps label-only chips when no URL match in MAP", () => {
    const cv: AdaptedCV = {
      ...baseCv,
      projects: [
        {
          name: "V12-UI",
          description: "x",
          technologies: ["React"],
          links: [{ label: "Custom badge", url: "" }],
        },
      ],
    };
    const out = substituteHyperlinksInCv(cv, [
      { label: "Github", url: "https://github.com/u/v", page: 1 },
    ]);
    // The chip is preserved with its empty URL — the renderer will
    // draw it as a label-only <span>.
    expect(out.projects[0]?.links[0]).toEqual({
      label: "Custom badge",
      url: "",
    });
  });

  it("substitutes only matching chips in mixed input", () => {
    const cv: AdaptedCV = {
      ...baseCv,
      projects: [
        {
          name: "V12-UI",
          description: "x",
          technologies: ["React"],
          links: [
            { label: "Github", url: "https://github.com/u/v" },
            { label: "Storybook link", url: "" },
            { label: "npm", url: "https://wrong.com" },
          ],
        },
      ],
    };
    const out = substituteHyperlinksInCv(cv, [
      { label: "npm", url: "https://npmjs.com/u/v", page: 1 },
    ]);
    expect(out.projects[0]?.links).toEqual([
      { label: "Github", url: "https://github.com/u/v" },
      { label: "Storybook link", url: "" },
      { label: "npm", url: "https://npmjs.com/u/v" },
    ]);
  });

  it("does not mutate the input CV", () => {
    const cv: AdaptedCV = {
      ...baseCv,
      projects: [
        {
          name: "V12-UI",
          description: "x",
          technologies: ["React"],
          links: [{ label: "Github link", url: "https://wrong.com" }],
        },
      ],
    };
    const originalUrl = cv.projects[0]?.links[0]?.url;
    substituteHyperlinksInCv(cv, [
      { label: "Github link", url: "https://github.com/u/v", page: 1 },
    ]);
    // Input unchanged.
    expect(cv.projects[0]?.links[0]?.url).toBe(originalUrl);
  });
});
