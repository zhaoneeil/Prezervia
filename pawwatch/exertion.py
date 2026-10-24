"""
pawwatch.exertion — tell a running dog apart from an unusual one.

The problem: a sprint and a fever both raise the heart rate. If we only look
at heart rate, a healthy run looks like an alarm. So we look at heart rate AND
movement TOGETHER.

The idea (we are an ABNORMAL-NUMBER detector, not an illness detector):
  * When a pet moves a lot, a high heart rate is EXPECTED — that's exercise.
  * When a pet is still but the heart is racing, that's UNUSUAL — worth a look.
  * We learn each pet's own move->heart relationship from its history, so the
    line between "expected" and "unusual" fits THIS pet, not a textbook.

What it gives the app:
  * expected_hr(movement)  — the heart rate we'd expect at this activity level,
  * exertion_check()       — is the current heart rate normal FOR this movement?
  * correlation data        — points for a movement-vs-heart chart.

We never say what's wrong. We say "this number is unusual for this activity —
check with your vet."

Dependency-free. Learns from the history monitor.py saves.

IMPORT:
    from pawwatch.exertion import exertion_check, expected_hr, correlation_series
"""

from __future__ import annotations

from dataclasses import dataclass

from .monitor import get_history
from .personalize import personalized_profile


# ----------------------------------------------------------------------
# Learn the pet's own movement -> heart-rate line (simple linear fit)
# ----------------------------------------------------------------------
def _fit_line(pet_name: str, min_points: int = 8) -> tuple[float, float, int]:
    """Fit heart_rate ≈ slope * movement + base from the pet's history.

    Returns (slope, base, n). Falls back to a gentle default line if there
    isn't enough data yet.
    """
    pts = []
    for r in get_history(pet_name):
        rd = r.get("readings", {})
        if "hr" in rd and "movement" in rd and not r.get("alarm"):
            pts.append((rd["movement"], rd["hr"]))
    n = len(pts)
    if n < min_points:
        # no reliable fit yet: assume heart rises modestly with movement
        prof = personalized_profile(pet_name)
        lo, hi = prof.hr
        base = lo + (hi - lo) * 0.25          # resting-ish
        slope = (hi - lo) / 100.0             # spread across the 0-100 move scale
        return slope, base, n

    # least-squares slope/intercept
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    denom = sum((x - mx) ** 2 for x, _ in pts) or 1e-6
    slope = sum((x - mx) * (y - my) for x, y in pts) / denom
    base = my - slope * mx
    return slope, base, n


def expected_hr(pet_name: str, movement: float) -> float:
    """The heart rate we'd expect at this movement level, for this pet."""
    slope, base, _ = _fit_line(pet_name)
    return round(base + slope * movement, 1)


# ----------------------------------------------------------------------
# #7 — the combined check: is this heart rate normal FOR this activity?
# ----------------------------------------------------------------------
@dataclass
class ExertionResult:
    movement: float
    hr: float
    expected_hr: float
    gap: float                 # actual minus expected
    pattern: str               # "exercise" / "resting_ok" / "unusual_high" / "unusual_low"
    unusual: bool
    message: str


def exertion_check(pet_name: str, hr: float, movement: float,
                   speed_mps: float | None = None,
                   tolerance: float = 25.0) -> dict:
    """Judge a heart rate in the context of how much the pet is moving.

    speed_mps (from GPS, optional) is a bonus confirmation that the pet really
    is moving fast. tolerance is how far from the expected line still counts as
    normal (in bpm).
    """
    exp = expected_hr(pet_name, movement)
    gap = round(hr - exp, 1)
    moving = movement >= 50 or (speed_mps is not None and speed_mps >= 1.5)

    if abs(gap) <= tolerance:
        pattern = "exercise" if moving else "resting_ok"
        unusual = False
        msg = (f"Heart rate {hr} fits the activity ({'active' if moving else 'calm'}). "
               f"Expected about {exp}. Looks normal.")
    elif gap > tolerance and not moving:
        pattern = "unusual_high"
        unusual = True
        msg = (f"Heart rate {hr} is high while barely moving "
               f"(expected about {exp}). That's an unusual pattern — "
               f"check with your vet.")
    elif gap > tolerance and moving:
        pattern = "exercise"
        unusual = False
        msg = (f"Heart rate {hr} is high, but the pet is active — "
               f"that's expected during exercise.")
    else:  # gap < -tolerance (heart lower than expected for the activity)
        pattern = "unusual_low"
        unusual = True
        msg = (f"Heart rate {hr} is low for this activity "
               f"(expected about {exp}). Unusual — check with your vet.")

    return {
        "pet_name": pet_name, "hr": hr, "movement": movement,
        "expected_hr": exp, "gap": gap, "pattern": pattern,
        "unusual": unusual, "moving": moving, "message": msg,
    }


# ----------------------------------------------------------------------
# data for a movement-vs-heart-rate chart (the correlation picture)
# ----------------------------------------------------------------------
def correlation_series(pet_name: str) -> dict:
    """Points + the learned line, for a scatter chart in the app.

    {"points":[{"movement":..,"hr":..}, ...], "line":{"slope":..,"base":..},
     "samples": n}
    """
    pts = []
    for r in get_history(pet_name):
        rd = r.get("readings", {})
        if "hr" in rd and "movement" in rd:
            pts.append({"movement": rd["movement"], "hr": rd["hr"],
                        "alarm": bool(r.get("alarm"))})
    slope, base, n = _fit_line(pet_name)
    return {"pet_name": pet_name, "points": pts,
            "line": {"slope": round(slope, 3), "base": round(base, 1)},
            "samples": n}


# ----------------------------------------------------------------------
# Self-test: python -m pawwatch.exertion
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import datetime, timezone, timedelta
    from .intake import intake
    from .monitor import record_reading

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Labrador Retriever",
            "age_years": 4, "weight_kg": 30}, save=True)

    # teach the line: when Rex moves more, his heart goes up (healthy readings)
    base = datetime.now(timezone.utc) - timedelta(days=2)
    samples = [(10, 72), (20, 78), (40, 88), (60, 98), (80, 106), (90, 110),
               (15, 74), (50, 92), (70, 102), (30, 82)]
    for i, (mv, hr) in enumerate(samples):
        record_reading("Rex", {"hr": hr, "resp": 20, "temp": 38.6, "movement": mv},
                       when=base + timedelta(hours=i))

    print("--- learned expected heart rate ---")
    for mv in (10, 50, 90):
        print(f"   at movement {mv}: expect ~{expected_hr('Rex', mv)} bpm")

    print("\n--- #7 running vs sick (same high heart rate, different movement) ---")
    print("   RUNNING (hr 140, moving hard):")
    print("     ", exertion_check("Rex", hr=140, movement=90, speed_mps=4.0)["message"])
    print("   STILL  (hr 140, lying down):")
    print("     ", exertion_check("Rex", hr=140, movement=3)["message"])
