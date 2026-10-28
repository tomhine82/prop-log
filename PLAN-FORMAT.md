# Prop Log plan format

Each person has their own plan file next to `index.html`:

| Person | File |
|---|---|
| Tom | `plans/tom.json` |
| Nikki | `plans/nikki.json` |
| Elspeth | `plans/elspeth.json` |
| Neil | `plans/neil.json` |
| Mark | `plans/mark.json` |

The app loads the **active person's** file every time it opens (and when it comes back to the
foreground after a minute or more). It fetches network-first with `cache: 'no-store'`, so a new
commit to the repo shows up the next time the app is opened. Offline, it uses the last copy it saw
(service-worker cache, then a copy kept in localStorage) and says "Offline – showing saved copy".

To update a plan: edit the JSON file, bump `updated`, and push to `main`. No app change needed.
Plans are served from the repo, not from cloud sync – cloud sync (see README.md) only carries
logged sessions and bodyweight. A session's link to its plan day (`session.plan`) syncs with it,
so ADDED/SKIPPED flags in the coach summary are the same on every device.

## Schema

```jsonc
{
  "version": 1,                      // schema version (currently 1)
  "athlete": "Tom",                  // display only
  "title": "In-season week",         // optional, short
  "author": "Coach bot",             // optional
  "updated": "2026-10-27",           // REQUIRED, ISO date (YYYY-MM-DD) – shown in the app
  "notes": "General guidance…",      // optional, shown at the top of the Plan tab
  "placeholder": false,              // optional; true = "no real plan yet" (nothing to start/compare)
  "weeks": [                         // REQUIRED, at least one week
    {
      "label": "Week 1",             // shown above the days
      "startDate": "2026-10-26",     // optional ISO date (any day in that week; Monday-based weeks)
      "days": [
        {
          "day": "Mon",              // Mon Tue Wed Thu Fri Sat Sun (full names also accepted)
          "title": "Lower strength", // short name for the day
          "type": "Lower strength",  // one of the app's session types (below); anything else → "Other"
          "focus": "Squat + hinge",  // optional one-liner shown in the collapsed day
          "notes": "Warm-up …",      // optional day notes
          "exercises": [             // may be empty (runs, rugby, match, rest)
            {
              "name": "Back squat",  // match names already used in the log so history/PBs line up
              "sets": 4,             // integer – number of empty set rows pre-filled
              "reps": "5",           // STRING: "5", "8-10", "10/leg", "30s", "30m"
              "targetKg": null,      // number or null (unknown / bodyweight)
              "rest": "3 min",       // optional string
              "notes": "RPE 8",      // optional string
              "video": "https://www.youtube.com/watch?v=XXXXXXXXXXX"  // optional – see "How-to videos"
            }
          ]
        }
      ]
    }
  ]
}
```

Session types: `Lower strength`, `Upper strength`, `Running conditioning`, `Ride`,
`Rugby training`, `Match`, `Other`.

### Which week is "this week"?

* Weeks **with** `startDate`: the latest week whose start (Monday of that date) is on or before
  this Monday. Before the first one, the first week is shown.
* Weeks **without** `startDate`: one week repeats every week. With several undated weeks they
  rotate weekly, starting with the first week in the week of `updated`.
* Days missing from a week show as "Rest".

## How the app uses it

* **Plan tab** – this week's Mon–Sun, today highlighted and expanded, a "✓ Logged" mark on days
  already logged, and the `updated` date.
* **Start this session** – opens the Log tab with the day's type and each planned exercise with
  `sets` empty rows. Target reps / kg appear as placeholders plus a "Plan: 4 × 5 @ 140 kg · rest 3 min"
  hint, so only actual reps and kg need typing. Extra sets and exercises can still be added.
  The saved session remembers which plan day it came from (`session.plan`).
* **Share with coach** – compares each session with its plan day (or, for sessions logged by hand,
  the plan day for that weekday when the session type matches):
  * `ADDED: <exercise>` – logged but not in the plan
  * `SKIPPED: <exercises>` – planned but no sets logged
  * `ADDED session (not in plan)` – a session that matches no plan day
  * `MISSED planned sessions:` – past plan days with exercises and nothing logged (only counted from
    the plan's `updated` date onward)

## How-to videos

Every exercise shows a small **▶ How to** link next to its name on the Plan tab and in the Log tab, which opens
YouTube in a new tab (or the YouTube app on a phone).

* By default the link is a YouTube search built from the exercise name:
  `https://www.youtube.com/results?search_query=` + URL-encoded `"<name> exercise form"`
  (e.g. `Seated cable row` → `...?search_query=Seated%20cable%20row%20exercise%20form`). This also works for
  exercises typed in by hand, which have no plan entry.
* To point at one specific video, add `"video": "<url>"` to the exercise in the plan. It must be a full `https://`
  link on `youtube.com` or `youtu.be` (e.g. `https://www.youtube.com/watch?v=…`, `https://youtu.be/…`,
  `https://www.youtube.com/shorts/…`); anything else is ignored and the search link is used instead.
* A `video` also applies in the Log tab to an exercise added by hand with the same name (case-insensitive) as a
  plan exercise that has one.

## Edits from the athlete

The Plan tab has **Edit plan**. The athlete can change exercise name, sets, reps, target kg, rest and notes,
add, remove and reorder exercises, change a day's title or type, mark a day as rest, and write a free-text
**Note to my coach**. Save replaces that person's plan inside the app (Plan tab, Start this session, How to
links) and shows an **Edited by you** tag. **Reset to coach's plan** throws the edits away.

The coach file in this repo is not changed. Edits live on the device at `proplog.planEdit:<profile>` and,
once `supabase/plan_edits.sql` has been run, sync as one `proplog_data` row:

| column | value |
|---|---|
| `kind` | `plan` |
| `id` | `current` |
| `profile` | `tom`, `nikki`, `elspeth`, `neil`, `mark`, … |
| `deleted` | `true` after they reset or choose **Use new plan** |
| `updated_at` | when they saved (`editedAt`) |
| `data` | object below |

```jsonc
{
  "plan": { },                       // full plan document, same schema as the file
  "basedOnUpdated": "2026-10-28",    // coach file `updated` the edits were based on
  "editedAt": 1761680000000,         // ms timestamp
  "coachNote": "knee sore, swap lunges",
  "changes": [
    "Mon: removed Dumbbell walking lunge",
    "Wed: Barbell deadlift 4x5 -> 3x5",
    "Note to coach: knee sore, swap lunges"
  ]
}
```

`changes` is computed at save time against the coach plan: removed and added exercises, `sets`x`reps`
(and target kg) changes, rest, notes, title, type, rest days, reordering, and the coach note.
Read this row to learn what they changed. When you next publish `plans/<profile>.json`, bump `updated`
to a later date. The app then shows **Your coach sent a new plan** with **Use new plan** (discards the
edits) and **Keep my edits**.

Until `plan_edits.sql` widens `proplog_data_kind_chk`, the `plan` row is rejected. The app keeps the
edit locally and retries. Sessions and bodyweight are unaffected. RLS is unchanged.

## Placeholder plans

`plans/nikki.json` is a placeholder until her coach bot writes her plan. A placeholder has
`"placeholder": true` and an empty `days` list; the Plan tab says the plan hasn't been written yet
and the share text skips plan comparisons. Replace the file and remove `placeholder` to activate it.
