-- NexLearn v2, Phase 2a: course materials and "Ask your course".
--
-- A student uploads PDFs to a course. Each page's text is kept, so answers can cite the
-- page they came from, and the text is split into overlapping chunks with an embedding
-- each for retrieval (classic chunk RAG, the baseline the Phase 2 benchmark compares
-- against the OKF study guide).

create table public.documents (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    course_id  uuid not null references public.courses (id) on delete cascade,
    filename   text not null check (length(trim(filename)) > 0),
    sha256     text not null,
    page_count integer not null check (page_count > 0),
    created_at timestamptz not null default now(),
    unique (course_id, sha256)  -- the same file uploaded twice to one course
);

create index documents_course_idx on public.documents (course_id);

create table public.document_pages (
    document_id uuid not null references public.documents (id) on delete cascade,
    user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
    page_no     integer not null check (page_no > 0),
    text        text not null,
    primary key (document_id, page_no)
);

create table public.chunks (
    id          bigint generated always as identity primary key,
    user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
    course_id   uuid not null references public.courses (id) on delete cascade,
    document_id uuid not null references public.documents (id) on delete cascade,
    page_from   integer not null,
    page_to     integer not null,
    text        text not null,
    embedding   extensions.vector(1536) not null,  -- text-embedding-3-small
    check (page_to >= page_from)
);

create index chunks_course_idx on public.chunks (course_id);
-- Cosine distance, matching how OpenAI embeddings are compared. Queries filter by course
-- and set hnsw.iterative_scan so the filter cannot leave a search short of results.
create index chunks_embedding_idx on public.chunks using hnsw (embedding extensions.vector_cosine_ops);

-- Every question asked, with what was retrieved and what it cost: the benchmark and the
-- Phase 4 analytics read from here.
create table public.course_questions (
    id         bigint generated always as identity primary key,
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    course_id  uuid not null references public.courses (id) on delete cascade,
    question   text not null,
    answer     text not null,
    covered    boolean not null,
    approach   text not null check (approach in ('chunks', 'wiki')),
    citations  jsonb not null default '[]',
    retrieved  jsonb not null default '[]',
    latency_ms integer not null,
    tokens     integer,
    created_at timestamptz not null default now()
);

create index course_questions_course_time_idx on public.course_questions (course_id, created_at);

alter table public.documents        enable row level security;
alter table public.document_pages   enable row level security;
alter table public.chunks           enable row level security;
alter table public.course_questions enable row level security;

create policy "own documents" on public.documents
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own document pages" on public.document_pages
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own chunks" on public.chunks
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own course questions" on public.course_questions
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert, update, delete on public.documents, public.document_pages, public.chunks,
    public.course_questions to authenticated;
grant usage on all sequences in schema public to authenticated;

-- Asking a question is one model call, so it counts toward the daily AI caps.
alter table public.ai_requests drop constraint ai_requests_kind_check;
alter table public.ai_requests
    add constraint ai_requests_kind_check check (kind in ('chat', 'flashcards', 'syllabus', 'ask'));
