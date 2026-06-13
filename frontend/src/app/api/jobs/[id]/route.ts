import { NextRequest, NextResponse } from "next/server";
import { fetchJobsHistory } from "@/lib/api-client";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const data = await fetchJobsHistory({ limit: 200 });
    const job = data.items.find((j) => j.id === id);
    if (!job) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }
    return NextResponse.json(job);
  } catch {
    return NextResponse.json(
      { error: "Backend unreachable" },
      { status: 503 },
    );
  }
}
