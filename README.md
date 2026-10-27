# Prop Log

Prop Log is a static progressive web app for logging home-gym strength, conditioning, and bodyweight work. It runs entirely in the browser and works offline after the first load.

Open it at [https://tomhine82.github.io/prop-log/](https://tomhine82.github.io/prop-log/).

The app supports two people, Tom and Nikki. Each person has their own plan in `plans/<name>.json` (`plans/tom.json` and `plans/nikki.json`). See [PLAN-FORMAT.md](PLAN-FORMAT.md) for the file shape and how to update a plan.

Workout data stays on the phone, in the browser's storage. Nothing is sent to a server. Export a backup from the app if you clear site data or switch browsers.
