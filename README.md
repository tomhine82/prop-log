# Prop Log

Offline-first workout tracker PWA (static HTML/JS, no build step, no CDN) for Tom and Nikki.
Live: https://tomhine82.github.io/prop-log/

## Files

| File | What |
|---|---|
| `index.html` | The whole app (inline CSS/JS) |
| `sw.js` | Service worker (`proplog-v3`): app shell cache-first; page, `config.js` and `plans/*.json` network-first |
| `manifest.json`, `icon*.{svg,png}` | PWA manifest + icons |
| `plans/tom.json`, `plans/nikki.json` | Coach plans – see `PLAN-FORMAT.md` |
| `config.js` | Public Supabase config for optional cloud sync (generated) |
| `supabase/schema.sql` | Table + Row Level Security for cloud sync – paste into the Supabase SQL Editor |
| `tools/make_config.py` | Generates `config.js` from `SUPABASE_ANON_KEY` |

## Data

Everything is stored per person in the browser's localStorage (`proplog.v1:<profile>` etc.) and works
fully offline. JSON export/import is on the Data tab.

## Optional cloud sync (Supabase)

* Sign-in: each person enters their own email on the Data tab, gets a 6-digit code by email and types it
  in (works inside the installed iPhone app; a magic link also works as a fallback if the email
  template still contains a link). The signed-in account is linked to the active person only.
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

## Deploy

Push the files to `main` (repo root) – GitHub Pages serves them under `/prop-log/`; all paths are relative.
Bump `CACHE` in `sw.js` when the app shell changes.
