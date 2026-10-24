"""
pawwatch.confirm — the "is this real?" page that opens when an alert pops up.

When the app shows an abnormal-reading notification, the customer taps it and
lands here. This module is the backend for that page. It lets them:

  1. SEE the alert — what tripped, and the plain-language "why".
  2. CONFIRM it      — "yes, something is wrong" (keeps the alert, logs it).
  3. OVERRIDE it     — "no, he was just at the park" (dismisses it with a reason).
  4. UPDATE pet info — fix age / weight / conditions right here, because stale
                       info is a common cause of a false alarm. Updating re-matches
                       the pet to the right vital-range profile.

Everything is dependency-free and writes to the same JSON files as the rest of
pawwatch. The customer's decision is saved so the app can learn and the vet can
see what the owner said.

IMPORT:
    from pawwatch.confirm import open_alert, confirm_alert, override_alert, update_pet_info
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .intake import Pet, load_pets, match_profile, build_pet, IntakeError
from .monitor import _NOTIFY_PATH, _read_json, get_notifications

# where the customer's confirm/override decisions are logged
_DECISION_PATH = Path(__file__).with_name("alert_decisions.json")

# which pet fields the customer may edit from this page
_EDITABLE = ["age_years", "weight_kg", "height_cm", "breed", "conditions"]


# ----------------------------------------------------------------------
# 1. OPEN — build everything the confirmation page needs to show
# ----------------------------------------------------------------------
def open_alert(notification_id: str) -> dict:
    """Return the full page payload for one alert.

    Shows the title, the "why" lines, the pet's current saved info, and
    which fields the customer is allowed to edit here.
    """
    note = _find_note(notification_id)
    pet = _find_pet(note["pet_name"])
    return {
        "notification_id": note["id"],
        "pet_name": note["pet_name"],
        "when": note["when"],
        "title": note["title"],
        "why": note["body"],                 # the tap-to-see-why lines
        "abnormal": note["abnormal"],
        "status": note.get("status", "open"),
        "pet_info": {k: pet.get(k) for k in _EDITABLE},
        "editable_fields": _EDITABLE,
        "actions": ["confirm", "override", "update_info"],
    }


# ----------------------------------------------------------------------
# 2. CONFIRM — the customer agrees something is wrong
# ----------------------------------------------------------------------
def confirm_alert(notification_id: str, note_text: str | None = None) -> dict:
    """Customer confirms the alert is real. Keeps it, logs the decision."""
    _set_note_status(notification_id, "confirmed")
    _log_decision(notification_id, "confirmed", note_text)
    return {
        "notification_id": notification_id,
        "status": "confirmed",
        "message": "Alert confirmed. We kept it and saved your note.",
    }


# ----------------------------------------------------------------------
# 3. OVERRIDE — the customer says it's a false alarm, with a reason
# ----------------------------------------------------------------------
def override_alert(notification_id: str, reason: str) -> dict:
    """Customer dismisses the alert. A reason is REQUIRED so we learn why."""
    if not str(reason).strip():
        raise IntakeError("Please say why this is not a problem "
                          "(e.g. 'just back from a run').")
    _set_note_status(notification_id, "overridden")
    _log_decision(notification_id, "overridden", reason)
    return {
        "notification_id": notification_id,
        "status": "overridden",
        "message": "Thanks — we dismissed this alert and saved your reason.",
    }


# ----------------------------------------------------------------------
# 4. UPDATE PET INFO — fix stale details right from the alert page
# ----------------------------------------------------------------------
def update_pet_info(pet_name: str, updates: dict) -> dict:
    """Change the customer's pet info and re-match its vital-range profile.

    updates : only keys in _EDITABLE are allowed, e.g. {"age_years": 9}.
    Returns the new info and whether the matched profile changed (which can
    make a future reading normal that used to look abnormal).
    """
    pets = load_pets()
    target = next((p for p in pets if p.get("pet_name") == pet_name), None)
    if target is None:
        raise KeyError(f"No saved pet named {pet_name!r}.")

    bad = [k for k in updates if k not in _EDITABLE]
    if bad:
        raise IntakeError(f"Can't edit these here: {', '.join(bad)}. "
                          f"Editable: {', '.join(_EDITABLE)}.")

    old_key = target.get("profile_key", "")
    merged = {**target, **updates}

    # rebuild + revalidate the pet through the normal intake rules
    raw = {k: merged.get(k) for k in (
        "pet_name", "species", "breed", "age_years",
        "weight_kg", "height_cm", "sex", "neutered", "conditions", "pet_id",
    )}
    pet = build_pet(raw)
    profile = match_profile(pet)   # sets pet.profile_key

    # save back in place
    new_pets = [asdict(pet) if p.get("pet_name") == pet_name else p for p in pets]
    _PETS_PATH = Path(__file__).with_name("pets.json")
    _PETS_PATH.write_text(json.dumps(new_pets, indent=2), encoding="utf-8")

    return {
        "pet_name": pet_name,
        "updated": {k: updates[k] for k in updates},
        "profile_changed": pet.profile_key != old_key,
        "new_profile": pet.profile_key,
        "message": ("We updated the info. The normal ranges changed, so future "
                    "readings use the new ranges."
                    if pet.profile_key != old_key else
                    "We updated the info. The normal ranges stayed the same."),
    }


# ----------------------------------------------------------------------
# Read back what the customer decided (for the vet / history)
# ----------------------------------------------------------------------
def get_decisions(pet_name: str | None = None) -> list[dict]:
    """Return the confirm/override decisions, newest first."""
    rows = _read_json(_DECISION_PATH)
    if pet_name:
        rows = [r for r in rows if r.get("pet_name") == pet_name]
    rows.sort(key=lambda r: r.get("when", ""), reverse=True)
    return rows


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _find_note(notification_id: str) -> dict:
    for n in _read_json(_NOTIFY_PATH):
        if n.get("id") == notification_id:
            return n
    raise KeyError(f"No alert with id {notification_id!r}.")


def _find_pet(pet_name: str) -> dict:
    for p in load_pets():
        if p.get("pet_name") == pet_name:
            return p
    raise KeyError(f"No saved pet named {pet_name!r}.")


def _set_note_status(notification_id: str, status: str) -> None:
    rows = _read_json(_NOTIFY_PATH)
    hit = False
    for n in rows:
        if n.get("id") == notification_id:
            n["status"] = status
            n["read"] = True
            hit = True
    if not hit:
        raise KeyError(f"No alert with id {notification_id!r}.")
    _NOTIFY_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _log_decision(notification_id: str, decision: str, note_text: str | None) -> None:
    note = _find_note(notification_id)
    rows = _read_json(_DECISION_PATH)
    rows.append({
        "notification_id": notification_id,
        "pet_name": note["pet_name"],
        "decision": decision,                 # confirmed / overridden
        "reason": (note_text or "").strip() or None,
        "when": datetime.now(timezone.utc).isoformat(),
    })
    _DECISION_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# Self-test: run `python -m pawwatch.confirm`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake
    from .monitor import record_reading

    # set up a pet and trip an alarm so there's a notification to confirm
    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3, "weight_kg": 2.5}, save=True)
    out = record_reading("Rex", {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2})
    note = get_notifications("Rex", unread_only=True)[0]
    nid = note["id"]

    print("--- 1. OPEN the alert page ---")
    page = open_alert(nid)
    print("title:", page["title"])
    for w in page["why"]:
        print("   why:", w)
    print("editable:", page["editable_fields"])

    print("\n--- 2. OVERRIDE (false alarm) ---")
    print(override_alert(nid, "Just finished a hard run at the park.")["message"])

    print("\n--- 3. UPDATE pet info (he's actually 9 now) ---")
    upd = update_pet_info("Rex", {"age_years": 9})
    print(upd["message"], "| profile_changed:", upd["profile_changed"])

    print("\n--- 4. Decisions on record (for the vet) ---")
    for d in get_decisions("Rex"):
        print(f"   {d['when'][:19]}  {d['decision']}  reason={d['reason']!r}")

    print("\n--- 5. CONFIRM path on a fresh alert ---")
    record_reading("Rex", {"hr": 215, "resp": 62, "temp": 40.8, "movement": 1})
    nid2 = get_notifications("Rex", unread_only=True)[0]["id"]
    print(confirm_alert(nid2, "He does look unwell, calling the vet.")["message"])
