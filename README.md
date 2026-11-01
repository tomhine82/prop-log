# Prop Log

Offline-first workout tracker PWA (static HTML/JS, no build step, no CDN) for Tom, Nikki, Elspeth, Neil and Mark.
Profiles are listed in `PROFILES` in `index.html`; `?p=<id>` (e.g. `?p=elspeth`, `?p=neil`, `?p=mark`) opens a profile directly. `?p=mum` still opens Elspeth.
Live: https://tomhine82.github.io/prop-log/

## Files

| File | What |
|---|---|
| `index.html` | The whole app (inline CSS/JS) |
| `sw.js` | Service worker (`proplog-v11`): app shell cache-first; page, `config.js` and `plans/*.json` network-first |
| `withings.html` | Withings OAuth callback – forwards `?code=&state=` to the local helper on 127.0.0.1:8765 |
| `manifest.json`, `icon*.{svg,png}` | PWA manifest + icons |
| `plans/tom.json`, `plans/nikki.json`, `plans/elspeth.json`, `plans/neil.json`, `plans/mark.json` | Coach plans – see `PLAN-FORMAT.md` (incl. optional per-exercise `video` links) |
| `config.js` | Public Supabase config for optional cloud sync (generated) |
| `supabase/schema.sql` | Table + Row Level Security for cloud sync – paste into the Supabase SQL Editor |
| `supabase/plan_edits.sql` | Lets plan edits sync: widens `proplog_data_kind_chk` to allow `kind = 'plan'` (RLS unchanged) |
| `tools/make_config.py` | Generates `config.js` from `SUPABASE_ANON_KEY` |
| `tools/withings_auth.py`, `tools/withings_sync.py`, `tools/withings_common.py` | Withings body-stats sync (runs on the box, not in the browser) |
| `tools/set_password.py` | Set/reset a user's password or create the user (admin API, service key) |
| `supabase/withings.sql` | Optional grant for the sync's service role (only if it reports permission denied) |
| `tests/` | `test_withings_tools.py` (mocked Withings + Supabase), `test_withings_app.py` (Playwright), `test_set_password.py`, `test_neil_profile.py` (Neil profile, plan + sync scoping; Playwright), `test_mark_profile.py` (Mark profile, plan + sync scoping; Playwright), `test_plan_editor.py` (in-app plan edits, coach banner, sync; Playwright), `test_theme_video.py` (colours, contrast, How-to video links; Playwright), `test_cardio.py` (cardio/timed logging; Playwright), `test_auth_session.py` (staying signed in; Playwright) |

## Look

Burnt orange page (`#C25100`) with royal blue cards, header, tab bar and sheets (`#1F3FA8`, inner boxes/inputs `#183590`),
white text and a light orange accent (`#FFB066`, dark navy `#0B1A4A` text on it). Same in light and dark mode; colours
are CSS variables at the top of `index.html` (and `withings.html`). Every exercise has a **▶ How to** YouTube link.

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
* Sync: one row per session / bodyweight entry / edited plan in `public.proplog_data`, last-write-wins by
  `updated_at`, deletes are tombstones (`deleted = true`). Pull on open / return to the app,
  push a moment after every save, offline changes queue and upload when back online.
  The first sign-in merges local and cloud and uploads everything local. Local data is never wiped
  (signing out keeps it; "Delete all data" only clears this device and the cloud copy re-downloads).
* Plan edits: the Plan tab's **Edit plan** saves that person's plan in `proplog.planEdit:<profile>` and
  syncs one row `kind = 'plan'`, `id = 'current'`. `data` is `{plan, basedOnUpdated, editedAt, coachNote, changes}`
  where `changes` is a human-readable diff from the coach file (see `PLAN-FORMAT.md`). The coach file in
  the repo is not overwritten. Until `supabase/plan_edits.sql` is run, Supabase rejects `kind = 'plan'`
  (check constraint `proplog_data_kind_chk`); the edit stays on the device, the Plan tab says
  "Saved on this device", and the upload is retried on the next sync. Sessions and weigh-ins still sync.
