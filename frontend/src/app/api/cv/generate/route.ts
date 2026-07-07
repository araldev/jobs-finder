import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { chatCompletion, LLMUnavailableError } from "@/lib/llm-client";
import {
  ADAPT_CV_SYSTEM_PROMPT,
  buildAdaptCVUserMessage,
  type AdaptedCV,
} from "@/lib/llm/prompts";
import { parseAdaptedCVResponse, AdaptedCVParseError } from "@/lib/llm/parser";
import { extractPdfText } from "@/lib/pdf/extract-text";
import { renderAdaptedCvAsPdf } from "@/lib/pdf/render-cv";

/**
 * POST /api/cv/generate
 *
 * Accepts a multipart form with:
 *   - file: PDF (the user's CV)
 *   - job_title: string
 *   - job_company: string
 *   - job_description: string
 *   - job_url: string (unused server-side, kept for parity with
 *     the backend's contract)
 *
 * The flow:
 *   1. Authenticate (Supabase session required — the engagement
 *      event recording relies on `auth.uid()`).
 *   2. Validate the upload (content-type whitelist + 10 MB cap
 *      per AGENTS.md rule #28).
 *   3. Extract the CV's text content with `unpdf`
 *      (`@/lib/pdf/extract-text`). Image-only / malformed PDFs
 *      yield an empty string — the LLM handles that gracefully.
 *   4. Send CV text + job description to the LLM
 *      (`chatCompletion({ jsonMode: true })`).
 *   5. Parse the response with the defensive JSON parser.
 *   6. Record a `cv_adapted` engagement event in Supabase so
 *      `useCVAdapted`'s dashboard widget keeps counting.
 *   7. Render the structured CV as a real PDF
 *      (`@/lib/pdf/render-cv`) and return it as
 *      `application/pdf` with a `Content-Disposition` attachment
 *      header so the browser saves it as `CV-adaptado.pdf`.
 *
 * No `LLM_API_KEY` is ever logged or surfaced (AGENTS.md rule #24).
 * The static `"LLM provider unavailable"` message is what reaches
 * the client on any LLM failure; the underlying cause is logged
 * server-side with `console.error`.
 */
export async function POST(request: NextRequest) {
  // 1. Authenticate.
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // 2. Parse + validate the multipart form.
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { error: "Invalid form data" },
      { status: 400 },
    );
  }

  const file = formData.get("file");
  const jobTitle = formData.get("job_title");
  const jobCompany = formData.get("job_company");
  const jobDescription = formData.get("job_description") ?? "";

  if (!(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing CV file" },
      { status: 400 },
    );
  }
  if (file.type && file.type !== "application/pdf") {
    return NextResponse.json(
      { error: "Solo se aceptan archivos PDF." },
      { status: 400 },
    );
  }
  if (typeof jobTitle !== "string" || jobTitle.length === 0) {
    return NextResponse.json(
      { error: "Missing job_title" },
      { status: 400 },
    );
  }
  if (typeof jobCompany !== "string" || jobCompany.length === 0) {
    return NextResponse.json(
      { error: "Missing job_company" },
      { status: 400 },
    );
  }

  // 3. Read + cap the upload (AGENTS.md rule #28 — file uploads
  //    MUST be validated: content-type whitelist + max_length cap).
  const maxFileSize = 10 * 1024 * 1024; // 10 MB
  let pdfBytes: ArrayBuffer;
  try {
    pdfBytes = await file.arrayBuffer();
  } catch {
    return NextResponse.json(
      { error: "Error leyendo el archivo PDF." },
      { status: 400 },
    );
  }
  if (pdfBytes.byteLength === 0) {
    return NextResponse.json(
      { error: "El archivo PDF está vacío." },
      { status: 400 },
    );
  }
  if (pdfBytes.byteLength > maxFileSize) {
    return NextResponse.json(
      { error: "El archivo PDF excede el tamaño máximo de 10 MB." },
      { status: 400 },
    );
  }

  // 4. Extract the CV text with `unpdf` (returns "" on failure —
  //    the LLM's system prompt already handles empty input).
  const cvText = await extractPdfText(pdfBytes);

  // 5. Build the messages array and call the LLM.
  const userMessage = buildAdaptCVUserMessage(
    cvText,
    jobTitle,
    jobCompany,
    typeof jobDescription === "string" ? jobDescription : "",
  );

  let rawResponse: string;
  try {
    rawResponse = await chatCompletion(
      [
        { role: "system", content: ADAPT_CV_SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
      { jsonMode: true },
    );
  } catch (err) {
    if (err instanceof LLMUnavailableError) {
      console.error("cv/generate: LLM unavailable", err);
      return NextResponse.json(
        { error: "LLM provider unavailable" },
        { status: 502 },
      );
    }
    console.error("cv/generate: unexpected LLM error", err);
    return NextResponse.json(
      { error: "LLM provider unavailable" },
      { status: 502 },
    );
  }

  // 6. Parse the LLM's response with the defensive parser (handles
  //    markdown fences, thinking blocks, brace-substring fallback).
  let adaptedCv: AdaptedCV;
  try {
    adaptedCv = parseAdaptedCVResponse(rawResponse);
  } catch (err) {
    if (err instanceof AdaptedCVParseError) {
      console.error("cv/generate: LLM response not parseable", err);
      return NextResponse.json(
        { error: "No se pudo adaptar el CV al perfil solicitado." },
        { status: 422 },
      );
    }
    console.error("cv/generate: unexpected parse error", err);
    return NextResponse.json(
      { error: "No se pudo adaptar el CV al perfil solicitado." },
      { status: 422 },
    );
  }

  // 7. Render the structured CV as a real PDF and return it. The
  //    `GenerateCVModal` consumer does `await res.blob()` and saves
  //    it as `CV-adaptado.pdf` — we set the Content-Disposition
  //    header so the browser does the same thing.
  let renderedPdf: Uint8Array<ArrayBuffer>;
  try {
    renderedPdf = await renderAdaptedCvAsPdf(adaptedCv);
  } catch (err) {
    console.error("cv/generate: PDF rendering failed", err);
    return NextResponse.json(
      { error: "No se pudo generar el PDF del CV adaptado." },
      { status: 500 },
    );
  }

  // 8. Record the engagement event (best-effort — the user still
  //    gets their CV even if the event recording fails, matching
  //    the backend's ENG-002 contract).
  //
  // CRITICAL: `user_engagement.user_id` has a NOT NULL constraint
  // AND an RLS policy `WITH CHECK (auth.uid() = user_id)` (migration
  // 007). Omitting `user_id` makes the INSERT fail with code 42501
  // ("row-level security policy"). We get the user id from the
  // session retrieved at the top of the handler.
  const userId = session.user.id;
  const { error: engagementError } = await supabase
    .from("user_engagement")
    .insert({
      user_id: userId,
      event_type: "cv_adapted",
      job_id: null,
      metadata: {
        job_title: jobTitle,
        job_company: jobCompany,
      },
    });

  if (engagementError) {
    // Log but don't fail the response — the CV was generated.
    console.error("cv/generate: failed to record engagement", engagementError);
  }

  // 9. Return the rendered PDF. `Uint8Array<ArrayBuffer>` is a
  //    valid `BodyInit` directly — no Blob wrapper needed (the
  //    `Blob` route we tried first caused the runtime to stringify
  //    the Blob instead of streaming its bytes in some Node
  //    versions; the raw Uint8Array round-trips correctly).
  return new NextResponse(renderedPdf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'attachment; filename="CV-adaptado.pdf"',
    },
  });
}