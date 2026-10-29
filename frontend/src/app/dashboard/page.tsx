import { redirect } from "next/navigation";

import { Dashboard } from "@/components/dashboard";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  if (!data?.claims) redirect("/");
  return <Dashboard email={String(data.claims.email ?? "")} />;
}
