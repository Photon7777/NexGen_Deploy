"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { createClient } from "@/lib/supabase/client";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/plan", label: "Plan" },
  { href: "/dashboard/chat", label: "Assistant" },
  { href: "/dashboard/tools", label: "Study tools" },
];

export function AppShell({ email, children }: { email: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/");
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link href="/dashboard" className="text-xl font-bold">
          <span className="text-umd-red">Nex</span>Learn AI
        </Link>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span className="hidden sm:inline">{email}</span>
          <button onClick={signOut} className="rounded-md border border-line px-3 py-1.5 hover:bg-surface">
            Sign out
          </button>
        </div>
      </header>
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-line" aria-label="Sections">
        {NAV.map(({ href, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
                active ? "border-umd-red text-foreground" : "border-transparent text-muted hover:text-foreground"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
      <main>{children}</main>
    </div>
  );
}
