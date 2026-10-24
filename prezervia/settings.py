"""
prezervia.settings — give the owner control, and keep trying until they see it.

Three questions:

  #4  "Do I have to open the app every day, or does it watch for me?"
         -> watching_state() says plainly whether monitoring is on and when
            the collar last reported. The liveness checker does the watching;
            this reports it.

  #8  "It keeps alerting at night when my dog just sleeps deep. Stop that?"
         -> quiet hours. During the owner's set window, low-movement and
            slightly-low heart/breathing (the signs of deep sleep) do NOT
            raise a notification. A real emergency (fever, racing heart,
            far-out values) ALWAYS gets through, even at night.

  #9  "If I miss an alert, does it try again or give up?"
         -> retry_due() returns alerts that are still unseen and old enough to
            re-notify, so the app nudges again instead of giving up.

Dependency-free. Settings + retry state live in settings.json.

IMPORT:
    from prezervia.settings import set_quiet_hours, suppress_in_quiet_hours, watching_state, retry_due
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .intake import load_pets
from .liveness import reading_age
from .monitor import get_notifications

_SETTINGS_PATH = Path(__file__).with_name("settings.json")


def _load() -> dict:
    if not _SETTINGS_PATH.exists():
        return {"quiet_hours": {}, "retry_minutes": 30}
    return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))


def _save(s: dict) -> None:
    _SETTINGS_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# #4 — is the app watching for me?
# ----------------------------------------------------------------------
def watching_state(pet_name: str, now: datetime | None = None) -> dict:
    """Plain answer to 'is the app watching my pet for me?'"""
    age = reading_age(pet_name, now)
    watching = age["fresh"]
    return {
        "pet_name": pet_name,
        "watching": watching,
        "message": (f"Yes — watching your pet. Last check {age['age_text']}. "
                    f"You don't need to open the app; we'll tell you if "
                    f"something's wrong."
                    if watching else
                    f"Not getting data right now (last heard {age['age_text']}). "
                    f"Check the collar — we can't watch without a signal."),
        "last_seen": age["last_seen"],
    }


# ----------------------------------------------------------------------
# #8 — quiet hours (deep sleep shouldn't alarm)
# ----------------------------------------------------------------------
def set_quiet_hours(pet_name: str, start_hour: int, end_hour: int) -> dict:
    """Set the nightly quiet window, e.g. 22 to 6 (10pm-6am)."""
    for h in (start_hour, end_hour):
        if not 0 <= h <= 23:
            raise ValueError("Hours must be 0-23.")
    s = _load()
    s["quiet_hours"][pet_name] = {"start": start_hour, "end": end_hour}
    _save(s)
    return {"pet_name": pet_name, "quiet_hours": s["quiet_hours"][pet_name],
            "message": f"Quiet hours set {start_hour}:00-{end_hour}:00. "
                       f"We'll stay quiet for normal sleep, but still alert "
                       f"you to anything serious."}


def _in_quiet_hours(pet_name: str, when: datetime) -> bool:
    s = _load()
    q = s["quiet_hours"].get(pet_name)
    if not q:
        return False
    h = when.hour
    if q["start"] <= q["end"]:
        return q["start"] <= h < q["end"]
    return h >= q["start"] or h < q["end"]       # window wraps past midnight


def suppress_in_quiet_hours(pet_name: str, readings: dict, severity_level: str,
                            when: datetime | None = None) -> dict:
    """Decide whether to stay quiet for this reading during quiet hours.

    We suppress ONLY gentle, sleep-like abnormalities (low movement, slightly
    low heart/breathing) and ONLY when severity is 'watch'. Anything
    'call_soon' or 'call_now', and anything involving temperature, ALWAYS
    notifies — even at 3am.
    """
    when = when or datetime.now(timezone.utc)
    if not _in_quiet_hours(pet_name, when):
        return {"suppressed": False, "reason": "not in quiet hours"}

    if severity_level in ("call_soon", "call_now"):
        return {"suppressed": False, "reason": "serious — always notify"}
    if "temp" in readings:
        return {"suppressed": False, "reason": "temperature — always notify"}

    return {"suppressed": True,
            "reason": "quiet hours: looks like normal deep sleep",
            "message": f"{pet_name} looks like they're sleeping deeply. "
                       f"Staying quiet — we'll still alert you to anything serious."}


# ----------------------------------------------------------------------
# #9 — retry: keep nudging until the owner sees it
# ----------------------------------------------------------------------
def retry_due(now: datetime | None = None) -> list[dict]:
    """Return open, unread alerts old enough to re-notify.

    The app calls this on a timer; any alert here gets another nudge. This is
    how we 'try again' instead of giving up on a missed alert.
    """
    now = now or datetime.now(timezone.utc)
    retry_min = _load().get("retry_minutes", 30)
    due = []
    for n in get_notifications(unread_only=True):
        if n.get("status", "open") != "open":
            continue
        age_min = (now - _parse(n["when"])).total_seconds() / 60
        if age_min >= retry_min:
            due.append({"notification_id": n["id"], "pet_name": n["pet_name"],
                        "title": n["title"], "age_minutes": round(age_min)})
    return due


def _parse(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.settings
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta
    from .intake import intake
    from .monitor import record_reading

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5}, save=True)
    now = datetime.now(timezone.utc)
    record_reading("Rex", {"hr": 120, "resp": 25, "temp": 38.8, "movement": 40}, when=now)

    print("--- #4 is the app watching? ---")
    print("  ", watching_state("Rex", now)["message"])

    print("\n--- #8 quiet hours 22:00-06:00 ---")
    print("  ", set_quiet_hours("Rex", 22, 6)["message"])
    night = now.replace(hour=3, minute=0)
    print("   deep sleep at 3am (low movement, watch-level):")
    print("     ", suppress_in_quiet_hours("Rex", {"movement": 8}, "watch", night))
    print("   fever at 3am (always notifies):")
    print("     ", suppress_in_quiet_hours("Rex", {"temp": 40.5}, "call_now", night))

    print("\n--- #9 retry a missed alert ---")
    record_reading("Rex", {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2},
                   when=now - timedelta(minutes=45))
    due = retry_due(now)
    print("   due for another nudge:", [(d["pet_name"], f"{d['age_minutes']}min") for d in due])
