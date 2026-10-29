"use client";

import { useEffect, useState } from "react";

import { api, download, json, type Plan, type PlanSettings } from "@/lib/api";
import { DEFAULT_PLAN_SETTINGS, formatClock, formatDay, hoursBetween } from "@/lib/format";
import { Card, ErrorNote, buttonPrimary, buttonSecondary } from "@/components/ui";

const hourLabel = (h: number) => `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;

function groupByDay(plan: Plan) {
  const days = new Map<string, Plan["blocks"]>();
  for (const b of plan.blocks) {
    const key = formatDay(b.starts_at);
    days.set(key, [...(days.get(key) ?? []), b]);
  }
  return [...days.entries()];
}

export function Planner() {
  const [settings, setSettings] = useState<PlanSettings>(DEFAULT_PLAN_SETTINGS);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Plan>("/plan").then(setPlan, (e: Error) => setError(e.message));
  }, []);

  async function makePlan() {
    setBusy(true);
    setError(null);
    try {
      setPlan(await api<Plan>("/plan", { method: "POST", ...json(settings) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const select = "rounded-md border border-line bg-background px-2 py-1 text-sm";
  const hours = Array.from({ length: 24 }, (_, h) => h);

  return (
    <div className="space-y-6">
      <Card title="Plan your next 7 days">
        <p className="mb-4 text-sm text-muted">
          Spreads each assignment&apos;s remaining hours over free time before it is due, earliest deadline first, never
          more than your daily limit.
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <label className="grid gap-1 text-sm">
            Max hours a day
            <select
              className={select}
              value={settings.daily_cap_hours}
              onChange={(e) => setSettings({ ...settings, daily_cap_hours: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5, 6, 7, 8].map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            From
            <select
              className={select}
              value={settings.start_hour}
              onChange={(e) => setSettings({ ...settings, start_hour: Number(e.target.value) })}
            >
              {hours.slice(5, 22).map((h) => (
                <option key={h} value={h}>
                  {hourLabel(h)}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            Until
            <select
              className={select}
              value={settings.end_hour}
              onChange={(e) => setSettings({ ...settings, end_hour: Number(e.target.value) })}
            >
              {hours.filter((h) => h > settings.start_hour).map((h) => (
                <option key={h} value={h}>
                  {hourLabel(h)}
                </option>
              ))}
            </select>
          </label>
          <button onClick={makePlan} disabled={busy} className={buttonPrimary}>
            {busy ? "Planning..." : "Plan the next 7 days"}
          </button>
          {plan && plan.blocks.length > 0 && (
            <button
              onClick={() => download("/plan/ics", "nexlearn_study_plan.ics").catch((e: Error) => setError(e.message))}
              className={buttonSecondary}
            >
              Download for your calendar (.ics)
            </button>
          )}
        </div>
      </Card>

      <ErrorNote message={error} />

      {plan?.shortfalls.map((s) => (
        <p key={s.assignment} className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
          <strong>{s.assignment}</strong>: {s.hours} h will not fit before it is due. Raise the daily limit or widen the
          study window.
        </p>
      ))}

      {plan && plan.blocks.length === 0 && (
        <p className="text-sm text-muted">No study blocks planned yet. Add assignments, then plan your week.</p>
      )}

      {plan && plan.blocks.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {groupByDay(plan).map(([dayLabel, blocks]) => (
            <Card key={dayLabel} title={dayLabel}>
              <ul className="space-y-2 text-sm">
                {blocks.map((b) => (
                  <li key={b.id} className="flex items-baseline justify-between gap-3">
                    <span>
                      <span className="tabular-nums text-muted">
                        {formatClock(b.starts_at)} to {formatClock(b.ends_at)}
                      </span>{" "}
                      <span className="font-medium">{b.title}</span>
                    </span>
                    <span className="tabular-nums text-muted">{hoursBetween(b.starts_at, b.ends_at)} h</span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
      <p className="text-xs text-muted">
        Import the .ics file in Google Calendar (Settings, then Import), Outlook, or Apple Calendar.
      </p>
    </div>
  );
}
