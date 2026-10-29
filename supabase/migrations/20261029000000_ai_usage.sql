-- NexLearn v2: AI usage log and daily caps.
--
-- Every chat turn and flashcard request costs the owner's OpenAI credit, so the API
-- asks the database for permission first. The check lives in a `private` schema,
-- which Supabase's public REST API does not expose: students cannot call it directly
-- to fill the shared daily quota or skip their own limit.

create table public.ai_requests (
    id         bigint generated always as identity primary key,
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    kind       text not null check (kind in ('chat', 'flashcards')),
    created_at timestamptz not null default now()
);

create index ai_requests_created_idx on public.ai_requests (created_at);
create index ai_requests_user_created_idx on public.ai_requests (user_id, created_at);

alter table public.ai_requests enable row level security;

-- Students may read their own usage. Rows are only written by private.take_ai_request.
create policy "own ai requests" on public.ai_requests
    for select to authenticated
    using (user_id = (select auth.uid()));

grant select on public.ai_requests to authenticated;

create schema if not exists private;
grant usage on schema private to authenticated;

-- Returns null and records the request when allowed, or a message explaining the limit.
-- Days run midnight to midnight US Eastern.
create function private.take_ai_request(p_kind text, p_user_limit int, p_global_limit int)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    uid uuid := auth.uid();
    day_start timestamptz := date_trunc('day', now() at time zone 'America/New_York') at time zone 'America/New_York';
begin
    if uid is null then
        raise exception 'not signed in';
    end if;
    -- One request at a time per student, so two tabs cannot both slip under the limit.
    perform pg_advisory_xact_lock(hashtext(uid::text));
    if (select count(*) from public.ai_requests where user_id = uid and created_at >= day_start) >= p_user_limit then
        return format('You have used your %s AI requests for today. They reset at midnight Eastern.', p_user_limit);
    end if;
    if (select count(*) from public.ai_requests where created_at >= day_start) >= p_global_limit then
        return 'NexLearn has reached its AI limit for today. Please try again tomorrow.';
    end if;
    insert into public.ai_requests (user_id, kind) values (uid, p_kind);
    return null;
end;
$$;

revoke all on function private.take_ai_request(text, int, int) from public;
grant execute on function private.take_ai_request(text, int, int) to authenticated;
