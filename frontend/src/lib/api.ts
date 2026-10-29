import { createClient } from "@/lib/supabase/client";

export type Assignment = {
  id: string;
  title: string;
  course: string | null;
  due_at: string;
  hours_required: number;
  completion_pct: number;
  source: string;
  remaining_hours: number;
  days_left: number;
  priority: number;
  overdue: boolean;
};

export type Block = {
  id: string;
  assignment_id: string;
  title: string;
  course: string | null;
  starts_at: string;
  ends_at: string;
};

export type Plan = { blocks: Block[]; shortfalls: { assignment: string; hours: number }[] };

export type PlanSettings = { daily_cap_hours: number; start_hour: number; end_hour: number };

export type ChatMessage = { role: "user" | "assistant"; content: string; created_at: string };

export type ChatReply = { reply: string; plan_updated: boolean; progress_updated: string[] };

export type Flashcard = { question: string; answer: string };

export type Course = { id: string; name: string; documents: number; pages: number; assignments: number };

export type CourseDocument = { id: string; filename: string; page_count: number; chunks: number; created_at: string };

export type Citation = { n: number; document_id: string; filename: string; page_from: number; page_to: number; text: string };

export type AskResult = { answer: string; covered: boolean; citations: Citation[]; latency_ms: number };

export type PastQuestion = { id: number; question: string; answer: string; covered: boolean; citations: Citation[]; created_at: string };

export type ImportResult = { imported: number; messages: string[]; assignments: Assignment[] };

export type SyllabusItem = {
  title: string;
  kind: string;
  due_at: string | null;
  due_text: string;
  weight_pct: number | null;
  hours_estimate: number;
  evidence: string;
  flags: string[];
};

export type SyllabusDraft = { course: string | null; pages: number; items: SyllabusItem[]; warnings: string[] };

export type CanvasStatus = { connected: boolean; feed: string | null; synced_at: string | null; last_error: string | null };

export type CanvasSync = {
  added: number;
  changed: number;
  unchanged: number;
  skipped_past: number;
  synced_at: string;
  assignments: Assignment[];
};

export type Checkin = {
  id: number;
  mood: number;
  energy: number;
  confidence: number;
  note: string | null;
  created_at: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await createClient().auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError(401, "You are signed out. Sign in again.");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail[0]?.msg : null;
    throw new ApiError(res.status, detail ?? res.statusText);
  }
  return res;
}

/** Call the FastAPI backend with the signed-in student's access token. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authorizedFetch(path, init);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** Fetch an authenticated file (the API needs the token, so a plain link will not do) and save it. */
export async function download(path: string, filename: string): Promise<void> {
  const blob = await (await authorizedFetch(path)).blob();
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });
