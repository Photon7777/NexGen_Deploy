-- NexLearn v2, Phase 1: assignments from Canvas and from syllabus PDFs.
--
-- Imported assignments land in public.assignments with source 'canvas_feed' or
-- 'syllabus' and the source's own id in external_id, so a re-import updates rows
-- instead of adding duplicates (see the unique key in 20261028000000_init.sql).

-- ------------------------------------------------------------------ Canvas calendar feed

-- The feed link carries a token that lets anyone holding it read the student's Canvas
-- calendar, so it gets its own table rather than sitting on the profile, and the API
-- never returns it in full.
create table public.canvas_feeds (
    user_id    uuid primary key default auth.uid() references auth.users (id) on delete cascade,
    feed_url   text not null,
    synced_at  timestamptz,
    last_error text,
    -- Canvas UIDs of imported assignments the student deleted, so a sync does not bring them back.
    dismissed  text[] not null default '{}',
    created_at timestamptz not null default now()
);

alter table public.canvas_feeds enable row level security;

create policy "own canvas feed" on public.canvas_feeds
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert, update, delete on public.canvas_feeds to authenticated;

-- ------------------------------------------------------------------ syllabus extraction

-- Reading a syllabus is one model call, so it counts toward the daily AI caps.
alter table public.ai_requests drop constraint ai_requests_kind_check;
alter table public.ai_requests
    add constraint ai_requests_kind_check check (kind in ('chat', 'flashcards', 'syllabus'));
