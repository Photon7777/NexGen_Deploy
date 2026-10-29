export function Card({ title, actions, children }: { title?: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5">
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mb-4 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
      {message}
    </p>
  );
}

export const buttonPrimary =
  "rounded-md bg-umd-red px-3 py-1.5 text-sm font-medium text-white hover:bg-umd-red-dark disabled:opacity-60";
export const buttonSecondary =
  "rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:bg-background disabled:opacity-60";
export const input =
  "rounded-md border border-line bg-background px-3 py-1.5 text-sm focus:border-umd-red focus:outline-none";
