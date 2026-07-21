import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { chatCompletion, LLMUnavailableError } from "@/lib/llm-client";
import { countCvAdaptedThisMonth, enforceCvQuota } from "@/lib/billing/quota";
import { planCacheGet } from "@/lib/billing/plan-cache";
import { PLANS } from "@/lib/billing/plans";
import {
  ADAPT_CV_SYSTEM_PROMPT,
  buildAdaptCVUserMessage,
  type AdaptedCV,
} from "@/lib/llm/prompts";
import { parseAdaptedCVResponse, AdaptedCVParseError } from "@/lib/llm/parser";
import { substituteHyperlinksInCv } from "@/lib/llm/substitute-hyperlinks";
import { extractPdfText } from "@/lib/pdf/extract-text";
import { extractPdfHyperlinks } from "@/lib/pdf/extract-hyperlinks";
import { extractCvImage } from "@/lib/pdf/extract-image";
import { renderAdaptedCvAsPdf } from "@/lib/pdf/render-cv";
import { fetchUrlContent } from "@/lib/url-fetch";

/**
 * POST /api/cv/generate-custom
 *
 * Accepts a multipart form with:
 *   - file: PDF (the user's CV, optional if saved CV is used client-side)
 *   - job_url: string (optional)
 *   - job_description: string (optional)
 *   - job_title: string (optional)
 *   - job_company: string (optional)
 *
 * The flow is the same as POST /api/cv/generate but with custom input
 * (a job URL or free-text description) instead of requiring a database
 * job record.
 *
 * URL resolution:
 *   - If job_url is provided AND job_description is empty → fetch the URL
 *     and use the extracted textContent as effectiveDescription.
 *   - If job_url is empty AND job_description is empty → 400 error.
 *   - If BOTH are provided → job_description wins over URL content.
 *
 * See POST /api/cv/generate for the detailed LLM + PDF rendering flow.
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

  // 1b. Quota enforcement (after auth, before LLM).
  const billingEnabled = process.env.NEXT_PUBLIC_BILLING_ENABLED;
  if (billingEnabled === "true") {
    const userId = session.user.id;
    const cached = planCacheGet(userId);
    const plan = cached?.plan ?? "free";
    const config = PLANS[plan];
    const used = await countCvAdaptedThisMonth(userId, supabase);
    const { allowed, limit, remaining } = enforceCvQuota(plan, used);
    if (!allowed) {
      return NextResponse.json(
        {
          error: "CV quota exceeded",
          message: `You have reached your monthly CV adaptation limit (${config.cvLimitPerMonth === "unlimited" ? "unlimited" : `${limit} per month`}). Upgrade to Pro for unlimited adaptations.`,
          used,
          limit,
          remaining,
          plan,
        },
        { status: 402 },
      );
    }
  }

  // 2. Parse the multipart form.
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
  const jobUrl = (formData.get("job_url") as string | null) ?? "";
  const jobDescription = (formData.get("job_description") as string | null) ?? "";
  const jobTitle = (formData.get("job_title") as string | null) ?? "";
  const jobCompany = (formData.get("job_company") as string | null) ?? "";

  // 3. Validate: need a file (PDF).
  if (!(file instanceof File)) {
    return NextResponse.json(
      { error: "Subí tu CV o guardalo primero en Configuración" },
      { status: 400 },
    );
  }
  if (file.type && file.type !== "application/pdf") {
    return NextResponse.json(
      { error: "Solo se aceptan archivos PDF." },
      { status: 400 },
    );
  }

  // 4. Validate: need at least URL or description.
  const hasJobUrl = typeof jobUrl === "string" && jobUrl.trim().length > 0;
  const hasJobDescription = typeof jobDescription === "string" && jobDescription.trim().length > 0;

  if (!hasJobUrl && !hasJobDescription) {
    return NextResponse.json(
      { error: "Proporcioná una URL de la oferta o pegá la descripción" },
      { status: 400 },
    );
  }

  // 5. Resolve the effective job description.
  //    If job_url is provided AND job_description is empty → fetch the URL.
  //    If BOTH are provided → job_description wins (user input overrides URL).
  //    If only job_description is provided → use it directly.
  let effectiveDescription: string;

  if (hasJobDescription) {
    // User-provided description always wins
    effectiveDescription = jobDescription.trim();
  } else if (hasJobUrl) {
    // Fetch the URL content
    const fetched = await fetchUrlContent(jobUrl.trim());
    if (!fetched.success || fetched.textContent.length === 0) {
      return NextResponse.json(
        { error: "No pudimos obtener la oferta desde esa URL. Pegá la descripción manualmente." },
        { status: 422 },
      );
    }
    effectiveDescription = fetched.textContent;
  } else {
    // Should not reach here due to validation above, but defensive.
    effectiveDescription = "";
  }

  // 6. Read + cap the upload (10 MB max).
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

  // 7. Clone the ArrayBuffer for image extraction (same reason as the
  //    generate route — pdf-lib's PDFDocument.load detaches the buffer).
  const pdfBytesForImage: ArrayBuffer = pdfBytes.slice(0);
  // Same reason — `extractPdfHyperlinks` (pdfjs-dist via unpdf) takes
  // ownership of its input. Give it a clone so the rest of the
  // pipeline stays intact.
  const pdfBytesForLinks: ArrayBuffer = pdfBytes.slice(0);

  // 8. Extract the CV text.
  const cvText = await extractPdfText(pdfBytes);

  // 8b. Extract the CV's external hyperlinks (real URLs from the PDF's
  //     link annotations). Passed to the LLM as a HYPERLINKS — ORIGINAL
  //     URL MAP so it doesn't have to invent URLs from labels. Returns
  //     `[]` on failure or for PDFs with no http(s) link annotations.
  const pdfHyperlinks = await extractPdfHyperlinks(pdfBytesForLinks);

  // 9. Extract the CV's embedded photo (best-effort).
  const extractedPhoto = await extractCvImage(pdfBytesForImage);

  // 10. Build the messages array and call the LLM.
  //     jobTitle and jobCompany CAN be empty strings — the LLM handles
  //     that gracefully (it just shows empty fields on the adapted CV).
  const userMessage = buildAdaptCVUserMessage(
    cvText,
    jobTitle,
    jobCompany,
    effectiveDescription,
    pdfHyperlinks,
  );

  let rawResponse: string;
  try {
    rawResponse = await chatCompletion(
      [
        { role: "system", content: ADAPT_CV_SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
      { jsonMode: true, thinking: { type: "disabled" } },
    );
  } catch (err) {
    if (err instanceof LLMUnavailableError) {
      console.error("cv/generate-custom: LLM unavailable", err);
      return NextResponse.json(
        { error: "LLM provider unavailable" },
        { status: 502 },
      );
    }
    console.error("cv/generate-custom: unexpected LLM error", err);
    return NextResponse.json(
      { error: "LLM provider unavailable" },
      { status: 502 },
    );
  }

  // 11. Parse the LLM's response.
  let adaptedCv: AdaptedCV;
  try {
    adaptedCv = parseAdaptedCVResponse(rawResponse);
  } catch (err) {
    if (err instanceof AdaptedCVParseError) {
      console.error("cv/generate-custom: LLM response not parseable", err);
      return NextResponse.json(
        { error: "No se pudo adaptar el CV al perfil solicitado." },
        { status: 422 },
      );
    }
    console.error("cv/generate-custom: unexpected parse error", err);
    return NextResponse.json(
      { error: "No se pudo adaptar el CV al perfil solicitado." },
      { status: 422 },
    );
  }

  // 11b. SUSPENDERS layer: substitute LLM-invented URLs in
  //      `cv.projects[].links[]` with the real URLs from the PDF
  //      hyperlink map (by label match — 4-strategy cascade). When
  //      `pdfHyperlinks` is empty this is a no-op. Mirrors the
  //      `substitute_hyperlinks_in_cv` step in the Python use case.
  const substitutedCv = substituteHyperlinksInCv(adaptedCv, pdfHyperlinks);

  // 12. Overlay the extracted photo.
  const finalCv: AdaptedCV = { ...substitutedCv, photo: extractedPhoto };

  // 13. Render the structured CV as a PDF.
  let renderedPdf: Uint8Array<ArrayBuffer>;
  try {
    renderedPdf = await renderAdaptedCvAsPdf(finalCv);
  } catch (err) {
    console.error("cv/generate-custom: PDF rendering failed", err);
    return NextResponse.json(
      { error: "No se pudo generar el PDF del CV adaptado." },
      { status: 500 },
    );
  }

  // 14. Record the engagement event (best-effort).
  const userId = session.user.id;
  const { error: engagementError } = await supabase
    .from("user_engagement")
    .insert({
      user_id: userId,
      event_type: "cv_adapted",
      job_id: null,
      metadata: {
        job_title: jobTitle || null,
        job_company: jobCompany || null,
        job_url: jobUrl || null,
      },
    });

  if (engagementError) {
    console.error(
      "cv/generate-custom: failed to record engagement",
      engagementError,
    );
  }

  // 15. Return the rendered PDF.
  return new NextResponse(renderedPdf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'attachment; filename="CV-adaptado.pdf"',
    },
  });
}
