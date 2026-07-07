import { NextRequest, NextResponse } from "next/server";
import { fetchJobsHistory } from "@/lib/supabase-queries";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const rawLimit = searchParams.get("limit") ?? "20";
  const rawPage = searchParams.get("page") ?? "0";
  const pageSize = parseInt(rawLimit, 10) || 20;
  const page = parseInt(rawPage, 10) || 0;

  const args = {
    keywords: searchParams.get("q") ?? undefined,
    location: searchParams.get("location") ?? undefined,
    sources: searchParams.get("sources") ?? undefined,
    limit: pageSize,
    offset: page * pageSize,
  };

  try {
    const data = await fetchJobsHistory(args);
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { items: [], total: 0, limit: pageSize, offset: page * pageSize },
      { status: 503 },
    );
  }
}
