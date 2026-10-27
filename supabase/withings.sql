-- Prop Log – Withings body-stats sync (tools/withings_sync.py). OPTIONAL, safe to re-run.
--
-- The sync writes with the project's secret / service_role key. service_role bypasses RLS, and the
-- proplog_data_before_write trigger + check constraints accept its rows as-is (user_id is sent explicitly,
-- kind = 'bodyweight', id = 'YYYY-MM-DD', small jsonb). Supabase normally grants service_role full access to
-- tables in public, so this file is only needed if the sync reports "permission denied" (42501) – e.g. on
-- projects where default Data API grants were turned off. It changes nothing else.
grant usage on schema public to service_role;
grant select, insert, update on table public.proplog_data to service_role;
