"""
prezervia.severity — how bad is it, and warn BEFORE it's an emergency.

This is the app's main job: catch unusual data and warn early.

Two parts:

  #7  "It said abnormal — how bad? Call the vet now, or just watch?"
         -> rate_alert() scores one alert and gives a plain verdict:
            WATCH / CALL SOON / CALL NOW.

  EARLY WARNING (the whole point of the app)
         -> trend_warning() looks at the last few readings and warns when a
            signal is drifting toward trouble, even if no single reading has
            alarmed yet. "Rex's heart rate has been climbing for 3 readings."

The score uses three honest ideas:
  * how FAR outside the normal range (a little over vs. way over),
  * how MANY signals are off at once,
  * (for trends) whether it's getting worse each reading.

Dependency-free. Reads history that monitor.py already saves.

IMPORT:
    from prezervia.severity import rate_alert, trend_warning
"""

from __future__ import annotations

from dataclasses import dataclass

from . import AnimalProfile, classify
from .monitor import get_history
from .personalize import personalized_profile


# ----------------------------------------------------------------------
# #7 — how bad is this one alert
# ----------------------------------------------------------------------
@dataclass
class Severity:
    level: str          # "watch" / "call_soon" / "call_now"
    score: float        # 0..1, how far past normal overall
    verdict: str        # plain-language advice
    worst_signal: str   # which signal is furthest out


def rate_alert(pet_name: str, readings: dict) -> dict:
    """Score how serious a reading is for this pet.

    level:
      "watch"     — a little off; keep an eye on them
      "call_soon" — clearly off; call the vet today
      "call_now"  — far off, or several signals at once; call the vet now
    """
    profile = personalized_profile(pet_name)
    offs = []                      # (signal, how-far-out 0..1)
    for sig, val in readings.items():
        far = _how_far_out(profile, sig, val)
        if far > 0:
            offs.append((sig, far))

    if not offs:
        return {"level": "ok", "score": 0.0,
                "verdict": "All readings are normal.", "worst_signal": None}

    worst_signal, worst = max(offs, key=lambda x: x[1])
    count = len(offs)
    # score blends the worst signal with how many are off
    score = min(1.0, worst * (1 + 0.25 * (count - 1)))

    # temperature out of range is treated more seriously (fever)
    temp_bad = any(s == "temp" for s, _ in offs)

    if score >= 0.6 or count >= 3 or (temp_bad and worst >= 0.4):
        level = "call_now"
        verdict = "Several signs are far from normal. Call your vet now."
    elif score >= 0.3 or count == 2:
        level = "call_soon"
        verdict = "Clearly off. Call your vet today."
    else:
        level = "watch"
        verdict = "A little off. Keep an eye on them and re-check soon."

    return {"level": level, "score": round(score, 2), "verdict": verdict,
            "worst_signal": worst_signal,
            "signals_off": [s for s, _ in offs]}


def _how_far_out(profile: AnimalProfile, signal: str, value: float) -> float:
    """0 if normal; otherwise how far outside, as a fraction of the normal width."""
    lo, hi = profile.range_for(signal)
    width = max(hi - lo, 1e-6)
    if value < lo:
        return min(1.0, (lo - value) / width)
    if value > hi:
        return min(1.0, (value - hi) / width)
    return 0.0


# ----------------------------------------------------------------------
# EARLY WARNING — notify AHEAD, before it alarms
# ----------------------------------------------------------------------
def trend_warning(pet_name: str, signal: str = "hr",
                  look_back: int = 4) -> dict:
    """Warn if a signal is drifting toward its limit, before it alarms.

    Looks at the last `look_back` readings. If the value keeps moving the same
    way and is getting close to the edge of normal, raise an early heads-up.
    This is the 'notify ahead' promise.
    """
    rows = [r for r in get_history(pet_name) if signal in r.get("readings", {})]
    rows.sort(key=lambda r: r.get("when", ""))     # oldest first
    recent = rows[-look_back:]
    if len(recent) < 3:
        return {"pet_name": pet_name, "signal": signal, "warning": False,
                "message": "Not enough readings yet to spot a trend."}

    vals = [r["readings"][signal] for r in recent]
    profile = personalized_profile(pet_name)
    lo, hi = profile.range_for(signal)

    # is it steadily rising or steadily falling?
    rising = all(b >= a for a, b in zip(vals, vals[1:])) and vals[-1] > vals[0]
    falling = all(b <= a for a, b in zip(vals, vals[1:])) and vals[-1] < vals[0]

    latest = vals[-1]
    width = max(hi - lo, 1e-6)
    # how close to an edge is the latest value? (within 15% of width = "near")
    near_high = 0 <= (hi - latest) <= 0.15 * width
    near_low = 0 <= (latest - lo) <= 0.15 * width

    if rising and near_high:
        return {"pet_name": pet_name, "signal": signal, "warning": True,
                "direction": "rising", "latest": latest, "normal_high": hi,
                "message": f"{pet_name}'s {_nice(signal)} has been climbing and is "
                           f"near the top of normal ({latest} vs max {hi}). "
                           f"Worth watching — we'll tell you if it crosses."}
    if falling and near_low:
        return {"pet_name": pet_name, "signal": signal, "warning": True,
                "direction": "falling", "latest": latest, "normal_low": lo,
                "message": f"{pet_name}'s {_nice(signal)} has been dropping and is "
                           f"near the bottom of normal ({latest} vs min {lo}). "
                           f"Worth watching — we'll tell you if it crosses."}
    return {"pet_name": pet_name, "signal": signal, "warning": False,
            "message": f"{_nice(signal)} is steady and inside normal."}


def _nice(signal: str) -> str:
    return {"hr": "heart rate", "resp": "breathing",
            "temp": "temperature", "movement": "movement"}.get(signal, signal)


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.severity
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import datetime, timezone, timedelta
    from .intake import intake
    from .monitor import record_reading

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5}, save=True)

    print("--- #7 how bad is it ---")
    print("   a little high hr:", rate_alert("Rex", {"hr": 150}))
    print("   two signals off: ", rate_alert("Rex", {"hr": 150, "resp": 38}))
    print("   emergency:       ", rate_alert("Rex", {"hr": 220, "resp": 65, "temp": 41.0}))

    print("\n--- EARLY WARNING: heart rate creeping up toward the top ---")
    base = datetime.now(timezone.utc) - timedelta(hours=4)
    for i, hr in enumerate([120, 128, 134, 138]):   # normal top is 140
        record_reading("Rex", {"hr": hr, "resp": 24, "temp": 38.7, "movement": 35},
                       when=base + timedelta(hours=i))
    print("  ", trend_warning("Rex", "hr")["message"])
