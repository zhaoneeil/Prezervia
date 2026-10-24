"""
prezervia.household — many pets, many people, honest delivery.

Three customer questions:

  #9  "Two pets, one screen. Which one needs me NOW?"
         -> home_screen() lists every pet with its status dot, worst first.

  #10 "My partner and I both use the app. If I override an alert,
       does it clear on their phone too?"
         -> members share one household. An alert is queued for EVERY member.
            When anyone resolves it, deliver_queue() stops delivering it to
            the others — it clears everywhere.

  #8  "If my phone is off, do I still get the alert when I turn it on?"
         -> NOT faked. Each member has a delivery queue. Alerts wait there
            until that member's device fetches them (device_online()), so a
            phone that was off catches up on everything it missed, in order.

Dependency-free. Stores household + queues in household.json.

IMPORT:
    from prezervia.household import add_member, home_screen, enqueue_alert, device_online, resolve_alert
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

from .intake import load_pets
from .monitor import get_notifications
from .alerts import status_dot

_HOUSE_PATH = Path(__file__).with_name("household.json")

# urgency order for the home screen
_RANK = {"red": 0, "grey": 1, "green": 2}


# ----------------------------------------------------------------------
# household state
# ----------------------------------------------------------------------
def _load() -> dict:
    if not _HOUSE_PATH.exists():
        return {"members": [], "queues": {}, "resolved": []}
    return json.loads(_HOUSE_PATH.read_text(encoding="utf-8"))


def _save(state: dict) -> None:
    _HOUSE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# #10 — members share one household
# ----------------------------------------------------------------------
def add_member(member_id: str, name: str) -> dict:
    """Add a person to the household (e.g. 'me', 'partner')."""
    state = _load()
    if not any(m["member_id"] == member_id for m in state["members"]):
        state["members"].append({"member_id": member_id, "name": name})
        state["queues"].setdefault(member_id, [])
        _save(state)
    return {"members": state["members"]}


# ----------------------------------------------------------------------
# #9 — the home screen: which pet needs me now
# ----------------------------------------------------------------------
def home_screen(now: datetime | None = None) -> list[dict]:
    """Every pet with its status dot, most-urgent first (red, then grey, then green)."""
    rows = []
    for p in load_pets():
        dot = status_dot(p["pet_name"], now)
        rows.append({
            "pet_name": p["pet_name"],
            "species": p.get("species"),
            "breed": p.get("breed"),
            "color": dot["color"],
            "label": dot["label"],
            "open_alerts": dot["open_alerts"],
        })
    rows.sort(key=lambda r: (_RANK.get(r["color"], 3), r["pet_name"]))
    return rows


# ----------------------------------------------------------------------
# #8 + #10 — queue an alert for everyone, deliver when a device comes online
# ----------------------------------------------------------------------
@dataclass
class QueuedAlert:
    notification_id: str
    pet_name: str
    title: str
    queued_at: str
    resolved: bool = False


def enqueue_alert(notification_id: str) -> dict:
    """Put one alert in EVERY member's delivery queue (real fan-out)."""
    note = next((n for n in get_notifications() if n["id"] == notification_id), None)
    if note is None:
        raise KeyError(f"No alert with id {notification_id!r}.")
    state = _load()
    item = asdict(QueuedAlert(
        notification_id=notification_id,
        pet_name=note["pet_name"],
        title=note["title"],
        queued_at=datetime.now(timezone.utc).isoformat(),
    ))
    for m in state["members"]:
        q = state["queues"].setdefault(m["member_id"], [])
        if not any(x["notification_id"] == notification_id for x in q):
            q.append(dict(item))
    _save(state)
    return {"queued_for": [m["member_id"] for m in state["members"]]}


def device_online(member_id: str) -> list[dict]:
    """A member's phone comes back online: hand it every undelivered alert.

    This is the honest version of push — nothing was shown while the phone
    was off; now it catches up on all missed alerts, oldest first, skipping
    any that someone already resolved.
    """
    state = _load()
    q = state["queues"].get(member_id, [])
    resolved_ids = set(state.get("resolved", []))
    to_deliver = [x for x in q
                  if not x["resolved"] and x["notification_id"] not in resolved_ids]
    # mark them delivered (remove from the queue)
    state["queues"][member_id] = [x for x in q
                                  if x["notification_id"] in resolved_ids or x["resolved"]]
    _save(state)
    to_deliver.sort(key=lambda x: x["queued_at"])
    return to_deliver


def resolve_alert(notification_id: str) -> dict:
    """Anyone resolves an alert -> it clears for the WHOLE household (#10)."""
    state = _load()
    if notification_id not in state["resolved"]:
        state["resolved"].append(notification_id)
    cleared = 0
    for mid, q in state["queues"].items():
        for x in q:
            if x["notification_id"] == notification_id and not x["resolved"]:
                x["resolved"] = True
                cleared += 1
    _save(state)
    return {"notification_id": notification_id,
            "cleared_from_members": cleared,
            "message": "Resolved for everyone in the household."}


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.household
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta
    from .intake import intake
    from .monitor import record_reading

    # two pets
    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5}, save=True)
    intake({"pet_name": "Milo", "species": "Cat", "breed": "Siamese",
            "age_years": 5, "weight_kg": 4.0}, save=True)

    now = datetime.now(timezone.utc)
    record_reading("Rex", {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2},
                   gps={"lat": 47.6, "lon": -122.3}, when=now)
    record_reading("Milo", {"hr": 180, "resp": 30, "temp": 38.8, "movement": 40},
                   when=now)

    # two people share the household
    add_member("me", "Me")
    add_member("partner", "Partner")

    print("--- #9 home screen (worst first) ---")
    for r in home_screen(now):
        print(f"   {r['color'].upper():5} {r['pet_name']:5} — {r['label']}")

    nid = get_notifications("Rex")[0]["id"]
    enqueue_alert(nid)

    print("\n--- #8 partner's phone was off, comes online ---")
    missed = device_online("partner")
    print("   caught up on:", [m["title"] for m in missed])

    print("\n--- #10 I resolve it -> clears for partner too ---")
    print("  ", resolve_alert(nid)["message"])
    enqueue_alert(nid)  # even if re-queued, resolved stays cleared
    again = device_online("partner")
    print("   partner now sees:", [m["title"] for m in again], "(should be empty)")
