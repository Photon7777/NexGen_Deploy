"use client";

import { useEffect, useState } from "react";

import { api, json, type Checkin, type Flashcard } from "@/lib/api";
import { formatDue } from "@/lib/format";
import { Card, ErrorNote, buttonPrimary, buttonSecondary, input } from "@/components/ui";

export function Flashcards() {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(6);
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCards(await api<Flashcard[]>("/flashcards", { method: "POST", ...json({ topic, count }) }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Flashcards">
      <form onSubmit={generate} className="mb-4 flex flex-wrap gap-2">
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          required
          minLength={2}
          maxLength={200}
          placeholder="Topic, e.g. linear regression assumptions"
          aria-label="Topic"
          className={`${input} min-w-0 flex-1`}
        />
        <select value={count} onChange={(e) => setCount(Number(e.target.value))} aria-label="Number of cards" className={input}>
          {[3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
            <option key={n} value={n}>
              {n} cards
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy} className={buttonPrimary}>
          {busy ? "Writing..." : "Generate"}
        </button>
      </form>
      <ErrorNote message={error} />
      <div className="space-y-2">
        {cards.map((c, i) => (
          <details key={i} className="rounded-md border border-line bg-background px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium">{c.question}</summary>
            <p className="mt-2 text-sm text-muted">{c.answer}</p>
          </details>
        ))}
      </div>
    </Card>
  );
}

export function Pomodoro() {
  const [minutes, setMinutes] = useState(25);
  const [endsAt, setEndsAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (endsAt === null) return;
    const timer = setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= endsAt) {
        setEndsAt(null);
        setFinished(true);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [endsAt]);

  const left = endsAt === null ? minutes * 60 : Math.max(0, Math.round((endsAt - now) / 1000));
  const progress = endsAt === null ? 0 : 1 - left / (minutes * 60);

  return (
    <Card title="Pomodoro">
      <div className="text-5xl font-semibold tabular-nums" role="timer" aria-live="off">
        {String(Math.floor(left / 60)).padStart(2, "0")}:{String(left % 60).padStart(2, "0")}
      </div>
      <div className="my-3 h-2 overflow-hidden rounded-full bg-background">
        <div className="h-full bg-umd-red transition-[width]" style={{ width: `${progress * 100}%` }} />
      </div>
      {finished && <p className="mb-3 text-sm text-green-700 dark:text-green-300">Session complete. Take a five-minute break.</p>}
      <div className="flex flex-wrap items-center gap-2">
        {endsAt === null ? (
          <>
            <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} aria-label="Minutes" className={input}>
              {[15, 20, 25, 30, 45, 50].map((m) => (
                <option key={m} value={m}>
                  {m} min
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                const t = Date.now();
                setNow(t);
                setFinished(false);
                setEndsAt(t + minutes * 60_000);
              }}
              className={buttonPrimary}
            >
              Start focus
            </button>
          </>
        ) : (
          <button onClick={() => setEndsAt(null)} className={buttonSecondary}>
            Stop
          </button>
        )}
      </div>
    </Card>
  );
}

const SCALE = [1, 2, 3, 4, 5];

function ScaleInput({ name, label }: { name: string; label: string }) {
  return (
    <fieldset className="grid gap-1">
      <legend className="text-sm">{label}</legend>
      <div className="flex gap-1">
        {SCALE.map((v) => (
          <label key={v} className="cursor-pointer">
            <input type="radio" name={name} value={v} defaultChecked={v === 3} className="peer sr-only" />
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line text-sm peer-checked:border-umd-red peer-checked:bg-umd-red peer-checked:text-white peer-focus-visible:ring-2 peer-focus-visible:ring-umd-red">
              {v}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function Checkins() {
  const [checkins, setCheckins] = useState<Checkin[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Checkin[]>("/checkins").then(setCheckins, (e: Error) => setError(e.message));
  }, []);

  async function save(form: FormData) {
    setError(null);
    try {
      const created = await api<Checkin>("/checkins", {
        method: "POST",
        ...json({
          mood: Number(form.get("mood")),
          energy: Number(form.get("energy")),
          confidence: Number(form.get("confidence")),
          note: form.get("note") || null,
        }),
      });
      setCheckins((list) => [...(list ?? []), created]);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const recent = (checkins ?? []).slice(-7).reverse();

  return (
    <Card title="Daily check-in">
      <form action={save} className="mb-4 grid gap-3">
        <div className="flex flex-wrap gap-4">
          <ScaleInput name="mood" label="Mood" />
          <ScaleInput name="energy" label="Energy" />
          <ScaleInput name="confidence" label="Confidence" />
        </div>
        <div className="flex gap-2">
          <input name="note" maxLength={500} placeholder="Note (optional)" aria-label="Note" className={`${input} flex-1`} />
          <button type="submit" className={buttonPrimary}>
            Save
          </button>
        </div>
      </form>
      <ErrorNote message={error} />
      {recent.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="py-1 font-medium">When</th>
              <th className="py-1 font-medium">Mood</th>
              <th className="py-1 font-medium">Energy</th>
              <th className="py-1 font-medium">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {recent.map((c) => (
              <tr key={c.id} className="border-t border-line" title={c.note ?? undefined}>
                <td className="py-1.5 pr-2 text-muted">{formatDue(c.created_at)}</td>
                {[c.mood, c.energy, c.confidence].map((v, i) => (
                  <td key={i} className="py-1.5 pr-2">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-background">
                        <div className="h-full bg-umd-red" style={{ width: `${(v / 5) * 100}%` }} />
                      </div>
                      <span className="tabular-nums">{v}</span>
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-3 text-xs text-muted">Only you can see your check-ins.</p>
    </Card>
  );
}
