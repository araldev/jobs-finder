import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("user_settings")
    .select("*")
    .single();

  if (error?.code === "PGRST116") {
    // No rows returned - return defaults
    return NextResponse.json({
      enabled_platforms: ["linkedin", "indeed", "infojobs"],
      notifications_enabled: true,
    });
  }
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({
    enabled_platforms: data.enabled_platforms,
    notifications_enabled: data.notifications_enabled,
  });
}

export async function PUT(request: NextRequest) {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();

  const { data, error } = await supabase
    .from("user_settings")
    .upsert({
      enabled_platforms: body.enabled_platforms,
      notifications_enabled: body.notifications_enabled,
    })
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({
    enabled_platforms: data.enabled_platforms,
    notifications_enabled: data.notifications_enabled,
  });
}
