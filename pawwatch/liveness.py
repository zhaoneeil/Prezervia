"""
pawwatch.liveness — is the collar still talking to us?

The collar is meant to send a full reading every 3 MINUTES. If we stop hearing
from it, the app must NOT pretend the pet is fine. This module answers two of
the customer's questions:

  "How old is this reading — a minute ago, or an hour?"
      -> every reading is time-stamped; we report its age in seconds/minutes.

  "What if the collar falls off or dies? Will the app lie and say 'fine'?"
      -> if NO reading arrives for 5 MINUTES, we raise a SILENT-COLLAR alert.
         Silence is never treated as 'healthy'. The app shows "no signal",
         not a green dot.

It also warns on LOW BATTERY, because the collar reports its own battery level
in every message (see note in the app docs: the app only knows the battery
because the collar sends it).

Thresholds (change in one place):
    EXPECT_EVERY_MIN = 3   # collar sends this often
    SILENT_AFTER_MIN = 5   # no word for this long -> alert
    LOW_BATTERY_PCT  = 20  # warn at or below this

IMPORT:
    from pawwatch.liveness import heartbeat, check_liveness, reading_age

Dependency-free. Writes last_seen.json next to the module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .intake import load_pets
from .monitor import _read_json, _NOTIFY_PATH, _append_json, Notification

# --- the only numbers you'd tune ---------------------------------------
EXPECT_EVERY_MIN = 3     # collar is supposed to report this often
SILENT_AFTER_MIN = 5     # no reading for this long -> "collar silent" alert
LOW_BATTERY_PCT = 20     # warn at or below this battery %
# -----------------------------------------------------------------------

_LASTSEEN_PATH = Path(__file__).with_name("last_seen.json")


# ----------------------------------------------------------------------
# 1. The collar checks in — call this every time a reading arrives
# ----------------------------------------------------------------------
def heartbeat(pet_name: str, battery_pct: float | None = None,
              when: datetime | None = None) -> None:
    """Record that we just heard from this pet's collar.

    Call this for EVERY incoming reading (monitor.record_reading can call it
    for you). `battery_pct` is what the collar reported about itself.
    """
    stamp = (when or datetime.now(timezone.utc)).isoformat()
    rows = _read_json(_LASTSEEN_PATH)
    rows = [r for r in rows if r.get("pet_name") != pet_name]
    rows.append({
        "pet_name": pet_name,
        "last_seen": stamp,
        "battery_pct": battery_pct,
    })
    _LASTSEEN_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# 2. How old is the latest reading?  (the customer's "when?" question)
# ----------------------------------------------------------------------
def reading_age(pet_name: str, now: datetime | None = None) -> dict:
    """Return the age of the last reading, in plain language.

    {
      "pet_name": "Rex",
      "last_seen": "2026-10-24T19:20:00+00:00",
      "age_seconds": 92,
      "age_text": "1 minute ago",
      "fresh": True,          # within the expected 3-minute cadence
      "battery_pct": 80,
    }
    """
    now = now or datetime.now(timezone.utc)
    rec = _last_seen(pet_name)
    if rec is None:
        return {"pet_name": pet_name, "last_seen": None, "age_seconds": None,
                "age_text": "no reading yet", "fresh": False, "battery_pct": None}

    seen = _parse(rec["last_seen"])
    age = int((now - seen).total_seconds())
    return {
        "pet_name": pet_name,
        "last_seen": rec["last_seen"],
        "age_seconds": age,
        "age_text": _age_text(age),
        "fresh": age <= EXPECT_EVERY_MIN * 60,
        "battery_pct": rec.get("battery_pct"),
    }


def _age_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} seconds ago"
    mins = seconds // 60
    if mins == 1:
        return "1 minute ago"
    if mins < 60:
        return f"{mins} minutes ago"
    hours = mins // 60
    return "1 hour ago" if hours == 1 else f"{hours} hours ago"


# ----------------------------------------------------------------------
# 3. The checker — run it on a timer; notifies on silence / low battery
# ----------------------------------------------------------------------
@dataclass
class LivenessStatus:
    pet_name: str
    state: str           # "ok" / "silent" / "no_data"
    age_seconds: int | None
    age_text: str
    battery_pct: float | None
    battery_low: bool
    notified: bool = False


def check_liveness(pet_name: str | None = None,
                   now: datetime | None = None) -> list[LivenessStatus]:
    """Check every saved pet (or one). Notify if a collar went silent or low.

    Run this on a schedule (e.g. every minute). It is SAFE to run often:
    it only creates a notification when the state is bad AND we haven't already
    warned for this silence.

    state:
      "ok"      — heard from the collar within 5 minutes
      "silent"  — no reading for 5+ minutes (collar off / dead / out of range)
      "no_data" — we have never heard from this collar
    """
    now = now or datetime.now(timezone.utc)
    names = [pet_name] if pet_name else [p["pet_name"] for p in load_pets()]
    out: list[LivenessStatus] = []

    for name in names:
        info = reading_age(name, now)
        age = info["age_seconds"]
        batt = info["battery_pct"]
        batt_low = batt is not None and batt <= LOW_BATTERY_PCT

        if age is None:
            state = "no_data"
        elif age > SILENT_AFTER_MIN * 60:
            state = "silent"
        else:
            state = "ok"

        notified = False
        if state == "silent":
            notified = _notify_once(
                name, now,
                title=f"{name}: no signal from the collar",
                body=[f"We haven't heard from {name}'s collar in "
                      f"{info['age_text']}.",
                      "This does NOT mean they are fine — the collar may be "
                      "off, out of range, or out of battery.",
                      "Please check the collar."],
                kind="silent",
            )
        elif batt_low and state == "ok":
            notified = _notify_once(
                name, now,
                title=f"{name}: collar battery low ({int(batt)}%)",
                body=[f"The collar battery is at {int(batt)}%.",
                      "Charge or change it soon so you don't lose signal."],
                kind="battery",
            )

        out.append(LivenessStatus(
            pet_name=name, state=state, age_seconds=age,
            age_text=info["age_text"], battery_pct=batt,
            battery_low=batt_low, notified=notified,
        ))
    return out


# ----------------------------------------------------------------------
# notify, but only ONCE per ongoing problem (don't spam)
# ----------------------------------------------------------------------
def _notify_once(pet_name: str, now: datetime, title: str,
                 body: list, kind: str) -> bool:
    """Create a liveness notification unless an unresolved one already exists."""
    today = now.date().isoformat()
    marker = f"{pet_name}|{kind}|{today}"   # one per pet+problem+day
    for n in _read_json(_NOTIFY_PATH):
        if n.get("id") == marker and n.get("status") == "open":
            return False                     # already warned, still open
    note = Notification(
        pet_name=pet_name,
        when=now.isoformat(),
        title=title,
        body=body,
        abnormal=[kind],
        id=marker,
        status="open",
    )
    from dataclasses import asdict
    _append_json(_NOTIFY_PATH, asdict(note))
    return True


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _last_seen(pet_name: str) -> dict | None:
    for r in _read_json(_LASTSEEN_PATH):
        if r.get("pet_name") == pet_name:
            return r
    return None


def _parse(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Self-test: run `python -m pawwatch.liveness`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5}, save=True)

    now = datetime.now(timezone.utc)

    print("--- fresh reading, 1 min ago, battery 80% ---")
    heartbeat("Rex", battery_pct=80, when=now - timedelta(minutes=1))
    print(reading_age("Rex", now)["age_text"],
          "| fresh:", reading_age("Rex", now)["fresh"])
    s = check_liveness("Rex", now)[0]
    print("state:", s.state, "| notified:", s.notified)

    print("\n--- low battery, 15% ---")
    heartbeat("Rex", battery_pct=15, when=now - timedelta(minutes=1))
    s = check_liveness("Rex", now)[0]
    print("state:", s.state, "| battery_low:", s.battery_low,
          "| notified:", s.notified)

    print("\n--- collar silent, last heard 8 min ago ---")
    heartbeat("Rex", battery_pct=80, when=now - timedelta(minutes=8))
    info = reading_age("Rex", now)
    print("age:", info["age_text"], "| fresh:", info["fresh"])
    s = check_liveness("Rex", now)[0]
    print("state:", s.state, "| notified:", s.notified)

    print("\n--- run checker again: should NOT notify twice ---")
    s = check_liveness("Rex", now)[0]
    print("state:", s.state, "| notified:", s.notified, "(expected False)")
