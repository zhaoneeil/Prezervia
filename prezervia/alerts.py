"""
prezervia.alerts — present alerts honestly and act on them.

Four customer questions, answered:

  #1  "Where was my pet when it went wrong?"
         -> alert_on_map() attaches the GPS point saved with the reading.

  #3  "Three alerts in a row — one problem or three?"
         -> group_alerts() folds a run of alerts for the same pet into one
            incident the owner reads once.

  #2  "Turn an alert into a vet message — with the location."
         -> vet_message() builds a real, copy-ready report: the numbers, the
            plain reasons, the time, AND where the pet was. No faking.

  #7  "Was the collar really on, or just quiet?"
         -> status_dot() is green ONLY if we actually heard from the collar
            recently. 'No alarm' is never enough to be green.

Dependency-free. Reads the files monitor.py / liveness.py already write.

IMPORT:
    from prezervia.alerts import alert_on_map, group_alerts, vet_message, status_dot
"""

from __future__ import annotations

from datetime import datetime, timezone

from .monitor import get_notifications, get_history
from .liveness import reading_age, EXPECT_EVERY_MIN
from .intake import load_pets


# ----------------------------------------------------------------------
# #1 — put the alert on the map
# ----------------------------------------------------------------------
def alert_on_map(notification_id: str) -> dict:
    """Return the alert plus the GPS point from the reading that caused it.

    {"notification_id":.., "when":.., "title":.., "gps":{"lat":..,"lon":..}}
    gps is None if that reading had no location.
    """
    note = _find_note(notification_id)
    gps = _gps_for(note["pet_name"], note["when"])
    return {
        "notification_id": note["id"],
        "pet_name": note["pet_name"],
        "when": note["when"],
        "title": note["title"],
        "gps": gps,
        "has_location": gps is not None,
    }


def _gps_for(pet_name: str, when: str) -> dict | None:
    for r in get_history(pet_name):
        if r.get("when") == when:
            return r.get("gps")
    return None


# ----------------------------------------------------------------------
# #3 — group a run of alerts into one incident
# ----------------------------------------------------------------------
def group_alerts(pet_name: str | None = None, gap_minutes: int = 30) -> list[dict]:
    """Fold alerts that happen close together into one incident per pet.

    A new incident starts when there's a quiet gap of `gap_minutes`.
    Returns newest incident first:
      {"pet_name":.., "started":.., "ended":.., "count":N,
       "signals":[..], "notification_ids":[..]}
    """
    notes = get_notifications(pet_name)
    notes.sort(key=lambda n: n.get("when", ""))     # oldest first to group

    incidents: list[dict] = []
    for n in notes:
        t = _parse(n["when"])
        placed = False
        for inc in incidents:
            if inc["pet_name"] == n["pet_name"]:
                gap = (t - _parse(inc["ended"])).total_seconds() / 60
                if 0 <= gap <= gap_minutes:
                    inc["ended"] = n["when"]
                    inc["count"] += 1
                    inc["signals"] = sorted(set(inc["signals"]) | set(n.get("abnormal", [])))
                    inc["notification_ids"].append(n["id"])
                    placed = True
                    break
        if not placed:
            incidents.append({
                "pet_name": n["pet_name"],
                "started": n["when"],
                "ended": n["when"],
                "count": 1,
                "signals": sorted(set(n.get("abnormal", []))),
                "notification_ids": [n["id"]],
            })
    incidents.sort(key=lambda i: i["started"], reverse=True)
    return incidents