* Staying signed in (v12): the session is kept in `proplog.sync:<profile>` with backup copies in
  `proplog.auth:<profile>` (localStorage) and IndexedDB `proplog-auth`, restored if the main copy disappears.
  Tokens refresh before they expire, when the app is reopened/focused, and every minute while open; only
  one refresh runs at a time (refresh tokens are single-use). Offline, timeouts, rate limits and server
  errors never sign anyone out – only Supabase saying the refresh token itself is invalid/used/revoked does.
  Signing out clears the backups. The app also asks the browser for persistent storage.
  iPhone/iPad: Safari and the Home Screen app have separate storage (sign in once in each), and Safari
  deletes a site's storage after ~7 days without a visit – use the Home Screen app, which is exempt.
* Cardio / timed exercises (v12): log time, km, kcal and average HR instead of reps × kg; see `PLAN-FORMAT.md`.
* Status: header pill (☁ 07:53 / ☁ offline / ☁ error) and the Data tab ("Synced 07:53", "Offline · 2 changes waiting", "Not signed in").
* The publishable/anon key in `config.js` is public by design; RLS limits every user to their own rows.
  Never put the `service_role` / `sb_secret_` key in this repo.

Regenerate `config.js`:

```bash
SUPABASE_ANON_KEY=sb_publishable_... python3 tools/make_config.py
```

If `config.js` is missing the app simply hides sync.

## Withings body stats (Tom and Nikki)

Runs on the box with `WITHINGS_CLIENT_ID`, `WITHINGS_CLIENT_SECRET` and `SUPABASE_SERVICE_KEY` in the environment
(never committed). Tokens and state live in `/home/box/.proplog/` (dir 700, files 600).

One Withings account can hold several Withings *users* (Tom, Nikki). The Withings API grants access per user, so
each Prop Log profile is linked with its own consent and gets its own token file:

| profile | token | state | sign-in URL file |
|---|---|---|---|
| `tom` | `withings_tokens.json` | `withings_state.json` | `withings_authorize_url.txt` |
| `nikki` | `withings_tokens.nikki.json` | `withings_state.nikki.json` | `withings_authorize_url.nikki.txt` |

```bash
python3 tools/withings_auth.py                     # Tom: prints the sign-in URL, catches the callback, saves tokens
python3 tools/withings_auth.py --profile nikki --no-print-url --timeout 3600
                                                   # Nikki: URL only written to withings_authorize_url.nikki.txt;
                                                   # on the Withings consent screen pick Nikki
python3 tools/withings_sync.py --dry-run
python3 tools/withings_sync.py                     # every linked profile; incremental; first run pulls 365 days
python3 tools/withings_sync.py --profile nikki     # one profile only
```

If a consent comes back for a Withings user that is already linked to another profile (wrong person picked),
the auth helper keeps that fresh token for the profile it belongs to and exits 5 without linking anything.
The sync also refuses (exit 5) to copy one Withings user into two profiles. Each profile's rows are owned by
that person's Supabase account: Tom's by his email, other profiles by the account that already owns that
profile's rows (or `--profile p --user-id <uuid>`), so Nikki sees them once she is signed in on her profile.

One `bodyweight` row per day (`id` = date) for the linked profile, latest measurement of the day wins, with
`fat_pct`, `fat_kg`, `muscle_kg`, `hydration_kg`, `bone_kg`, `source: 'withings'`. `updated_at` = time of the
weigh-in, so newest-wins applies: a weight typed or deleted in the app after the weigh-in is kept. The Body tab
shows body fat % / muscle and a "from Withings" tag. Exit code 3 = Withings sign-in needed again (the message
names the profile). Weigh-ins the scale could not attribute show up in the Withings app as unknown/ambiguous
measurements and are skipped until assigned to a person there.

## Deploy

Push the files to `main` (repo root) – GitHub Pages serves them under `/prop-log/`; all paths are relative.
Bump `CACHE` in `sw.js` when the app shell changes.
