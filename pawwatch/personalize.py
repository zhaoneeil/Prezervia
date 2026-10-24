"""
pawwatch.personalize — learn ONE pet's "new normal".

The big question from an owner of an old or sick pet:
  "He's slower now. Will the app alarm every single day because of that?"

The fix: the app watches what THIS pet actually does when the owner says
it's fine, and widens that pet's own normal ranges to match. So the breed
chart is only the starting point; over time the alarm uses the pet's real
baseline.

Two sources of truth, both already saved by the app:
  * OVERRIDES  — owner tapped "not a problem" on an alert (confirm.py).
                 Those readings were abnormal-by-chart but fine-by-owner.
  * HEALTHY HISTORY — readings that never alarmed (monitor.py).

We combine them into a per-pet range and store it in learned_ranges.json.
check_pet() can then prefer the learned range when one exists.

SAFETY: temperature is NOT auto-widened — a fever is a fever at any age.
And we only widen, never narrow below the breed range, so we never miss a
real emergency by learning a sick pattern as "normal".

IMPORT:
    from pawwatch.personalize import learn_ranges, get_learned_range, personalized_profile
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from . import AnimalProfile, index_by_key
from .intake import Pet, load_pets, match_profile
from .monitor import get_history

_LEARNED_PATH = Path(__file__).with_name("learned_ranges.json")

# signals we're willing to personalize; temp stays on the clinical range
_LEARNABLE = ["hr", "resp", "movement"]
_MIN_SAMPLES = 10          # need this many "fine" readings before we trust it


# ----------------------------------------------------------------------
# learn — build a personal range from what the owner called fine
# ----------------------------------------------------------------------
def learn_ranges(pet_name: str) -> dict:
    """Study this pet's fine readings and widen its personal ranges.

    "Fine" = readings that did NOT alarm, PLUS readings the owner overrode
    (abnormal by the chart, but the owner said it's okay).

    Returns the learned ranges, or a note if there isn't enough data yet.
    """
    rows = get_history(pet_name)
    if not rows:
        return {"pet_name": pet_name, "learned": {}, "ready": False,
                "message": "No history yet. Keep the collar on for a few days."}

    fine = [r for r in rows if not r.get("alarm") or _was_overridden(r)]
    if len(fine) < _MIN_SAMPLES:
        return {"pet_name": pet_name, "learned": {}, "ready": False,
                "message": f"Only {len(fine)} fine readings so far; "
                           f"need {_MIN_SAMPLES} to learn a reliable normal."}

    base = _breed_profile(pet_name)
    learned = {}
    for sig in _LEARNABLE:
        vals = [r["readings"][sig] for r in fine if sig in r.get("readings", {})]
        if len(vals) < _MIN_SAMPLES:
            continue
        vals.sort()
        # use the 5th..95th percentile of what the pet really does
        lo = _pct(vals, 5)
        hi = _pct(vals, 95)
        # only ever WIDEN past the breed range, never narrow it
        b_lo, b_hi = base.range_for(sig)
        learned[sig] = [min(b_lo, round(lo, 1)), max(b_hi, round(hi, 1))]

    record = {"pet_name": pet_name, "learned": learned,
              "samples": len(fine), "ready": bool(learned),
              "message": "Learned this pet's normal from its own readings."}
    _save(record)
    return record


def _pct(sorted_vals: list[float], p: float) -> float:
    """Simple percentile (p in 0..100) of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _was_overridden(reading_row: dict) -> bool:
    """True if the owner dismissed the alert for this reading."""
    from .confirm import get_decisions
    when = reading_row.get("when")
    for d in get_decisions(reading_row.get("pet_name")):
        if d.get("decision") == "overridden" and d.get("notification_id", "").endswith(when or "\0"):
            return True
    return False


# ----------------------------------------------------------------------
# read the learned range, and build a personalized profile for the alarm
# ----------------------------------------------------------------------
def get_learned_range(pet_name: str, signal: str) -> tuple[float, float] | None:
    """Return this pet's learned [lo, hi] for a signal, or None."""
    for r in _read_all():
        if r.get("pet_name") == pet_name:
            rng = r.get("learned", {}).get(signal)
            return (rng[0], rng[1]) if rng else None
    return None


def personalized_profile(pet_name: str) -> AnimalProfile:
    """The pet's breed profile, with learned ranges swapped in where we have them.

    Hand this to check_alarm() instead of the plain breed profile and the
    alarm uses the pet's own normal.
    """
    base = _breed_profile(pet_name)
    learned_row = next((r for r in _read_all() if r["pet_name"] == pet_name), None)
    if not learned_row or not learned_row.get("learned"):
        return base
    L = learned_row["learned"]
    return AnimalProfile(
        animal_group=base.animal_group, species=base.species,
        breed_or_type=base.breed_or_type, age_range_yrs=base.age_range_yrs,
        typical_lifespan_yrs=base.typical_lifespan_yrs, height_cm=base.height_cm,
        hr=tuple(L.get("hr", base.hr)),
        resp=tuple(L.get("resp", base.resp)),
        temp_c=base.temp_c,                       # temp never personalized
        movement=tuple(L.get("movement", base.movement)),
        source=base.source + " + learned",
    )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _breed_profile(pet_name: str) -> AnimalProfile:
    pet_dict = next((p for p in load_pets() if p.get("pet_name") == pet_name), None)
    if pet_dict is None:
        raise KeyError(f"No saved pet named {pet_name!r}.")
    pet = Pet(**pet_dict)
    idx = index_by_key()
    return idx.get(pet.profile_key) or match_profile(pet)


def _read_all() -> list[dict]:
    if not _LEARNED_PATH.exists():
        return []
    return json.loads(_LEARNED_PATH.read_text(encoding="utf-8"))


def _save(record: dict) -> None:
    rows = [r for r in _read_all() if r.get("pet_name") != record["pet_name"]]
    rows.append(record)
    _LEARNED_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# Self-test: python -m pawwatch.personalize
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import datetime, timezone, timedelta
    from .intake import intake
    from .monitor import record_reading, get_notifications
    from .confirm import override_alert
    from . import check_alarm

    # an OLD dog: slower, lower movement than the breed chart expects
    intake({"pet_name": "Old Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 14, "weight_kg": 2.5}, save=True)

    before = _breed_profile("Old Rex")
    print("breed movement normal:", before.movement, "-> movement=5 alarms by the chart")
    r1 = check_alarm(before, {"movement": 5})
    print("   with breed range, alarm:", r1.alarm, "(too slow by the chart)")

    # The real flow: each slow reading alarms, the owner says "he's fine, just old"
    # and overrides it. The app LEARNS from those overrides.
    base = datetime.now(timezone.utc) - timedelta(days=5)
    for i in range(15):
        stamp = base + timedelta(hours=i * 6)
        record_reading("Old Rex",
            {"hr": 115, "resp": 24, "temp": 38.7, "movement": 5},
            when=stamp)
        nid = f"Old Rex|{stamp.isoformat()}"        # the alert id for that reading
        override_alert(nid, "He's 14 — this is normal for him now.")

    print("\n(owner overrode 15 slow readings as 'fine for an old dog')")
    out = learn_ranges("Old Rex")
    print("learned:", out["learned"], "| ready:", out["ready"])

    after = personalized_profile("Old Rex")
    print("personal movement normal:", after.movement)
    r2 = check_alarm(after, {"movement": 5})
    print("   with learned range, alarm:", r2.alarm, "(should be False now)")

    # but a real emergency STILL alarms
    r3 = check_alarm(after, {"movement": 0, "hr": 230, "temp": 41.0})
    print("   true emergency still alarms:", r3.alarm, r3.abnormal)
