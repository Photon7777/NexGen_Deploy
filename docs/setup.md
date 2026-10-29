# NexLearn v2 setup

v2 is three pieces:

| Piece | What it is | Where it runs |
| --- | --- | --- |
| Database and sign-in | Postgres (with pgvector), Google sign-in, file storage | Supabase |
| API | FastAPI, `backend/` | Google Cloud Run |
| Web app | Next.js, `frontend/` | Vercel |

```
Browser ──(Google sign-in)──> Supabase Auth
   │  session token
   ▼
Next.js on Vercel ──(Bearer token)──> FastAPI on Cloud Run ──(SQL as the signed-in user)──> Supabase Postgres
```

The API checks every token's signature, then runs each request's SQL as the
`authenticated` role with that student's claims, so the row-level security policies
in `supabase/migrations/` decide what each query can see.

Do the steps in order. Steps 1 and 2 take about 15 minutes.

## 1. Supabase project

1. Go to [supabase.com](https://supabase.com), sign in with GitHub, and create a project:
   name `nexlearn`, region **East US (North Virginia)**. Save the database password in a password manager.
2. Open **SQL Editor**, paste all of `supabase/migrations/20261028000000_init.sql`, and click **Run**.
3. Collect these values for later:

   | Value | Where |
   | --- | --- |
   | Project URL | Project Settings, then API Keys (or Data API) |
   | Publishable key (`sb_publishable_...`) | Project Settings, then API Keys |
   | Transaction pooler connection string (port 6543) | **Connect** button at the top, then Transaction pooler |

4. Open Project Settings, then **JWT Keys**. If the project uses the new signing keys
   (ECC or RSA), there is nothing to copy. If it only shows a legacy JWT secret, copy it for
   `SUPABASE_JWT_SECRET`.

## 2. Google sign-in

1. In [Google Cloud Console](https://console.cloud.google.com), pick or create a project for NexLearn.
2. Open **Google Auth Platform**:
   - **Branding:** app name `NexLearn AI`, your email as support and developer contact.
   - **Audience:** External, leave it in **Testing**, and add your Gmail as a test user.
     (Testing allows up to 100 test users. Publishing to everyone comes later.)
   - **Clients:** create a client of type **Web application**.
     - Authorized JavaScript origins: `http://localhost:3000` (add the Vercel URL after step 5).
     - Authorized redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback`
3. In Supabase, open **Authentication**, then **Sign In / Providers**, then **Google**. Turn it
   on and paste the client ID and client secret.
4. In Supabase, open **Authentication**, then **URL Configuration**:
   - Site URL: `http://localhost:3000` for now (switch it to the Vercel URL after step 5).
   - Redirect URLs: `http://localhost:3000/auth/callback`

## 3. Run it locally

```bash
# API, in one terminal
cd backend
cp .env.example .env        # fill in DATABASE_URL and SUPABASE_URL
uv sync
PYTHONPATH=.. uv run uvicorn app.main:app --reload --port 8000

# Web app, in another
cd frontend
cp .env.local.example .env.local   # fill in the Supabase URL and publishable key
pnpm install
pnpm dev
```

Open http://localhost:3000, sign in with Google, and click **Load sample assignments**.

Tests (no Supabase needed, just Docker):

```bash
docker run -d --name nexlearn-testdb -e POSTGRES_PASSWORD=postgres -p 54329:5432 pgvector/pgvector:pg17
cd backend && uv run pytest
```

## 4. Deploy the API to Cloud Run

One-time setup, in your terminal (the database URL is a secret, so type it yourself):

```bash
gcloud config set project <your-project-id>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create nexlearn --repository-format=docker --location=us-east4
printf '%s' '<transaction pooler connection string>' | gcloud secrets create nexlearn-database-url --data-file=-
```

Grant permissions (both accounts are the project's default compute service account,
`<project-number>-compute@developer.gserviceaccount.com`, unless you changed them):

- The **Cloud Build** account deploys, so it needs `roles/run.admin`,
  `roles/iam.serviceAccountUser`, and `roles/artifactregistry.writer`.
- The **Cloud Run runtime** account reads the database URL, so it needs
  `roles/secretmanager.secretAccessor` on `nexlearn-database-url`.

Fill in `backend/cloudrun.env.yaml`, then deploy from the repo root:

```bash
gcloud builds submit --config backend/cloudbuild.yaml .
```

The command prints the service URL (`https://nexlearn-api-...run.app`). Check
`<service URL>/health` returns `{"status":"ok"}`.

## 5. Deploy the web app to Vercel

1. Sign in to [vercel.com](https://vercel.com) with GitHub, then **Add New**, then **Project**,
   and import `Photon7777/NexGen_Deploy`.
2. Set **Root Directory** to `frontend`.
3. Add environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
   and `NEXT_PUBLIC_API_URL` (the Cloud Run URL).
4. Deploy, then wire the new URL back in:
   - Google client: add it to Authorized JavaScript origins.
   - Supabase URL Configuration: make it the Site URL and add `<vercel URL>/auth/callback`.
   - `backend/cloudrun.env.yaml`: add it to `ALLOWED_ORIGINS`, and redeploy the API.

## Secrets: what goes where

| Secret | Lives in | Never in |
| --- | --- | --- |
| Database connection string | `backend/.env` (local), Secret Manager (Cloud Run) | git, Vercel |
| Google client secret | Supabase provider settings | git, frontend |
| Supabase publishable key | `frontend/.env.local`, Vercel | (safe in the browser) |
| OpenAI key (Phase 0b) | `backend/.env`, Secret Manager | frontend |
