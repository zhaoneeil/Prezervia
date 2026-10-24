"""
pawwatch.monitor — the app's "watch my pet" loop.

Three jobs:

  1. TAP THE ALERT -> see why.
     Every reading becomes a plain-language reason the app can show when the
     customer taps a red alert ("Heart rate 210 is HIGH. Normal is 100-160.").

  2. HISTORY.
     Every reading is saved to a log, healthy or not. All of that code now
     lives in pawwatch.history; this file just calls it. The names are
     re-exported below, so `from .monitor import get_history, HistoryEntry`
     still works exactly as before.

  3. NOTIFY ONLY ON ABNORMAL.
     A notification is created ONLY when a reading is an alarm. A healthy
     reading is still saved to history, but it stays quiet — no notification.

IMPORT:
    from pawwatch.monitor import record_reading, get_history, get_notifications

Everything is dependency-free and writes JSON next to the module, matching
how pawwatch.intake saves pets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import AlarmResult, Status
from .watch import check_pet
from .intake import load_pets

# All history code lives in pawwatch.history now. Re-exported here so existing
# callers that do `from .monitor import get_history / HistoryEntry / ...` keep
# working. _read_json / _append_json are shared helpers (liveness uses them).
from .history import (
    HistoryEntry,
    add_history,
    get_history,
    _HISTORY_PATH,
    _read_json,
    _append_json,
)

# Notifications log lives next to the module, like pets.json.
_NOTIFY_PATH = Path(__file__).with_name("notifications.json")

# Friendly names + units for the plain-language reason text.
_SIGNAL_LABEL = {
    "hr": ("Heart rate", "bpm"),
    "resp": ("Breathing", "breaths/min"),
    "temp": ("Temperature", "\u00b0C"),
    "movement": ("Movement", "/100"),
}


# ----------------------------------------------------------------------
# The "why" behind one signal — this is what a tapped alert shows
# ----------------------------------------------------------------------
@dataclass
class Reason:
    """One plain-language line explaining a single signal's status."""
    signal: str          # "hr"
    label: str           # "Heart rate"
    value: float         # 210
    status: Status       # "LOW" / "NORMAL" / "HIGH"
    normal_low: float    # 100
    normal_high: float   # 160
    unit: str            # "bpm"

    @property
    def text(self) -> str:
        """The sentence the app shows when the alert is tapped."""
        rng = f"Normal is {_trim(self.normal_low)}-{_trim(self.normal_high)} {self.unit}."
        if self.status == "NORMAL":
            return f"{self.label} {_trim(self.value)} {self.unit} is normal. {rng}"
        word = "above normal" if self.status == "HIGH" else "below normal"
        return f"{self.label} {_trim(self.value)} {self.unit} is {word}. {rng}"


def _trim(n: float) -> str:
    """Show 210 not 210.0, but keep 38.5."""
    return str(int(n)) if float(n).is_integer() else str(n)


def explain(pet_or_dict, readings: dict) -> list[Reason]:
    """Turn one reading into a list of plain-language Reason lines.

    This is the data behind the tappable alert: one Reason per signal,
    each with a human sentence in `.text`.
    """
    pet = pet_or_dict
    result = check_pet(pet, readings)
    profile = _profile_for(pet)

    reasons: list[Reason] = []
    for sig, value in readings.items():
        lo, hi = profile.range_for(sig)
        label, unit = _SIGNAL_LABEL.get(sig, (sig, ""))
        reasons.append(Reason(
            signal=sig,
            label=label,
            value=value,
            status=result.detail[sig],
            normal_low=lo,
            normal_high=hi,
            unit=unit,
        ))
    return reasons


def _profile_for(pet_or_dict):
    """Resolve the vital-range profile for a pet (dict or Pet)."""
    from . import index_by_key
    from .intake import Pet, match_profile
    pet = pet_or_dict if isinstance(pet_or_dict, Pet) else Pet(**pet_or_dict)
    idx = index_by_key()
    prof = idx.get(pet.profile_key) if pet.profile_key else None
    return prof or match_profile(pet)


