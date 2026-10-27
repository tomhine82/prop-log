# Prop Log plan format

Each person has their own plan file next to `index.html`:

| Person | File |
|---|---|
| Tom | `plans/tom.json` |
| Nikki | `plans/nikki.json` |

The app loads the **active person's** file every time it opens (and when it comes back to the
foreground after a minute or more). It fetches network-first with `cache: 'no-store'`, so a new
commit to the repo shows up the next time the app is opened. Offline, it uses the last copy it saw
(service-worker cache, then a copy kept in localStorage) and says "Offline – showing saved copy".

To update a plan: edit the JSON file, bump `updated`, and push to `main`. No app change needed.

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
              "notes": "RPE 8"       // optional string
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

## Placeholder plans

`plans/nikki.json` is a placeholder until her coach bot writes her plan. A placeholder has
`"placeholder": true` and an empty `days` list; the Plan tab says the plan hasn't been written yet
and the share text skips plan comparisons. Replace the file and remove `placeholder` to activate it.
