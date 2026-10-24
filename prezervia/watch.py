"""
prezervia.watch — take a live collar reading for a saved pet and say whether
it is normal or an alarm.

It joins two things together:
  * the customer's pet (from prezervia.intake),
  * the vital-range profile (from prezervia).

IMPORT:
    from prezervia.watch import check_pet
"""

from __future__ import annotations

from . import AlarmResult, check_alarm, index_by_key
from .intake import Pet, load_pets, match_profile


def _as_pet(pet_or_dict) -> Pet:
    if isinstance(pet_or_dict, Pet):
        return pet_or_dict
    return Pet(**pet_or_dict)


def check_pet(pet_or_dict, readings: dict) -> AlarmResult:
    """Check one live reading against the pet's normal range.

    pet_or_dict : a Pet, or a dict from load_pets()
    readings    : {"hr": 150, "resp": 40, "temp": 39.0, "movement": 10}
                  You can send only the signals you have.
    """
    pet = _as_pet(pet_or_dict)
    idx = index_by_key()

    # use the saved profile key if we have one, else match now
    profile = idx.get(pet.profile_key) if pet.profile_key else None
    if profile is None:
        profile = match_profile(pet)

    return check_alarm(profile, readings)


def check_saved_pet(pet_name: str, readings: dict) -> AlarmResult:
    """Look a pet up by name from the saved list, then check it."""
    for p in load_pets():
        if p.get("pet_name") == pet_name:
            return check_pet(p, readings)
    raise KeyError(f"No saved pet named {pet_name!r}.")


# ----------------------------------------------------------------------
# Self-test: run `python -m prezervia.watch`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake

    # a customer signs up their dog
    pet, profile = intake({
        "pet_name": "Rex",
        "species": "Dog",
        "breed": "Chihuahua",
        "age_years": 3,
        "weight_kg": 2.5,
    }, save=False)
    print(f"Matched {pet.pet_name} -> {profile.key}")
    print(f"Normal heart rate: {profile.hr[0]}-{profile.hr[1]} bpm\n")

    # a healthy reading
    good = check_pet(pet, {"hr": 120, "resp": 25, "temp": 38.8, "movement": 40})
    print("Healthy reading -> alarm:", good.alarm, good.detail)

    # a sick reading (heart racing, barely moving)
    bad = check_pet(pet, {"hr": 210, "resp": 60, "temp": 40.5, "movement": 2})
    print("Sick reading    -> alarm:", bad.alarm)
    for a in bad.abnormal:
        print("   abnormal:", a)
