"use client";

import { useEffect, useState } from "react";

import { api, json, type Assignment, type CanvasStatus, type CanvasSync } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Card, ErrorNote, buttonPrimary, buttonSecondary, input } from "@/components/ui";

const STALE_AFTER_MS = 6 * 3_600_000;

function summary(r: CanvasSync): string {
  const parts = [`${r.added} new`, `${r.changed} updated`, `${r.unchanged} already up to date`];
  const past = r.skipped_past ? ` Skipped ${r.skipped_past} already past due.` : "";
  return `Canvas synced: ${parts.join(", ")}.${past}`;
}

/** Connect a Canvas calendar feed, and keep assignments in step with it. */
export function CanvasConnect({ onSynced }: { onSynced: (assignments: Assignment[]) => void }) {
  const [status, setStatus] = useState<CanvasStatus | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(request: () => Promise<CanvasSync>) {
    setBusy(true);
    setError(null);
    try {
      const result = await request();
      onSynced(result.assignments);
      setNote(summary(result));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStatus(await api<CanvasStatus>("/canvas").catch(() => null));
      setBusy(false);
    }
  }

  const sync = () => run(() => api<CanvasSync>("/canvas/sync", { method: "POST" }));
  const connect = (form: FormData) =>
    run(() => api<CanvasSync>("/canvas", { method: "PUT", ...json({ feed_url: form.get("feed_url") }) }));

  async function disconnect() {
    setBusy(true);
    await api("/canvas", { method: "DELETE" }).catch((e: Error) => setError(e.message));
    setStatus({ connected: false, feed: null, synced_at: null, last_error: null });
    setNote("Canvas disconnected. Assignments already imported stay.");
    setBusy(false);
  }

  useEffect(() => {
    api<CanvasStatus>("/canvas").then((s) => {
      setStatus(s);
      const stale = !s.synced_at || Date.now() - new Date(s.synced_at).getTime() > STALE_AFTER_MS;
      if (s.connected && stale) sync();
    }, (e: Error) => setError(e.message));
    // Runs once on load; `sync` is recreated every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (status === null && !error) return null;

  if (!status?.connected) {
    return (
      <Card title="Import from Canvas">
        <ErrorNote message={error} />
        {note && <p className="mb-3 text-sm text-muted">{note}</p>}
        <p className="mb-3 text-sm text-muted">
          Bring in every due date from ELMS-Canvas and keep them current. In Canvas, open <b>Calendar</b>, click{" "}
          <b>Calendar Feed</b> at the bottom right, and copy the link.
        </p>
        <form action={connect} className="flex flex-col gap-2 sm:flex-row">
          <input
            name="feed_url"
            type="url"
            required
            placeholder="https://umd.instructure.com/feeds/calendars/user_....ics"
            aria-label="Canvas calendar feed link"
            className={`${input} min-w-0 flex-1`}
          />
          <button type="submit" disabled={busy} className={buttonPrimary}>
            {busy ? "Importing..." : "Connect"}
          </button>
        </form>
        <p className="mt-2 text-xs text-muted">
          Anyone with this link can read your Canvas calendar, so NexLearn keeps it private to your account and never shows it
          back in full.
        </p>
      </Card>
    );
  }

  return (
    <Card
      title="Canvas"
      actions={
        <>
          <button onClick={sync} disabled={busy} className={buttonSecondary}>
            {busy ? "Syncing..." : "Sync now"}
          </button>
          <button onClick={disconnect} disabled={busy} className="text-sm text-muted underline hover:text-foreground">
            Disconnect
          </button>
        </>
      }
    >
      <ErrorNote message={error ?? status.last_error} />
      <p className="text-sm text-muted">
        Connected to {status.feed}. {status.synced_at ? `Last synced ${timeAgo(status.synced_at)}.` : "Not synced yet."} NexLearn
        checks Canvas again whenever you open it after six hours. Canvas sets titles and due dates; your hours and progress
        stay yours. A Canvas assignment you delete here stays out of future syncs.
      </p>
      {note && <p className="mt-2 text-sm">{note}</p>}
    </Card>
  );
}
