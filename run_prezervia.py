#!/usr/bin/env python3
"""
run_prezervia.py — one file that runs the whole Prezervia demo.

It ties together every piece we built:
  * the vital-range dataset (66 animal profiles),
  * intake  — sign up a pet and match it to its normal ranges,
  * watch   — check a live collar reading: normal or alarm,
  * monitor — save history + notify only when something is wrong,
  * gps     — safe-zone fence and distance.

Run it from this folder:
    python3 run_prezervia.py

If you set up the virtual environment earlier, use that Python:
    .venv/bin/python run_prezervia.py
"""

from __future__ import annotations

from prezervia import load_animals
from prezervia.intake import intake
from prezervia.watch import check_pet
from prezervia.monitor import record_reading, get_history, get_notifications
from prezervia.gps import Fix, SafeZone, GpsTracker


def line(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    # ------------------------------------------------------------------
    line("1. The data")
    animals = load_animals()
    species = sorted({a.species for a in animals})
    print(f"Loaded {len(animals)} animal profiles across {len(species)} species.")
    print("Species:", ", ".join(species))

    # ------------------------------------------------------------------
    line("2. Sign up a pet (intake)")
    pet, profile = intake({
        "pet_name": "Rex",
        "species": "Dog",
        "breed": "Chihuahua",
        "age_years": 3,
        "weight_kg": 2.5,
    }, save=True)
    print(f"Saved {pet.pet_name} the {pet.breed}.")
    print(f"Matched to normal ranges -> {profile.key}")
    print(f"  heart {profile.hr[0]}-{profile.hr[1]} bpm")
    print(f"  breath {profile.resp[0]}-{profile.resp[1]} /min")
    print(f"  temp {profile.temp_c[0]}-{profile.temp_c[1]} C")

    # ------------------------------------------------------------------
    line("3. A healthy reading (should stay quiet)")
    out = record_reading("Rex",
        {"hr": 120, "resp": 25, "temp": 38.8, "movement": 40})
    print(f"alarm: {out['alarm']}   notified: {out['notified']}")

    # ------------------------------------------------------------------
    line("4. A sick reading (should raise an alarm)")
    out = record_reading("Rex",
        {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2})
    print(f"alarm: {out['alarm']}   notified: {out['notified']}")
    print("Why (tap-the-alert reasons):")
    for why in out["reasons"]:
        print("   -", why)

    # ------------------------------------------------------------------
    line("5. Notifications (abnormal only)")
    for n in get_notifications("Rex", unread_only=True):
        print("   *", n["title"])

    # ------------------------------------------------------------------
    line("6. History (newest first)")
    for h in get_history("Rex"):
        print(f"   {h['when'][:19]}  alarm={h['alarm']}  {h['readings']}")

    # ------------------------------------------------------------------
    line("7. GPS safe zone")
    home = Fix(37.7749, -122.4194)
    tracker = GpsTracker(SafeZone(home, radius_m=100))
    points = [
        Fix(37.7751, -122.4190),   # close to home, inside
        Fix(37.7760, -122.4180),   # drifting
        Fix(37.7800, -122.4140),   # left the zone
    ]
    for p in points:
        g = tracker.update(p)
        flag = "FENCE ALARM" if g.fence_alarm else "safe"
        print(f"   {round(g.metres_from_home):>5} m from home  ->  {flag}")
    report = tracker.distance_report()
    print(f"   walked {round(report.path_length_m)} m over {report.points} points")

    line("Demo complete")
    print("Rex is saved. Run again to add more readings.")


if __name__ == "__main__":
    main()
