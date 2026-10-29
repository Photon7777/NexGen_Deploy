import { createClient } from "@/lib/supabase/client";

export type Assignment = {
  id: string;
  title: string;
  course: string | null;
  due_at: string;
  hours_required: number;
  completion_pct: number;
  source: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Call the FastAPI backend with the signed-in student's access token. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await createClient().auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError(401, "You are signed out. Sign in again.");

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
