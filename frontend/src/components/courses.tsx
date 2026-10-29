"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, json, type AskResult, type Citation, type Course, type CourseDocument, type PastQuestion } from "@/lib/api";
import { formatDue } from "@/lib/format";
import { Card, ErrorNote, buttonPrimary, buttonSecondary, input } from "@/components/ui";

const pages = (c: { page_from: number; page_to: number }) =>
  c.page_from === c.page_to ? `page ${c.page_from}` : `pages ${c.page_from}-${c.page_to}`;

function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <ul className="mt-3 space-y-1 text-sm">
      {citations.map((c) => (
        <li key={c.n}>
          <details>
            <summary className="cursor-pointer text-muted hover:text-foreground">
              [{c.n}] {c.filename}, {pages(c)}
            </summary>
            <p className="mt-1 whitespace-pre-line rounded-md bg-background px-3 py-2 text-xs text-muted">{c.text}</p>
          </details>
        </li>
      ))}
    </ul>
  );
}

function Answer({ answer, covered, citations }: { answer: string; covered: boolean; citations: Citation[] }) {
  return (
    <div>
      {!covered && (
        <p className="mb-2 rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
          Your materials don&apos;t cover this.
        </p>
      )}
      <div className="chat-md text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
      </div>
      <Citations citations={citations} />
    </div>
  );
}

function Materials({ course, onChanged }: { course: Course; onChanged: () => void }) {
  const [docs, setDocs] = useState<CourseDocument[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<CourseDocument[]>(`/courses/${course.id}/documents`).then(setDocs, (e: Error) => setError(e.message));
  }, [course.id]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const upload = (file: File) =>
    run(async () => {
      const body = new FormData();
      body.append("file", file);
      const doc = await api<CourseDocument>(`/courses/${course.id}/documents`, { method: "POST", body });
      setDocs((list) => [...(list ?? []), doc]);
    });

  const remove = (doc: CourseDocument) =>
    run(async () => {
      await api(`/documents/${doc.id}`, { method: "DELETE" });
      setDocs((list) => list?.filter((d) => d.id !== doc.id) ?? null);
    });

  return (
    <Card
      title={`Materials for ${course.name}`}
      actions={
        <button onClick={() => fileInput.current?.click()} disabled={busy} className={buttonSecondary}>
          {busy ? "Reading and indexing..." : "Upload a PDF"}
        </button>
      }
    >
      <input
        ref={fileInput}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
          e.target.value = "";
        }}
      />
      <ErrorNote message={error} />
      {docs?.length === 0 && (
        <p className="text-sm text-muted">
          Upload slides, notes, or readings. NexLearn keeps each page&apos;s text so answers can cite the page they came from.
        </p>
      )}
      <ul className="divide-y divide-line">
        {docs?.map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className="min-w-0 truncate">
              {d.filename} <span className="text-muted">· {d.page_count} pages</span>
            </span>
            <button onClick={() => remove(d)} disabled={busy} className="text-xs text-muted hover:text-red-600" aria-label={`Delete ${d.filename}`}>
              Delete
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted">PDFs with a text layer, up to 20 MB and 300 pages each, 600 pages per course.</p>
    </Card>
  );
}

function Ask({ course }: { course: Course }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<(AskResult & { question: string }) | null>(null);
  const [history, setHistory] = useState<PastQuestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The parent remounts this per course (key), so there is no earlier result to clear.
    api<PastQuestion[]>(`/courses/${course.id}/questions`).then(setHistory, () => setHistory([]));
  }, [course.id]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    try {
      const answer = await api<AskResult>(`/courses/${course.id}/ask`, { method: "POST", ...json({ question: q }) });
      if (result) {
        setHistory((h) => [{ id: Date.now(), question: result.question, answer: result.answer, covered: result.covered, citations: result.citations, created_at: new Date().toISOString() }, ...h]);
      }
      setResult({ ...answer, question: q });
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const earlier = result ? history : history.slice(1);
  const latest = result ?? (history[0] ? { ...history[0], latency_ms: 0 } : null);

  return (
    <Card title={`Ask about ${course.name}`}>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={1000}
          placeholder="What does the least squares line minimize?"
          aria-label="Your question"
          className={`${input} min-w-0 flex-1`}
        />
        <button type="submit" disabled={busy || course.documents === 0 || question.trim().length < 3} className={buttonPrimary}>
          {busy ? "Reading your materials..." : "Ask"}
        </button>
      </form>
      <p className="mt-2 text-xs text-muted">
        {course.documents === 0
          ? "Upload materials first. Answers come only from them."
          : "Answers come only from this course's materials, with the pages they used. Each question uses one daily AI request."}
      </p>
      <ErrorNote message={error} />
      {latest && (
        <div className="mt-4 border-t border-line pt-4">
          <p className="mb-2 text-sm font-medium">{"question" in latest ? latest.question : ""}</p>
          <Answer answer={latest.answer} covered={latest.covered} citations={latest.citations} />
        </div>
      )}
      {earlier.length > 0 && (
        <details className="mt-4 border-t border-line pt-3">
          <summary className="cursor-pointer text-sm font-medium">Earlier questions ({earlier.length})</summary>
          <ul className="mt-2 space-y-4">
            {earlier.map((h) => (
              <li key={h.id}>
                <p className="text-sm font-medium">
                  {h.question} <span className="text-xs font-normal text-muted">· {formatDue(h.created_at)}</span>
                </p>
                <Answer answer={h.answer} covered={h.covered} citations={h.citations} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

export function Courses() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  const show = useCallback((list: Course[]) => {
    setCourses(list);
    setSelected((current) =>
      current && list.some((c) => c.id === current) ? current : (list.find((c) => c.documents > 0) ?? list[0])?.id ?? null,
    );
  }, []);
  const fail = useCallback((e: Error) => setError(e.message), []);
  const load = useCallback(() => api<Course[]>("/courses").then(show, fail), [show, fail]);

  useEffect(() => {
    api<Course[]>("/courses").then(show, fail);
  }, [show, fail]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      const course = await api<Course>("/courses", { method: "POST", ...json({ name: name.trim() }) });
      setName("");
      await load();
      setSelected(course.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const course = courses?.find((c) => c.id === selected) ?? null;

  return (
    <div className="space-y-6">
      <ErrorNote message={error} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {courses && courses.length > 0 ? (
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">Course</span>
            <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value)} className={`${input} max-w-xs`}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.pages ? ` (${c.pages} pages)` : ""}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="text-sm text-muted">{courses ? "No courses yet. Add one to upload its materials." : "Loading..."}</p>
        )}
        <form onSubmit={add} className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} placeholder="BUDT 758T" aria-label="New course name" className={`${input} w-40`} />
          <button type="submit" disabled={!name.trim()} className={buttonSecondary}>
            Add course
          </button>
        </form>
      </div>
      {course && (
        <>
          <Materials key={`m-${course.id}`} course={course} onChanged={load} />
          <Ask key={`a-${course.id}`} course={course} />
        </>
      )}
    </div>
  );
}
