# NexLearn web app

Next.js 16 (App Router) with Supabase sign-in. It talks to the FastAPI backend in `../backend`.

```bash
cp .env.local.example .env.local
pnpm install
pnpm dev
```

- `src/proxy.ts` refreshes the Supabase session and guards `/dashboard`.
- `src/app/auth/callback/route.ts` finishes Google sign-in.
- `src/lib/api.ts` calls the API with the student's access token.

Full setup, including deployment: [`../docs/setup.md`](../docs/setup.md).
