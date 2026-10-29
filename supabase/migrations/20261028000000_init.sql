-- NexLearn v2: core schema.
--
-- Every table carries user_id and has row-level security (RLS), so the database
-- itself refuses to return another student's rows. The API connects as `postgres`
-- but switches to the `authenticated` role with the caller's JWT claims for each
-- request (see backend/app/db.py), so these policies apply to API queries too.

create extension if not exists vector with schema extensions;  -- used from Phase 2

-- ------------------------------------------------------------------ profiles

create table public.profiles (
    id           uuid primary key references auth.users (id) on delete cascade,
    display_name text,
    timezone     text not null default 'America/New_York',
    created_at   timestamptz not null default now()
);

create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (id, display_name)
    values (new.id, coalesce(new.raw_user_meta_data ->> 'full_name', new.email));
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ------------------------------------------------------------------ courses and assignments

create table public.courses (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    name       text not null,
    created_at timestamptz not null default now(),
    unique (user_id, name)
);

create table public.assignments (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
    course_id      uuid references public.courses (id) on delete set null,
    title          text not null check (length(trim(title)) > 0),
    due_at         timestamptz not null,
    hours_required numeric(5, 2) not null check (hours_required >= 0),
    completion_pct smallint not null default 0 check (completion_pct between 0 and 100),
    source         text not null default 'manual'
                   check (source in ('manual', 'sample', 'csv', 'canvas_feed', 'syllabus')),
    external_id    text,  -- id from the source system, e.g. a Canvas feed UID, for re-imports
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    unique (user_id, source, external_id)
);

create index assignments_user_due_idx on public.assignments (user_id, due_at);

-- Append-only history of progress changes. Phase 4 analytics read from this.
create table public.progress_events (
    id             bigint generated always as identity primary key,
    user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
    assignment_id  uuid not null references public.assignments (id) on delete cascade,
    completion_pct smallint not null check (completion_pct between 0 and 100),
    changed_by     text not null check (changed_by in ('student', 'agent')),
    created_at     timestamptz not null default now()
);

create table public.study_blocks (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
    assignment_id uuid not null references public.assignments (id) on delete cascade,
    starts_at     timestamptz not null,
    ends_at       timestamptz not null,
    created_at    timestamptz not null default now(),
    check (ends_at > starts_at)
);

create index study_blocks_user_start_idx on public.study_blocks (user_id, starts_at);

-- ------------------------------------------------------------------ check-ins and chat

create table public.checkins (
    id         bigint generated always as identity primary key,
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    mood       smallint not null check (mood between 1 and 5),
    energy     smallint not null check (energy between 1 and 5),
    confidence smallint not null check (confidence between 1 and 5),
    note       text,
    created_at timestamptz not null default now()
);

create table public.chat_messages (
    id         bigint generated always as identity primary key,
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    role       text not null check (role in ('user', 'assistant')),
    content    text not null,
    created_at timestamptz not null default now()
);

create index chat_messages_user_time_idx on public.chat_messages (user_id, created_at);

-- ------------------------------------------------------------------ updated_at

create function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create trigger assignments_touch before update on public.assignments
    for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------------ row-level security

alter table public.profiles        enable row level security;
alter table public.courses         enable row level security;
alter table public.assignments     enable row level security;
alter table public.progress_events enable row level security;
alter table public.study_blocks    enable row level security;
alter table public.checkins        enable row level security;
alter table public.chat_messages   enable row level security;

-- (select auth.uid()) instead of auth.uid(): Postgres evaluates it once per query,
-- not once per row.
create policy "own profile" on public.profiles
    for all to authenticated
    using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy "own courses" on public.courses
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own assignments" on public.assignments
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own progress" on public.progress_events
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own study blocks" on public.study_blocks
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own checkins" on public.checkins
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own chat" on public.chat_messages
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage on all sequences in schema public to authenticated;
