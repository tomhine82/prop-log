# Prop Log v12 – changes (base: v11, commit 208c7aa)

Unzip at the repo root (paths are repo paths). Not pushed.

## Changed files
| file | change |
|---|---|
| `index.html` | **Cardio / timed exercises**: per-exercise mode "Reps & kg" / "⏱ Time & distance" (auto from the name: run, jog, bike/cycle/turbo/assault bike, rower/rowing, ski erg, swim, walk, treadmill, conditioning, sprint, interval…; weights names such as "Dumbbell row", "Seated cable row", "Walking lunge" stay reps & kg); entries of time (mm:ss, h:mm:ss or minutes), km, kcal, avg HR; live total + best pace; last-time placeholders; History line (⏱ km · time · kcal · HR); Progress view for cardio (total km/time, best pace, chart, PBs); share text; plan `type`/`metrics`/`duration`/`distanceKm`; plan editor "Log as" + Duration + Distance km; Start-from-plan opens cardio exercises in cardio mode. Weights exercises and old sessions keep the v11 format. **Staying signed in**: session backups in localStorage `proplog.auth:<profile>` + IndexedDB `proplog-auth` (restored if the main copy is lost), single-flight token refresh, proactive refresh (5 min margin) on focus / visibilitychange / pageshow / online + every 60 s while open, REST 401 → refresh + retry, sign-out only for a real invalid/used/revoked refresh token (never offline/timeouts/429/5xx), backups cleared on sign-out, `navigator.storage.persist()`. |
| `sw.js` | cache `proplog-v12` |
| `PLAN-FORMAT.md` | cardio fields (`type`, `metrics`, `duration`, `distanceKm`) and the stored cardio session format |
| `README.md` | staying signed in (incl. iOS 7-day Safari storage note), cardio, Withings per-profile (Tom + Nikki) |
| `tools/withings_common.py` | profiles table, per-profile token/state/URL file paths, `profile_for_userid` |
| `tools/withings_auth.py` | `--profile` (tom default); per-profile URL file; refuses a consent whose Withings user is already linked to another profile (keeps that fresh token for the right profile, exit 5); success page names the person |
| `tools/withings_sync.py` | syncs every linked profile (or `--profile`), each Withings user → its own profile rows owned by that person's Supabase account; per-profile state; duplicate-link guard (exit 5); one profile failing doesn't stop the others; re-auth hint names the profile |
| `tests/test_mark_profile.py`, `tests/test_neil_profile.py`, `tests/test_plan_editor.py`, `tests/test_theme_video.py` | expect `proplog-v12` |
| `tests/test_withings_app.py` | `proplog-v12`; Nikki's Withings rows show on her Body tab via her own sign-in |
| `tests/test_withings_tools.py` | per-profile auth/sync tests (Nikki link, wrong-person refusal, duplicate guard, per-profile failure); fixed a time-of-day bug (a 06:00 "today" reading was in the future before 6 am) |

## New files
| file | |
|---|---|
| `tests/test_cardio.py` | cardio helpers, Log UI, save format, old sessions untouched, History, Progress, sync payload, share, plan editor, start from plan (44 checks) |
| `tests/test_auth_session.py` | backups + restore (localStorage / IndexedDB), no sign-out on offline/500/503/429/other 400, sign-out on invalid/used token, single-flight, focus/visibility refresh, 401 retry (35 checks) |
| `CHANGES.md` | this file |

## Tests
All 9 files in `tests/` pass: auth_session 35/35, cardio 44/44, mark_profile 30/30, neil_profile 35/35,
plan_editor 20/20, set_password 12/12, theme_video 34/34, withings_app 27/27, withings_tools 55/55.

## Notes
* A device still on v11 that edits and re-saves a v12 cardio session would drop the cardio numbers – update every device (reopen the app twice) before logging cardio.
* Box: the same three `tools/withings_*.py` were also installed in `/workspace/workout-tracker/tools` (old copies in `/workspace/tools-backup-v11`).
