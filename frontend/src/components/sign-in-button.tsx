"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export function SignInButton() {
  const [busy, setBusy] = useState(false);

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
