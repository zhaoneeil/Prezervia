# Prezervia

Collar telemetry for pets and livestock — an abnormal-activity tracker. The app
watches each animal's vitals against its own species/breed/age ranges and flags
anything outside them. It does not diagnose; it surfaces unusual data for a vet.

This repository holds two things that work together:

- **The app** — a Next.js + Tailwind front end, packaged as native iOS/Android
  apps with Capacitor, plus a self-contained standalone web build.
- **The data engine** — a dependency-free Python package (`prezervia/`) that
  provides the animal vital ranges and the abnormal-reading detector.

## Run the web app
```
npm install
npm run dev
```

## Build the native apps
Requires Xcode (iOS) and/or Android Studio (Android).
```
npm install
npm run build        # exports the web app to ./out
npx cap sync         # copies it into ios/ and android/
npx cap open ios     # then press Run in Xcode (set your Team under Signing)
npx cap open android # then press Run in Android Studio
```
After changing any web code, run `npm run build && npx cap sync` again.

## Downloads
Ready-to-run builds live in [`downloads/`](downloads/):

- `Prezervia-standalone.html` — the whole app in one file, works offline in any browser (Windows, Mac, Linux, phones).
- `Prezervia-Windows-Linux.zip` — the standalone app plus double-click launchers for Windows and Linux.
- `Prezervia-Mac.zip` — a Mac `.app`.

## The data engine (Python)

```python
from prezervia import load_animals, find, check_alarm

animals = load_animals()                           # every animal profile
lab = find("Dog", "Labrador Retriever", "1-6")     # one profile

# A live sensor reading comes in from the collar:
result = check_alarm(lab, {"hr": 150, "resp": 40, "temp": 40.0, "movement": 10})
print(result.alarm)       # True  -> raise the alert in the UI
print(result.abnormal)    # ['hr=150 (HIGH)', 'resp=40 (HIGH)', ...]
```

### What is in the data
- 108 animal profiles across 21 species.
- Groups: `Pet`, `Farm`, `Zoo`.
- Per profile: heart rate, breathing, body temp (°C), a 0–100 movement score,
  height in cm, age range in years, and typical lifespan.
- Source: Merck / VCA veterinary references.

### Signals

| signal key | meaning | unit |
|---|---|---|
| `hr` | heart rate | beats / minute |
| `resp` | breathing | breaths / minute |
| `temp` | body temperature | °C |
| `movement` | activity proxy | 0–100 |

`movement` is an activity stand-in, not a clinical vital. A real collar builds
it from a motion sensor.

### Self-test
```bash
python -m prezervia
```

## Importing data
Tap "Import data" and choose a CSV or JSON file (or paste). CSV columns:
`name, species, temp_c` plus optional `heart_rate, respiration`; oldest row
first, one reading per 10 minutes, at least 14 per animal. A sample CSV is
available in the import sheet.
