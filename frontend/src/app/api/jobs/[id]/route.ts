import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (BACKEND_API_KEY) headers["X-API-Key"] = BACKEND_API_KEY;

  try {
    const res = await fetch(`${BACKEND_URL}/jobs/history/by-id/${encodeURIComponent(id)}`, {
      headers,
    });
    if (res.status === 404) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }
    if (!res.ok) {
      return NextResponse.json({ error: "Backend unreachable" }, { status: 503 });
    }
    const job = await res.json();
    return NextResponse.json(job);
  } catch {
    return NextResponse.json({ error: "Backend unreachable" }, { status: 503 });
  }
}
