-- Prop Log – allow in-app plan edits to sync.
-- Paste into Supabase Dashboard → SQL Editor → Run. Safe to run more than once.
--
-- proplog_data_kind_chk originally allowed only 'session' and 'bodyweight', so a row
-- with kind 'plan' is rejected until this runs. The app keeps the edit on the device
-- and retries the upload on the next sync.
-- Row Level Security is unchanged: each signed-in user can still only see and change
-- their own rows (policies in schema.sql).

alter table public.proplog_data drop constraint if exists proplog_data_kind_chk;
alter table public.proplog_data add  constraint proplog_data_kind_chk
  check (kind in ('session', 'bodyweight', 'plan'));
