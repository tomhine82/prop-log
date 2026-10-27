-- Prop Log – optional cloud sync schema.
-- Paste into Supabase Dashboard → SQL Editor → Run. Safe to run more than once (idempotent).
--
-- One row per record per person: kind = 'session' | 'bodyweight', id = session id or bodyweight date.
-- Deletes are tombstones (deleted = true) so they sync to other devices.
-- updated_at = when the record was last changed on a device (last-write-wins key).
-- synced_at  = server time the row was last written (used for incremental pulls; set by trigger).

create table if not exists public.proplog_data (
  user_id    uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  profile    text        not null,
  kind       text        not null,
  id         text        not null,
  data       jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  deleted    boolean     not null default false,
  synced_at  timestamptz not null default now(),
  primary key (user_id, profile, kind, id)
);

-- Columns added after the first version (no-ops if they exist).
alter table public.proplog_data add column if not exists deleted   boolean     not null default false;
alter table public.proplog_data add column if not exists synced_at timestamptz not null default now();

-- Sanity constraints (dropped + re-added so the script stays re-runnable).
alter table public.proplog_data drop constraint if exists proplog_data_kind_chk;
alter table public.proplog_data add  constraint proplog_data_kind_chk    check (kind in ('session', 'bodyweight'));
alter table public.proplog_data drop constraint if exists proplog_data_profile_chk;
alter table public.proplog_data add  constraint proplog_data_profile_chk check (profile ~ '^[a-z0-9_-]{1,32}$');
alter table public.proplog_data drop constraint if exists proplog_data_id_chk;
alter table public.proplog_data add  constraint proplog_data_id_chk      check (char_length(id) between 1 and 64);
alter table public.proplog_data drop constraint if exists proplog_data_size_chk;
alter table public.proplog_data add  constraint proplog_data_size_chk    check (pg_column_size(data) < 65536);

create index if not exists proplog_data_pull_idx on public.proplog_data (user_id, profile, synced_at);

-- Server timestamp + last-write-wins guard: an older write never overwrites a newer row.
create or replace function public.proplog_data_before_write()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' and new.updated_at < old.updated_at then
    return null;               -- stale write from a device that was offline: keep the newer row
  end if;
  new.synced_at := now();
  return new;
end;
$$;

drop trigger if exists proplog_data_before_write on public.proplog_data;
create trigger proplog_data_before_write
  before insert or update on public.proplog_data
  for each row execute function public.proplog_data_before_write();

-- Row Level Security: each signed-in user can only see and change their own rows.
alter table public.proplog_data enable row level security;

drop policy if exists "proplog own rows select" on public.proplog_data;
drop policy if exists "proplog own rows insert" on public.proplog_data;
drop policy if exists "proplog own rows update" on public.proplog_data;
drop policy if exists "proplog own rows delete" on public.proplog_data;

create policy "proplog own rows select" on public.proplog_data
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "proplog own rows insert" on public.proplog_data
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "proplog own rows update" on public.proplog_data
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "proplog own rows delete" on public.proplog_data
  for delete to authenticated using ((select auth.uid()) = user_id);

-- Only signed-in users get table access through the API; anonymous visitors get nothing.
revoke all on table public.proplog_data from anon;
grant select, insert, update, delete on table public.proplog_data to authenticated;
