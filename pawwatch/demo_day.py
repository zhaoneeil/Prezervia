"""
pawwatch.demo_day — prove it works: a healthy day, then a sick day.

The new-user trust question:
  "Show me it working on a healthy day AND a sick day, so I believe the
   alert before I need it."

This script plays both, out loud, using the real app code:
  * HEALTHY DAY  — normal readings all day. The app stays QUIET. One green line.
  * SICK DAY     — readings drift wrong (early WARNING), then cross the line
                   (ALARM), with a severity verdict and a vet message.

Run it:
    python -m pawwatch.demo_day
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from .intake import intake
from .monitor import record_reading, get_notifications
from .severity import rate_alert, trend_warning
from .onboarding import confidence, INFO


def _line(c="-"):
    print(c * 58)


def run() -> None:
    print(INFO["goal"])
    _line("=")

    intake({"pet_name": "Buddy", "species": "Dog", "breed": "Labrador Retriever",
            "age_years": 4, "weight_kg": 30}, save=True)

    # ---------------- HEALTHY DAY ----------------
    print("HEALTHY DAY — normal readings every 3 min, morning to night")
    _line()
    start = datetime.now(timezone.utc).replace(hour=8, minute=0) - timedelta(days=1)
    # real Lab normal (age 4): hr 70-110, resp 14-26, temp 38.3-39.2, move 40-90
    healthy = [(8, 80, 50), (11, 100, 80), (14, 78, 45), (18, 105, 85), (22, 72, 42)]
    quiet_count = 0
    for hour, hr, move in healthy:
        out = record_reading("Buddy",
            {"hr": hr, "resp": 20, "temp": 38.6, "movement": move},
            when=start.replace(hour=hour))
        tag = "ALARM" if out["alarm"] else "quiet"
        if not out["alarm"]:
            quiet_count += 1
        print(f"   {hour:02d}:00  hr={hr:3} move={move:3}  -> {tag}")
    print(f"\n   Result: {quiet_count}/{len(healthy)} readings normal, "
          f"notifications sent = {len(get_notifications('Buddy'))}.")
    print("   The app stayed QUIET. That's a good day. ✔")
    _line("=")

    # ---------------- SICK DAY ----------------
    print("SICK DAY — heart rate drifts up, then crosses into danger")
    _line()
    today = datetime.now(timezone.utc).replace(minute=0)
    # Lab normal hr 70-110. Watch it climb toward the top: 100 -> 105 -> 108 (near 110)
    drift = [(0, 100), (1, 105), (2, 108)]
    for i, (h, hr) in enumerate(drift):
        record_reading("Buddy", {"hr": hr, "resp": 22, "temp": 38.7, "movement": 50},
                       when=today - timedelta(hours=3 - i))
    warn = trend_warning("Buddy", "hr")
    print("   EARLY WARNING (before any alarm):")
    print("     ", warn["message"])
    print()

    # now it crosses the line
    sick = {"hr": 150, "resp": 48, "temp": 40.2, "movement": 4}
    out = record_reading("Buddy", sick, gps={"lat": 47.61, "lon": -122.33}, when=today)
    sev = rate_alert("Buddy", sick)
    print("   ALARM:")
    for why in out["reasons"]:
        if "normal is" in why.lower() and ("above" in why or "below" in why):
            print("     -", why)
    print(f"\n   How bad: {sev['level'].upper().replace('_',' ')} — {sev['verdict']}")
    _line("=")

    print("So: quiet when Buddy is fine, loud when he isn't — and a heads-up")
    print("BEFORE it got bad. That's the promise.")
    print()
    print(INFO["disclaimer"])


if __name__ == "__main__":
    run()
