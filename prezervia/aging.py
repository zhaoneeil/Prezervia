"""
prezervia.aging — the pet's "normal" moves as it grows up.

The customer's point:
  "Puppy to old dog — does his normal move as he grows, or do I re-enter it?"

Answer: we store a BIRTHDAY. Age is calculated as time passes, and when the
pet crosses into a new age band (puppy -> adult -> senior) we automatically
re-match it to that band's normal ranges. The owner never re-enters anything.

IMPORT:
    from prezervia.aging import age_from_birthday, refresh_age

Dependency-free. Reads/updates pets.json (same store as intake.py).
"""

from __future__ import annotations

from datetime import datetime, timezone, date

from .intake import Pet, load_pets, save_pet, match_profile


# ----------------------------------------------------------------------
# age from a birthday
# ----------------------------------------------------------------------
def age_from_birthday(birthday: str, today: date | None = None) -> float:
    """Years old, as a decimal, from an ISO birthday like '2022-03-01'."""
    bd = date.fromisoformat(birthday)
    today = today or datetime.now(timezone.utc).date()
    days = (today - bd).days
    return round(days / 365.25, 2)


# ----------------------------------------------------------------------
# refresh one pet's age and re-match its band if it crossed into a new one
# ----------------------------------------------------------------------
def refresh_age(pet_name: str, birthday: str | None = None,
                today: date | None = None) -> dict:
    """Recalculate the pet's age and update its profile band if it changed.

    Pass birthday the first time (we save it on the pet). After that it's
    remembered, so the app can call refresh_age(pet_name) on its own — e.g.
    once a day — and the ranges keep up with the growing pet.
    """
    pets = load_pets()
    row = next((p for p in pets if p.get("pet_name") == pet_name), None)
    if row is None:
        raise KeyError(f"No saved pet named {pet_name!r}.")

    birthday = birthday or row.get("birthday")
    if not birthday:
        return {"pet_name": pet_name, "updated": False,
                "message": "No birthday on file. Add one so we can keep the "
                           "age — and the normal ranges — up to date."}

    new_age = age_from_birthday(birthday, today)
    old_key = row.get("profile_key", "")

    pet = Pet(**{k: row.get(k) for k in (
        "pet_name", "species", "breed", "age_years", "weight_kg", "height_cm",
        "sex", "neutered", "conditions", "pet_id", "profile_key")})
    pet.age_years = new_age
    new_profile = match_profile(pet)      # sets pet.profile_key to the right band

    # persist (store birthday too, so next time it's automatic)
    updated_row = {**row, "age_years": new_age,
                   "profile_key": pet.profile_key, "birthday": birthday}
    other = [p for p in pets if p.get("pet_name") != pet_name]
    from .intake import _PETS_PATH
    import json
    _PETS_PATH.write_text(json.dumps(other + [updated_row], indent=2),
                          encoding="utf-8")

    band_changed = pet.profile_key != old_key
    return {
        "pet_name": pet_name,
        "age_years": new_age,
        "band_changed": band_changed,
        "profile_key": pet.profile_key,
        "updated": True,
        "message": (f"{pet_name} is now {new_age} years old. Moved to a new age "
                    f"band — normal ranges updated automatically."
                    if band_changed else
                    f"{pet_name} is now {new_age} years old. Same age band."),
    }


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.aging
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta
    from .intake import intake

    # a puppy born recently
    intake({"pet_name": "Pup", "species": "Dog", "breed": "Labrador Retriever",
            "age_years": 0.5, "weight_kg": 8}, save=True)

    born = (datetime.now(timezone.utc).date() - timedelta(days=180)).isoformat()
    print("--- today: a 6-month puppy ---")
    r = refresh_age("Pup", birthday=born)
    print(f"   age {r['age_years']} -> band {r['profile_key']}")

    print("\n--- pretend 2 years pass (no re-entry by the owner) ---")
    two_years_on = datetime.now(timezone.utc).date() + timedelta(days=730)
    r = refresh_age("Pup", today=two_years_on)      # birthday now remembered
    print(f"   age {r['age_years']} -> band {r['profile_key']}")
    print("  ", r["message"])
