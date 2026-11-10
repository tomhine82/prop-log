# Prop Log v14 – visible sync status and retry (base: v13 working tree)

Unzip at the repo root (paths are repo paths). Not pushed. No Supabase changes.

## Why
Nikki completed workouts in the week of 2–8 Nov 2026 that never reached the cloud. The server has no
rows for her after 1 Nov, and her signed-in copy last contacted Supabase on Monday 2 Nov at 08:22 GMT
(a token refresh and a successful pull – no upload). There were no 23514 / 401 / 403 errors on
`proplog_data` for her: the workouts were never sent.

The most likely reason is that she saved them in a copy of the app that was not signed in (Safari and
the Home Screen icon each have their own storage on iPhone). The app said "Session saved ✓" even when
nothing was backed up, and hid the sync pill when signed out, so it was easy to miss.

A rejected `kind = 'plan'` row does **not** block session uploads in v11+: sessions and plans are
pushed in separate batches. The plan-kind SQL still has not been applied (`proplog_data_kind_chk`
still allows only `session` and `bodyweight`).

## Changed files
| file | change |
|---|---|
| `index.html` | Always show the header sync pill when cloud sync is configured, including "☁ not backed up" when signed out. Yellow banner when this phone has sessions that are not backed up, or when a signed-in sync fails – the banner includes the error and a Sign in / Retry button. Saving while signed out says "on this phone only – not backed up". Saving while signed in waits for the upload and warns if it failed. On open, wake, online and once a minute, every signed-in profile retries leftover session/bodyweight rows (not just the person currently on screen). Leftover workout queue items keep an error instead of looking "Synced". |
| `sw.js` | cache `proplog-v14` |
| `tests/test_auth_session.py`, `test_cardio.py`, `test_mark_profile.py`, `test_neil_profile.py`, `test_plan_editor.py`, `test_theme_video.py`, `test_withings_app.py`, `test_reps_capture.py` | expect `proplog-v14` |

## New files
| file | |
|---|---|
| `tests/test_sync_status.py` | banner and pill when signed out with local sessions; save-while-signed-out toast; failed upload shows the error; queued sessions on another profile upload when the app opens |
| `CHANGES.md` | this file |

## Tests
Run the files in `tests/` against http://localhost:8766/prop-log/.

## Notes
* Existing cloud rows are not changed. If Nikki's missing sessions are still on her phone, signing in
  on that same copy (the Safari tab or the Home Screen icon she used) will upload them.
* The Home Screen icon and Safari do not share a sign-in on iPhone.
