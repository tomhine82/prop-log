# Prop Log

Offline-first workout tracker PWA (static HTML/JS, no build step, no CDN) for Tom and Nikki.
Live: https://tomhine82.github.io/prop-log/

## Files

| File | What |
|---|---|
| `index.html` | The whole app (inline CSS/JS) |
| `sw.js` | Service worker (`proplog-v5`): app shell cache-first; page, `config.js` and `plans/*.json` network-first |
| `withings.html` | Withings OAuth callback – forwards `?code=&state=` to the local helper on 127.0.0.1:8765 |
| `manifest.json`, `icon*.{svg,png}` | PWA manifest + icons |
| `plans/tom.json`, `plans/nikki.json` | Coach plans – see `PLAN-FORMAT.md` |
| `config.js` | Public Supabase config for optional cloud sync (generated) |
| `supabase/schema.sql` | Table + Row Level Security for cloud sync – paste into the Supabase SQL Editor |
| `tools/make_config.py` | Generates `config.js` from `SUPABASE_ANON_KEY` |
| `tools/withings_auth.py`, `tools/withings_sync.py`, `tools/withings_common.py` | Withings body-stats sync (runs on the box, not in the browser) |
| `tools/set_password.py` | Set/reset a user's password or create the user (admin API, service key) |
| `supabase/withings.sql` | Optional grant for the sync's service role (only if it reports permission denied) |
| `tests/` | `test_withings_tools.py` (mocked Withings + Supabase), `test_withings_app.py` (Playwright), `test_set_password.py` |

## Data

Everything is stored per person in the browser's localStorage (`proplog.v1:<profile>` etc.) and works
fully offline. JSON export/import is on the Data tab.

## Optional cloud sync (Supabase)

* Sign-in: email + password on the Data tab ("Sign in", or "Create account" the first time; 8+ characters,
  show/hide toggle). No emails are sent (BT rejects the Supabase/Brevo mail), so in Supabase → Authentication →
  Providers → Email, turn **Confirm email** off – otherwise a new account shows "email confirmation is on" and
  can't sign in until it's activated. There is no "forgot password" email: reset or create accounts with
  `NEW_PASSWORD=… python3 tools/set_password.py --email you@example.com` (needs `SUPABASE_SERVICE_KEY`; also
  confirms the account). The signed-in account is linked to the active person only. Old magic links still work.
* Sync: one row per session / bodyweight entry in `public.proplog_data`, last-write-wins by
  `updated_at`, deletes are tombstones (`deleted = true`). Pull on open / return to the app,
  push a moment after every save, offline changes queue and upload when back online.
  The first sign-in merges local and cloud and uploads everything local. Local data is never wiped
  (signing out keeps it; "Delete all data" only clears this device and the cloud copy re-downloads).
* Status: header pill (☁ 07:53 / ☁ offline / ☁ error) and the Data tab ("Synced 07:53", "Offline · 2 changes waiting", "Not signed in").
* The publishable/anon key in `config.js` is public by design; RLS limits every user to their own rows.
  Never put the `service_role` / `sb_secret_` key in this repo.

Regenerate `config.js`:

```bash
SUPABASE_ANON_KEY=sb_publishable_... python3 tools/make_config.py
```

If `config.js` is missing the app simply hides sync.

## Withings body stats (Tom)

Runs on the box with `WITHINGS_CLIENT_ID`, `WITHINGS_CLIENT_SECRET` and `SUPABASE_SERVICE_KEY` in the environment
(never committed). Tokens and state live in `/home/box/.proplog/` (dir 700, files 600).

```bash
python3 tools/withings_auth.py          # once: prints the Withings sign-in URL, catches the callback, saves tokens
python3 tools/withings_sync.py --dry-run
python3 tools/withings_sync.py          # incremental; first run pulls the last 365 days
```

One `bodyweight` row per day (`id` = date) for profile `tom`, latest measurement of the day wins, with
`fat_pct`, `fat_kg`, `muscle_kg`, `hydration_kg`, `bone_kg`, `source: 'withings'`. `updated_at` = time of the
weigh-in, so newest-wins applies: a weight typed or deleted in the app after the weigh-in is kept. The Body tab
shows body fat % / muscle and a "from Withings" tag. Exit code 3 = Withings sign-in needed again.

## Deploy

Push the files to `main` (repo root) – GitHub Pages serves them under `/prop-log/`; all paths are relative.
Bump `CACHE` in `sw.js` when the app shell changes.