# ----------------------------------------------------------------------
# The main entry point the app calls for every incoming reading
# ----------------------------------------------------------------------
def record_reading(pet_name: str, readings: dict, gps: dict | None = None,
                   when: datetime | None = None,
                   battery_pct: float | None = None) -> dict:
    """Process ONE live reading for a saved pet.

    Does all three jobs:
      * builds the tappable reasons,
      * appends the reading to history (always),
      * creates a notification ONLY if it's abnormal.

    `battery_pct` is what the collar reported about itself; it also records a
    liveness heartbeat so the silent-collar checker knows we just heard from it.

    Returns a small dict the app can show right away:
      {
        "pet_name": "Rex",
        "alarm": True,
        "reasons": ["Heart rate 210 bpm is above normal. Normal is 100-160 bpm.", ...],
        "notified": True,     # did we create a notification?
      }
    """
    pet = _find_pet(pet_name)
    result = check_pet(pet, readings)
    reasons = explain(pet, readings)

    stamp = (when or datetime.now(timezone.utc)).isoformat()

    # mark the collar as alive (import here to avoid a circular import)
    from .liveness import heartbeat
    heartbeat(pet_name, battery_pct=battery_pct, when=when)

    entry = HistoryEntry(
        pet_name=pet_name,
        when=stamp,
        readings=readings,
        alarm=result.alarm,
        abnormal=result.abnormal,
        reasons=[r.text for r in reasons],
        gps=gps,
    )
    add_history(entry)

    notified = False
    if result.alarm:                       # <-- notify ONLY on abnormal
        _create_notification(pet_name, stamp, result, reasons)
        notified = True

    return {
        "pet_name": pet_name,
        "alarm": result.alarm,
        "reasons": [r.text for r in reasons],
        "abnormal": result.abnormal,
        "notified": notified,
    }


def _find_pet(pet_name: str) -> dict:
    for p in load_pets():
        if p.get("pet_name") == pet_name:
            return p
    raise KeyError(f"No saved pet named {pet_name!r}. Add them in intake first.")


# ----------------------------------------------------------------------
# Notifications — created only for abnormal readings
# ----------------------------------------------------------------------
@dataclass
class Notification:
    pet_name: str
    when: str
    title: str                       # short line for the app banner
    body: list                       # the "why" lines (tap to expand)
    abnormal: list
    id: str = ""                     # stable id the confirm page uses
    status: str = "open"             # open / confirmed / overridden
    read: bool = False               # app marks True when opened


def _create_notification(pet_name: str, stamp: str,
                         result: AlarmResult, reasons: list[Reason]) -> None:
    # only the signals that actually tripped go in the body
    why = [r.text for r in reasons if r.status != "NORMAL"]
    bad_signals = [_SIGNAL_LABEL.get(r.signal, (r.signal, ""))[0]
                   for r in reasons if r.status != "NORMAL"]
    title = f"{pet_name}: check on them — {', '.join(bad_signals)} abnormal"
    note = Notification(
        pet_name=pet_name,
        when=stamp,
        title=title,
        body=why,
        abnormal=result.abnormal,
        id=f"{pet_name}|{stamp}",
    )
    _append_json(_NOTIFY_PATH, asdict(note))


def get_notifications(pet_name: str | None = None,
                      unread_only: bool = False) -> list[dict]:
    """Return notifications, newest first. Only abnormal readings make these."""
    rows = _read_json(_NOTIFY_PATH)
    if pet_name:
        rows = [r for r in rows if r.get("pet_name") == pet_name]
    if unread_only:
        rows = [r for r in rows if not r.get("read")]
    rows.sort(key=lambda r: r.get("when", ""), reverse=True)
    return rows


def mark_notifications_read(pet_name: str | None = None) -> int:
    """Mark notifications read (all, or for one pet). Returns how many changed."""
    rows = _read_json(_NOTIFY_PATH)
    changed = 0
    for r in rows:
        if (pet_name is None or r.get("pet_name") == pet_name) and not r.get("read"):
            r["read"] = True
            changed += 1
    if changed:
        _NOTIFY_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return changed


# ----------------------------------------------------------------------
# Self-test: run `python -m pawwatch.monitor`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake

    # make sure one pet exists
    intake({
        "pet_name": "Rex",
        "species": "Dog",
        "breed": "Chihuahua",
        "age_years": 3,
        "weight_kg": 2.5,
    }, save=True)

    print("--- healthy reading (should stay quiet) ---")
    out = record_reading("Rex",
        {"hr": 120, "resp": 25, "temp": 38.8, "movement": 40},
        gps={"lat": 47.6, "lon": -122.3})
    print("alarm:", out["alarm"], "| notified:", out["notified"])

    print("\n--- sick reading (should notify) ---")
    out = record_reading("Rex",
        {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2})
    print("alarm:", out["alarm"], "| notified:", out["notified"])
    print("tap-the-alert reasons:")
    for line in out["reasons"]:
        print("   -", line)

    print("\n--- notifications (abnormal only) ---")
    for n in get_notifications("Rex", unread_only=True):
        print("   *", n["title"])

    print("\n--- history (newest first) ---")
    for h in get_history("Rex"):
        print(f"   {h['when'][:19]}  alarm={h['alarm']}  {h['readings']}")
