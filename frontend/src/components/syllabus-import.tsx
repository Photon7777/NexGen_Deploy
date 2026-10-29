"use client";

import { useRef, useState } from "react";

import { api, json, type Assignment, type ImportResult, type SyllabusDraft } from "@/lib/api";
import { Card, ErrorNote, buttonPrimary, buttonSecondary, input } from "@/components/ui";

// Items the model may have invented or been told to add, and ones already over, start unticked.
// The flag texts come from backend/app/syllabus.py.
const UNTICK = ["Not found in the PDF", "Comes from text aimed at AI tools, not the course", "Already past"];

type Row = { include: boolean; title: string; due: string; hours: number };

/** An ISO time as a datetime-local value in the browser's time zone (what the Add form uses too). */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Upload a syllabus PDF, review what the model found, and save the rows the student keeps. */
export function SyllabusImport({ onSaved }: { onSaved: (assignments: Assignment[]) => void }) {
  const [draft, setDraft] = useState<SyllabusDraft | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [course, setCourse] = useState("");
  const [busy, setBusy] = useState<"reading" | "saving" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function read(file: File) {
    setBusy("reading");
    setError(null);
    setNote(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const result = await api<SyllabusDraft>("/syllabus/extract", { method: "POST", body });
      setDraft(result);
      setCourse(result.course ?? "");
      setRows(
        result.items.map((i) => ({
          include: !i.flags.some((f) => UNTICK.includes(f)),
          title: i.title,
          due: toLocalInput(i.due_at),
          hours: i.hours_estimate,
        })),
      );
      if (result.items.length === 0) setNote("No graded work found in that PDF.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const chosen = rows.filter((r) => r.include);
  const missingDates = chosen.filter((r) => !r.due).length;

  async function save() {
    setBusy("saving");
    setError(null);
    try {
      const result = await api<ImportResult>("/syllabus/save", {
        method: "POST",
        ...json({
          course: course.trim() || null,
          items: chosen.map((r) => ({ title: r.title, due_at: new Date(r.due).toISOString(), hours_required: r.hours })),
        }),
      });
      onSaved(result.assignments);
      setNote(`Saved ${result.imported} assignments from the syllabus.`);
      setDraft(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const update = (index: number, change: Partial<Row>) =>
    setRows((list) => list.map((r, i) => (i === index ? { ...r, ...change } : r)));

  const picker = (
    <input
      ref={fileInput}
      type="file"
      accept=".pdf,application/pdf"
      className="hidden"
      onChange={(e) => {
        const file = e.target.files?.[0];
        if (file) read(file);
        e.target.value = "";
      }}
    />
  );

  if (!draft) {
    return (
      <Card
        title="Import a syllabus"
        actions={
          <button onClick={() => fileInput.current?.click()} disabled={busy !== null} className={buttonSecondary}>
            {busy === "reading" ? "Reading your syllabus..." : "Choose a PDF"}
          </button>
        }
      >
        {picker}
        <ErrorNote message={error} />
        <p className="text-sm text-muted">
          {note ??
            "NexLearn reads the graded work and due dates out of a syllabus PDF, then lets you check every row before saving. Uses one of your daily AI requests."}
        </p>
      </Card>
    );
  }

  return (
    <Card
      title={`Review: ${draft.items.length} items found in ${draft.pages} ${draft.pages === 1 ? "page" : "pages"}`}
      actions={
        <>
          <button onClick={save} disabled={busy !== null || chosen.length === 0 || missingDates > 0} className={buttonPrimary}>
            {busy === "saving" ? "Saving..." : `Save ${chosen.length} ${chosen.length === 1 ? "assignment" : "assignments"}`}
          </button>
          <button onClick={() => setDraft(null)} disabled={busy !== null} className={buttonSecondary}>
            Cancel
          </button>
        </>
      }
    >
      <ErrorNote message={error} />
      {draft.warnings.map((w) => (
        <p key={w} role="alert" className="mb-3 rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
          {w}
        </p>
      ))}
      <label className="mb-3 flex items-center gap-2 text-sm">
        <span className="text-muted">Course</span>
        <input value={course} onChange={(e) => setCourse(e.target.value)} maxLength={100} className={`${input} w-48`} />
      </label>
      <p className="mb-3 text-xs text-muted">
        Check each row against your syllabus. Rows marked in amber need a look; ones that are past or that NexLearn could not
        find in the PDF start unticked.
        {missingDates > 0 && ` Add a date to the ${missingDates} ticked ${missingDates === 1 ? "row" : "rows"} without one to save.`}
      </p>
      <ul className="divide-y divide-line">
        {draft.items.map((item, i) => {
          const row = rows[i];
          return (
            <li key={i} className={`grid gap-2 py-3 sm:grid-cols-[auto_1fr_200px_90px] sm:items-start ${row.include ? "" : "opacity-60"}`}>
              <input
                type="checkbox"
                checked={row.include}
                onChange={(e) => update(i, { include: e.target.checked })}
                aria-label={`Include ${row.title}`}
                className="mt-2 accent-umd-red"
              />
              <div className="min-w-0 space-y-1">
                <input value={row.title} onChange={(e) => update(i, { title: e.target.value })} maxLength={200} aria-label="Title" className={`${input} w-full`} />
                <div className="text-xs text-muted">
                  {item.kind}
                  {item.weight_pct !== null && ` · ${item.weight_pct}% of grade`}
                  {item.due_text && ` · syllabus says "${item.due_text}"`}
                </div>
                {item.flags.length > 0 && <div className="text-xs text-amber-700 dark:text-amber-300">{item.flags.join(". ")}.</div>}
                {item.evidence && <div className="truncate text-xs italic text-muted" title={item.evidence}>&ldquo;{item.evidence}&rdquo;</div>}
              </div>
              <input
                type="datetime-local"
                value={row.due}
                onChange={(e) => update(i, { due: e.target.value })}
                required={row.include}
                aria-label={`Due date for ${row.title}`}
                className={input}
              />
              <label className="flex items-center gap-1 text-sm">
                <input
                  type="number"
                  min={0}
                  max={500}
                  step={0.5}
                  value={row.hours}
                  onChange={(e) => update(i, { hours: Number(e.target.value) })}
                  aria-label={`Hours for ${row.title}`}
                  className={`${input} w-16`}
                />
                h
              </label>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
