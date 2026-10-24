# Prezervia

Collar telemetry for pets and livestock. One Next.js + Tailwind codebase, packaged as native iOS and Android apps with Capacitor.

## Run in the browser
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

## Importing data
Tap "Import data" and choose a CSV or JSON file (or paste). CSV columns: `name, species, temp_c` plus optional `heart_rate, respiration`; oldest row first, one reading per 10 minutes, at least 14 per animal. A sample CSV is available in the import sheet.
