"""
pawwatch.insights — make sense of the saved history.

Answers three customer questions, all from the readings monitor.py already saves:

  #4  "Show me a line, not a list. Did the heart rate climb all week?"
         -> series_for() returns time + value points, ready for a chart.

  #5  "What is normal for a DAY? When my pet sleeps, moves, eats?"
         -> daily_pattern() averages each signal by hour of day.

  #6  "Can I save a tag? 'Vet visit', 'new food' — so I see what changed after?"
         -> add_tag() / get_tags() mark a moment on the timeline. compare_around()
            shows the average before vs after a tag, so the owner sees the effect.

Dependency-free. Tags are stored in tags.json next to the module.

IMPORT:
    from pawwatch.insights import series_for, daily_pattern, add_tag, get_tags, compare_around
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .monitor import get_history, _read_json, _append_json

_TAGS_PATH = Path(__file__).with_name("tags.json")

_SIGNALS = ["hr", "resp", "temp", "movement"]


def _parse(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# #4 — a line for the chart: time + value points for one signal
# ----------------------------------------------------------------------
@dataclass
class Point:
    when: str
    value: float


def series_for(pet_name: str, signal: str, days: int = 7) -> list[dict]:
    """Return [{when, value}, ...] oldest-first for one signal over N days.

    Feed straight into a chart (x = when, y = value). Lets the owner SEE a
    climb instead of reading a list of numbers.
    """
    if signal not in _SIGNALS:
        raise ValueError(f"signal must be one of {_SIGNALS}, got {signal!r}.")
    cutoff = _now() - days * 86400
    out = []
    for r in get_history(pet_name):
        if signal in r.get("readings", {}):
            t = _parse(r["when"]).timestamp()
            if t >= cutoff:
                out.append(asdict(Point(when=r["when"], value=r["readings"][signal])))
    out.sort(key=lambda p: p["when"])
    return out


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


# ----------------------------------------------------------------------
# #5 — the daily shape: average each signal by hour of day
# ----------------------------------------------------------------------
def daily_pattern(pet_name: str, signal: str = "movement",
                  days: int = 14) -> list[dict]:
    """Average one signal for each hour (0-23), over the last N days.

    Shows the pet's normal daily rhythm — quiet at night, busy on walks.
    Returns [{hour, average, samples}, ...] for hours that have data.
    """
    if signal not in _SIGNALS:
        raise ValueError(f"signal must be one of {_SIGNALS}, got {signal!r}.")
    cutoff = _now() - days * 86400
    buckets: dict[int, list[float]] = {h: [] for h in range(24)}
    for r in get_history(pet_name):
        if signal not in r.get("readings", {}):
            continue
        t = _parse(r["when"])
        if t.timestamp() >= cutoff:
            buckets[t.hour].append(r["readings"][signal])
    out = []
    for h in range(24):
        vals = buckets[h]
        if vals:
            out.append({"hour": h,
                        "average": round(sum(vals) / len(vals), 1),
                        "samples": len(vals)})
    return out


# ----------------------------------------------------------------------
# #6 — tags: mark a moment, then see the effect
# ----------------------------------------------------------------------
@dataclass
class Tag:
    pet_name: str
    label: str              # "Vet visit", "New food"
    when: str               # ISO time the thing happened
    note: str | None = None


def add_tag(pet_name: str, label: str, when: datetime | None = None,
            note: str | None = None) -> dict:
    """Pin an event on the pet's timeline."""
    if not str(label).strip():
        raise ValueError("A tag needs a label, e.g. 'New food'.")
    tag = Tag(pet_name=pet_name, label=label.strip(),
              when=(when or datetime.now(timezone.utc)).isoformat(),
              note=(note or None))
    _append_json(_TAGS_PATH, asdict(tag))
    return asdict(tag)


def get_tags(pet_name: str | None = None) -> list[dict]:
    """Return tags, newest first."""
    rows = _read_json(_TAGS_PATH)
    if pet_name:
        rows = [r for r in rows if r.get("pet_name") == pet_name]
    rows.sort(key=lambda r: r.get("when", ""), reverse=True)
    return rows


def compare_around(pet_name: str, tag_when: str, signal: str = "hr",
                   window_days: int = 7) -> dict:
    """Average a signal BEFORE vs AFTER a tagged moment.

    "After we changed food, his resting heart rate dropped from 95 to 82."
    """
    if signal not in _SIGNALS:
        raise ValueError(f"signal must be one of {_SIGNALS}, got {signal!r}.")
    pivot = _parse(tag_when).timestamp()
    lo = pivot - window_days * 86400
    hi = pivot + window_days * 86400
    before, after = [], []
    for r in get_history(pet_name):
        if signal not in r.get("readings", {}):
            continue
        t = _parse(r["when"]).timestamp()
        v = r["readings"][signal]
        if lo <= t < pivot:
            before.append(v)
        elif pivot <= t <= hi:
            after.append(v)

    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    b, a = avg(before), avg(after)
    change = round(a - b, 1) if (a is not None and b is not None) else None
    return {
        "pet_name": pet_name, "signal": signal, "tag_when": tag_when,
        "before_avg": b, "after_avg": a,
        "before_samples": len(before), "after_samples": len(after),
        "change": change,
    }


# ----------------------------------------------------------------------
# Self-test: python -m pawwatch.insights
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta
    from .intake import intake
    from .monitor import record_reading

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5}, save=True)

    base = datetime.now(timezone.utc) - timedelta(days=6)
    # 6 days of readings; heart rate creeps up after day 3 (a tagged food change)
    for d in range(6):
        hr = 100 + (d * 6 if d >= 3 else 0)
        record_reading("Rex",
            {"hr": hr, "resp": 24, "temp": 38.6, "movement": 35},
            when=base + timedelta(days=d, hours=9))

    food_day = (base + timedelta(days=3)).isoformat()
    add_tag("Rex", "New food", when=_parse(food_day))

    print("--- #4 heart-rate series (for the chart) ---")
    for p in series_for("Rex", "hr"):
        print(f"   {p['when'][:10]}  hr={p['value']}")

    print("\n--- #5 daily pattern (movement by hour) ---")
    for row in daily_pattern("Rex", "movement"):
        print(f"   {row['hour']:02d}:00  avg={row['average']}  n={row['samples']}")

    print("\n--- #6 tag effect: heart rate before vs after new food ---")
    cmp = compare_around("Rex", food_day, "hr")
    print(f"   before={cmp['before_avg']}  after={cmp['after_avg']}  change={cmp['change']}")
