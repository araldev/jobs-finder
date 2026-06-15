import "server-only";

import { type NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

/**
 * POST /api/cv/generate
 *
 * Accepts a multipart form with:
 *   - file: PDF (the user's CV)
 *   - job_title: string
 *   - job_company: string
 *   - job_description: string
 *   - job_url: string
 *
 * Proxies the request to the FastAPI backend and returns the PDF binary.
 */
export async function POST(request: NextRequest) {
  if (!BACKEND_API_KEY) {
    return NextResponse.json(
      { error: "Backend API key not configured" },
      { status: 500 },
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data" }, { status: 400 });
  }

  // Forward the multipart form to FastAPI
  const backendResponse = await fetch(`${BACKEND_URL}/cv/generate`, {
    method: "POST",
    headers: {
      "X-API-Key": BACKEND_API_KEY,
    },
    body: formData,
  });

  if (!backendResponse.ok) {
    const errorText = await backendResponse.text();
    return NextResponse.json(
      { error: `Backend error ${backendResponse.status}: ${errorText}` },
      { status: backendResponse.status },
    );
  }

  // Stream the PDF back to the browser
  const pdfBytes = await backendResponse.arrayBuffer();
  const contentDisposition = backendResponse.headers.get("Content-Disposition");
  const filename = contentDisposition
    ? contentDisposition.replace('attachment; filename="', "").replace('"', "")
    : "CV-adaptado.pdf";

  return new NextResponse(pdfBytes, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Content-Length": String(pdfBytes.byteLength),
    },
  });
}
