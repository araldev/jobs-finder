import "server-only";

import { extractText, getDocumentProxy } from "unpdf";

/**
 * Extract the text content of a PDF as a single merged string.
 *
 * Uses `unpdf` (the unjs pure-JS PDF parser, optimized for serverless
 * environments — no native bindings, no cold-start pain). Pages are
 * merged with a `\n` separator via `mergePages: true` so the LLM
 * receives one continuous string.
 *
 * Returns `""` on any failure (malformed PDF, image-only PDF, empty
 * document). The system prompt already instructs the LLM to handle
 * empty input gracefully — see `ADAPT_CV_SYSTEM_PROMPT`'s "if the
 * CV is empty, do not assume experience" guidance.
 *
 * AGENTS.md rule #24 — failures are caught and logged server-side;
 * the caller never sees the underlying exception (it could expose
 * internal library internals or PDF structure).
 */
export async function extractPdfText(bytes: ArrayBuffer): Promise<string> {
  try {
    const pdf = await getDocumentProxy(new Uint8Array(bytes));
    const result = await extractText(pdf, { mergePages: true });
    return result.text ?? "";
  } catch (err) {
    console.error("pdf/extract-text: extraction failed", err);
    return "";
  }
}