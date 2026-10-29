import { redirect } from "next/navigation";

import { SignInButton } from "@/components/sign-in-button";
import { createClient } from "@/lib/supabase/server";

export default async function Home({ searchParams }: PageProps<"/">) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  if (data?.claims) redirect("/dashboard");
  const { error } = await searchParams;

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <h1 className="text-4xl font-bold tracking-tight">
        <span className="text-umd-red">Nex</span>Learn AI
      </h1>
      <p className="text-lg text-muted">
        Turn your syllabus into a study plan you can actually follow. Built for University of Maryland students.
      </p>
      <SignInButton />
      {error && <p className="text-sm text-red-600 dark:text-red-400">Sign-in did not complete. Please try again.</p>}
    </main>
  );
}
