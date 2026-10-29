"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, type Assignment } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

const due = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "America/New_York",
});

export function Dashboard({ email }: { email: string }) {
  const router = useRouter();
  const [assignments, setAssignments] = useState<Assignment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Assignment[]>("/assignments").then(setAssignments, (e: Error) => setError(e.message));
  }, []);

  async function loadSample() {
    setBusy(true);
    setError(null);
    try {
      setAssignments(await api<Assignment[]>("/assignments/sample", { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/");
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">
          <span className="text-umd-red">Nex</span>Learn AI
        </h1>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span>{email}</span>
          <button onClick={signOut} className="rounded-md border border-line px-3 py-1.5 hover:bg-surface">
            Sign out
          </button>
        </div>
      </header>

      <section className="rounded-xl border border-line bg-surface p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Your assignments</h2>
          <button
            onClick={loadSample}
            disabled={busy}
            className="rounded-md bg-umd-red px-3 py-1.5 text-sm font-medium text-white hover:bg-umd-red-dark disabled:opacity-60"
          >
            {busy ? "Loading..." : "Load sample assignments"}
          </button>
        </div>

        {error && <p className="mb-4 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

        {assignments === null && !error && <p className="text-sm text-muted">Loading...</p>}

        {assignments?.length === 0 && (
          <p className="text-sm text-muted">No assignments yet. Load the sample set to see how NexLearn works.</p>
        )}

        {assignments && assignments.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-muted">
                <tr className="border-b border-line">
                  <th className="py-2 pr-4 font-medium">Assignment</th>
                  <th className="py-2 pr-4 font-medium">Course</th>
                  <th className="py-2 pr-4 font-medium">Due</th>
                  <th className="py-2 pr-4 text-right font-medium">Hours</th>
                  <th className="py-2 text-right font-medium">Done</th>
                </tr>
              </thead>
              <tbody>
                {assignments.map((a) => (
                  <tr key={a.id} className="border-b border-line last:border-0">
                    <td className="py-2 pr-4 font-medium">{a.title}</td>
                    <td className="py-2 pr-4 text-muted">{a.course ?? "-"}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">{due.format(new Date(a.due_at))}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{a.hours_required}</td>
                    <td className="py-2 text-right tabular-nums">{a.completion_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