# ----------------------------------------------------------------------
# #2 — a real vet message, with the location
# ----------------------------------------------------------------------
def vet_message(notification_id: str) -> dict:
    """Build a copy-ready report the owner can send to their vet.

    Includes the pet, the time, the readings + plain reasons, and WHERE the
    pet was. Returns both a plain-text block and the structured data.
    """
    note = _find_note(notification_id)
    pet = next((p for p in load_pets() if p["pet_name"] == note["pet_name"]), {})
    reading = next((r for r in get_history(note["pet_name"])
                    if r.get("when") == note["when"]), {})
    gps = reading.get("gps")

    lines = [
        f"Prezervia health alert for {note['pet_name']}",
        f"Pet: {pet.get('breed','?')} {pet.get('species','')}, "
        f"age {pet.get('age_years','?')}",
        f"Time: {note['when'][:19].replace('T',' ')} UTC",
        "",
        "Abnormal readings:",
    ]
    for why in note.get("body", []):
        lines.append(f"  - {why}")
    if reading.get("readings"):
        lines.append("")
        lines.append("All readings at that moment: "
                     + ", ".join(f"{k}={v}" for k, v in reading["readings"].items()))
    if gps:
        lines.append("")
        lines.append(f"Location: {gps.get('lat')}, {gps.get('lon')}")
        lines.append(f"Map: https://maps.google.com/?q={gps.get('lat')},{gps.get('lon')}")
    if pet.get("conditions"):
        lines.append("")
        lines.append(f"Known conditions: {pet['conditions']}")

    return {
        "notification_id": notification_id,
        "pet_name": note["pet_name"],
        "text": "\n".join(lines),       # ready to copy / email to the vet
        "gps": gps,
        "readings": reading.get("readings"),
    }


# ----------------------------------------------------------------------
# #7 — the honest status dot
# ----------------------------------------------------------------------
def status_dot(pet_name: str, now: datetime | None = None) -> dict:
    """Green ONLY if we truly heard from the collar recently.

    color:
      "green"  — fresh reading AND no open alert
      "red"    — an open alert needs attention
      "grey"   — collar silent / no data (NOT 'fine')
    """
    now = now or datetime.now(timezone.utc)
    age = reading_age(pet_name, now)
    open_alerts = [n for n in get_notifications(pet_name, unread_only=True)
                   if n.get("status", "open") == "open"]

    if age["age_seconds"] is None or not age["fresh"]:
        color, label = "grey", f"No signal — last heard {age['age_text']}"
    elif open_alerts:
        color, label = "red", f"{len(open_alerts)} alert(s) need you"
    else:
        color, label = "green", f"All good — heard {age['age_text']}"

    return {
        "pet_name": pet_name,
        "color": color,
        "label": label,
        "heard_recently": bool(age["fresh"]),
        "last_seen": age["last_seen"],
        "open_alerts": len(open_alerts),
        "proof": f"Collar reported {age['age_text']}"
                 if age["age_seconds"] is not None else "Collar never reported",
    }


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _find_note(notification_id: str) -> dict:
    for n in get_notifications():
        if n.get("id") == notification_id:
            return n
    raise KeyError(f"No alert with id {notification_id!r}.")


def _parse(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.alerts
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta
    from .intake import intake
    from .monitor import record_reading

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5, "conditions": "none"}, save=True)

    now = datetime.now(timezone.utc)
    # three sick readings close together, newest one just now (fresh)
    for i in range(3):
        record_reading("Rex",
            {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2},
            gps={"lat": 47.6062, "lon": -122.3321},
            when=now - timedelta(minutes=2 - i))
    nid = get_notifications("Rex")[0]["id"]

    print("--- #1 alert on map ---")
    m = alert_on_map(nid)
    print("   gps:", m["gps"], "| has_location:", m["has_location"])

    print("\n--- #3 group alerts into incidents ---")
    for inc in group_alerts("Rex"):
        print(f"   incident: {inc['count']} alerts, signals={inc['signals']}")

    print("\n--- #2 vet message (with location) ---")
    print(vet_message(nid)["text"])

    print("\n--- #7 honest status dot ---")
    fresh = status_dot("Rex", now)
    print(f"   fresh + alert -> {fresh['color'].upper()}: {fresh['label']}")
    silent = status_dot("Rex", now + timedelta(minutes=20))
    print(f"   collar quiet  -> {silent['color'].upper()}: {silent['label']}")
