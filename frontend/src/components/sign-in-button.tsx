"use client";

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export function SignInButton() {
  const [busy, setBusy] = useState(false);

  // The API scales to zero and takes several seconds to boot, so wake it now: it is
  // ready by the time the student is back from Google. The response is not needed.
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { mode: "no-cors" }).catch(() => {});
  }, []);

  async function signIn() {
    setBusy(true);
    const { error } = await createClient().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) setBusy(false);
  }

  return (
    <button
      onClick={signIn}
      disabled={busy}
      className="rounded-lg bg-umd-red px-5 py-3 font-semibold text-white shadow transition hover:bg-umd-red-dark disabled:opacity-60"
    >
      {busy ? "Opening Google..." : "Continue with Google"}
    </button>
  );
}
