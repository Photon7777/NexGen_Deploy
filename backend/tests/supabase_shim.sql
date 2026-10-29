-- The parts of Supabase the migrations rely on, for testing against plain Postgres.
-- Supabase provides all of this already; never run this file against a real project.

create schema if not exists auth;
create schema if not exists extensions;

do $$
begin
    if not exists (select from pg_roles where rolname = 'anon') then create role anon nologin; end if;
    if not exists (select from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
    if not exists (select from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end
$$;

create table if not exists auth.users (
    id                 uuid primary key,
    email              text,
    raw_user_meta_data jsonb not null default '{}'::jsonb
);

-- Same definition Supabase uses: the `sub` claim of the JWT set for this transaction.
create or replace function auth.uid()
returns uuid
language sql
stable
as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.sub', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
    )::uuid
$$;

grant usage on schema auth, public, extensions to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;

-- Supabase puts extensions (pgvector) on every role's search path.
do $$
begin
    execute format('alter database %I set search_path = "$user", public, extensions', current_database());
end
$$;
set search_path = "$user", public, extensions;
