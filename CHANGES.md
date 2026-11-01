# Prop Log v13 – reps that looked entered but weren't saved (base: v12, commit 519422a)

Unzip at the repo root (paths are repo paths). Not pushed. No Supabase changes.

## The bug
Since v9 (theme, 28 Oct 18:13 UTC) an empty reps box showed the plan's reps ("10", "10 each side", "30m") as a
placeholder in near-white (#AEBDEB, opacity 1) at the same 18px bold as typed numbers, on the blue card. A box
looked filled in when it was empty. People typed the kg (its placeholder just said "kg") and tapped Save, and only
the kg was stored, with `reps: null`. Nikki's Wed 28 Oct session was logged at 16:53 UTC, before v9 went live, when
placeholders were faint grey, and has every rep. Her Fri 30 Oct session (v9–v11) has kg on every set and no reps.

## Changed files
| file | change |
|---|---|
| `index.html` | **Empty boxes look empty**: weights boxes show a generic faint italic "reps" / "kg" placeholder (all set-grid placeholders are faint, light and italic). The plan target stays in the "Plan:" hint. **"✓ Use plan: 10 reps @ 10 kg in empty boxes"** button per planned exercise fills only empty boxes (leading number of the plan reps: "10 each side" → 10, "30m" → 30, "15-20s" → 15; target kg if set). **Save asks** "N sets have kg but no reps (…)", and Cancel goes back with those boxes highlighted. **Capture**: set boxes listen to `input` and `change`, and Save reads every box again before saving, so a value is kept even if no event fired. **Sync merge**: a newer cloud copy never blanks a set value this device has (same exercise and set position). The merged record gets a new `updatedAt` and is re-uploaded. Real changes from the newer copy still win. **Stale edit**: when the saved session changed after an edit was opened, its values are kept in boxes left empty. Test hooks `__proplog.reps`. |
| `sw.js` | cache `proplog-v13` |
| `tests/test_auth_session.py`, `test_cardio.py`, `test_mark_profile.py`, `test_neil_profile.py`, `test_plan_editor.py`, `test_theme_video.py`, `test_withings_app.py` | expect `proplog-v13` |

## New files
| file | |
|---|---|
| `tests/test_reps_capture.py` | regression (23 checks): placeholders, kg-without-reps prompt, Use plan, type then Save at once with focus still in the box, Save without input events, Nikki's stored sessions load unchanged, merge never blanks values and re-uploads, stale edit. Fails on v12 and passes on v13. |
| `CHANGES.md` | this file |

## Tests
All 10 files in `tests/` pass: auth_session 35/35, cardio 44/44, mark_profile 30/30, neil_profile 35/35, plan_editor 20/20,
reps_capture 23/23, set_password 12/12, theme_video 34/34, withings_app 27/27, withings_tools 55/55.

## Notes
* Existing data isn't changed. Sessions saved with `reps: null` stay as they are. Nothing in the app back-fills them.
* "Add exercise" still pre-fills set 1 with last time's real numbers, and "Copy last set" copies real values. Both are visible values, not placeholders.
