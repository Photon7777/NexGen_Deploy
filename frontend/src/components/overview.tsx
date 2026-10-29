"use client";

import { useEffect, useRef, useState } from "react";

import { api, json, type Assignment } from "@/lib/api";
import { formatDue, relativeDays } from "@/lib/format";
import { CanvasConnect } from "@/components/canvas-connect";
import { SyllabusImport } from "@/components/syllabus-import";
import { Card, ErrorNote, buttonPrimary, buttonSecondary, input } from "@/components/ui";

function urgencyClass(a: Assignment) {
  if (a.overdue || a.days_left <= 1) return "text-red-700 dark:text-red-300";
  if (a.days_left <= 3) return "text-amber-700 dark:text-amber-300";
  return "text-green-700 dark:text-green-300";
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4" title={hint}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 truncate text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function Overview() {
  const [assignments, setAssignments] = useState<Assignment[] | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Assignment[]>("/assignments").then(setAssignments, (e: Error) => setError(e.message));
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const loadSample = () =>
    run(async () => setAssignments(await api<Assignment[]>("/assignments/sample", { method: "POST" })));

  const importCsv = (file: File) =>
    run(async () => {
      const body = new FormData();
      body.append("file", file);
      const result = await api<{ imported: number; messages: string[]; assignments: Assignment[] }>("/assignments/import", {
        method: "POST",
        body,
      });
      setAssignments(result.assignments);
      setNotes([`Imported ${result.imported} assignments.`, ...result.messages]);
    });

  async function saveProgress(a: Assignment) {
    const pct = draft[a.id];
    if (pct === undefined || pct === a.completion_pct) return;
    try {
      const updated = await api<Assignment>(`/assignments/${a.id}`, { method: "PATCH", ...json({ completion_pct: pct }) });
      setAssignments((list) => list?.map((x) => (x.id === a.id ? updated : x)) ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const remove = (a: Assignment) =>
    run(async () => {
      await api(`/assignments/${a.id}`, { method: "DELETE" });
      setAssignments((list) => list?.filter((x) => x.id !== a.id) ?? null);
    });

  async function add(form: FormData) {
    await run(async () => {
      const created = await api<Assignment>("/assignments", {
        method: "POST",
        ...json({
          title: form.get("title"),
          course: form.get("course") || null,
          due_at: new Date(String(form.get("due"))).toISOString(),
          hours_required: Number(form.get("hours")),
        }),
      });
      setAssignments((list) => [...(list ?? []), created].sort((x, y) => x.due_at.localeCompare(y.due_at)));
    });
  }

  const active = assignments?.filter((a) => a.remaining_hours > 0) ?? [];
  const total = assignments?.reduce((s, a) => s + a.hours_required, 0) ?? 0;
  const left = assignments?.reduce((s, a) => s + a.remaining_hours, 0) ?? 0;
  const urgent = [...active].sort((x, y) => y.priority - x.priority)[0];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Due in the next 7 days" value={active.filter((a) => !a.overdue && a.days_left <= 7).length} />
        <Metric label="Study hours left" value={Math.round(left * 10) / 10} />
        <Metric label="Overall progress" value={total ? `${Math.round(((total - left) / total) * 100)}%` : "n/a"} hint="Weighted by hours" />
        <Metric label="Most urgent" value={urgent?.title ?? "All done"} hint="Most hours per day needed to finish on time" />
      </div>

      <CanvasConnect onSynced={setAssignments} />
      <SyllabusImport onSaved={setAssignments} />

      <Card
        title="Your assignments"
        actions={
          <>
            <button onClick={loadSample} disabled={busy} className={buttonSecondary}>
              Load sample assignments
            </button>
            <button onClick={() => fileInput.current?.click()} disabled={busy} className={buttonSecondary}>
              Import CSV
            </button>
            <a href="/nexlearn_template.csv" download className="text-sm text-muted underline hover:text-foreground">
              CSV template
            </a>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) importCsv(file);
                e.target.value = "";
              }}
            />
          </>
        }
      >
        <ErrorNote message={error} />
        {notes.length > 0 && (
          <ul className="mb-4 space-y-1 rounded-md bg-background px-3 py-2 text-sm text-muted">
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
        {assignments === null && !error && <p className="text-sm text-muted">Loading...</p>}
        {assignments?.length === 0 && (
          <p className="text-sm text-muted">No assignments yet. Connect Canvas or import a syllabus above, load the sample set, import a CSV, or add one below.</p>
        )}

        <ul className="divide-y divide-line">
          {assignments?.map((a) => {
            const pct = draft[a.id] ?? a.completion_pct;
            return (
              <li key={a.id} className="grid gap-2 py-3 sm:grid-cols-[1fr_220px_auto] sm:items-center">
                <div className="min-w-0">
                  <div className="truncate font-medium">{a.title}</div>
                  <div className="text-xs text-muted">
                    {a.course ? `${a.course} · ` : ""}
                    Due {formatDue(a.due_at)} · <span className={urgencyClass(a)}>{relativeDays(a.days_left, a.overdue)}</span>
                    {" · "}
                    {a.remaining_hours} of {a.hours_required} h left
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <span className="sr-only">Progress for {a.title}</span>
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={pct}
                    onChange={(e) => setDraft((d) => ({ ...d, [a.id]: Number(e.target.value) }))}
                    onPointerUp={() => saveProgress(a)}
                    onKeyUp={() => saveProgress(a)}
                    className="w-full accent-umd-red"
                  />
                  <span className="w-10 text-right tabular-nums">{pct}%</span>
                </label>
                <button
                  onClick={() => remove(a)}
                  disabled={busy}
                  className="justify-self-start text-xs text-muted hover:text-red-600 sm:justify-self-end"
                  aria-label={`Delete ${a.title}`}
                >
                  Delete
                </button>
              </li>
            );
          })}
        </ul>

        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium">Add an assignment</summary>
          <form action={add} className="mt-3 grid gap-2 sm:grid-cols-[2fr_1fr_1.4fr_0.6fr_auto]">
            <input name="title" required maxLength={200} placeholder="Title" className={input} />
            <input name="course" maxLength={100} placeholder="Course" className={input} />
            <input name="due" type="datetime-local" required aria-label="Due" className={input} />
            <input name="hours" type="number" required min={0} max={500} step={0.5} placeholder="Hours" className={input} />
            <button type="submit" disabled={busy} className={buttonPrimary}>
              Add
            </button>
          </form>
        </details>
      </Card>
    </div>
  );
}
