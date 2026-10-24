"""
prezervia.intake — collect a customer's pet details and match them to the
right vital-range profile so the alarm rule can run.

A customer fills in a few fields when they set up the collar. This module:
  * defines exactly which fields we ask for (REQUIRED vs OPTIONAL),
  * validates what they typed (age is a number, species isn't blank, ...),
  * matches the pet to the closest AnimalProfile in the dataset,
  * saves the pet so the app remembers it.

IMPORT:
    from prezervia.intake import (
        FIELDS, build_pet, save_pet, load_pets, match_profile,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

from . import AnimalProfile, load_animals


# ----------------------------------------------------------------------
# 1. What we ask the customer
# ----------------------------------------------------------------------
# key, label shown to customer, required?, short help
FIELDS: list[dict] = [
    {"key": "pet_name",   "label": "Pet's name",              "required": True,  "help": "What you call them."},
    {"key": "species",    "label": "Species",                 "required": True,  "help": "e.g. Dog, Cat, Rabbit."},
    {"key": "breed",      "label": "Breed or type",           "required": True,  "help": "e.g. Labrador Retriever."},
    {"key": "age_years",  "label": "Age (years)",             "required": True,  "help": "A number, e.g. 3."},
    {"key": "weight_kg",  "label": "Weight (kg)",             "required": False, "help": "For vet context."},
    {"key": "height_cm",  "label": "Shoulder height (cm)",    "required": False, "help": "Confirms their size."},
    {"key": "sex",        "label": "Sex",                     "required": False, "help": "male / female."},
    {"key": "neutered",   "label": "Spayed or neutered?",     "required": False, "help": "yes / no."},
    {"key": "conditions", "label": "Known health conditions", "required": False, "help": "So we don't false-alarm."},
    {"key": "pet_id",     "label": "Microchip / collar ID",   "required": False, "help": "Links the collar to the pet."},
]

_REQUIRED = [f["key"] for f in FIELDS if f["required"]]

# Where saved pets live, next to the module.
_PETS_PATH = Path(__file__).with_name("pets.json")


# ----------------------------------------------------------------------
# 2. The pet record
# ----------------------------------------------------------------------
@dataclass
class Pet:
    """One customer's pet, with the profile key the alarm rule uses."""
    pet_name: str
    species: str
    breed: str
    age_years: float
    weight_kg: float | None = None
    height_cm: float | None = None
    sex: str | None = None
    neutered: bool | None = None
    conditions: str | None = None
    pet_id: str | None = None
    profile_key: str = ""   # filled in by match_profile()


# ----------------------------------------------------------------------
# 3. Validate + build a pet from raw customer input
# ----------------------------------------------------------------------
class IntakeError(ValueError):
    """Something the customer entered was missing or wrong."""


def _to_number(value, field_name: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        raise IntakeError(f"{field_name} must be a number, got {value!r}.")


def build_pet(raw: dict) -> Pet:
    """Turn raw form input into a validated Pet (profile not matched yet)."""
    # every required field must be present and non-blank
    for key in _REQUIRED:
        if not str(raw.get(key, "")).strip():
            label = next(f["label"] for f in FIELDS if f["key"] == key)
            raise IntakeError(f"Please enter: {label}.")

    age = _to_number(raw["age_years"], "Age")
    if age < 0 or age > 200:
        raise IntakeError(f"Age {age} looks wrong. Enter it in years.")

    weight = raw.get("weight_kg")
    height = raw.get("height_cm")
    neutered = raw.get("neutered")

    pet = Pet(
        pet_name=str(raw["pet_name"]).strip(),
        species=str(raw["species"]).strip().title(),
        breed=str(raw["breed"]).strip().title(),
        age_years=age,
        weight_kg=_to_number(weight, "Weight") if str(weight or "").strip() else None,
        height_cm=_to_number(height, "Height") if str(height or "").strip() else None,
        sex=(str(raw.get("sex")).strip().lower() or None) if raw.get("sex") else None,
        neutered=_yes_no(neutered),
        conditions=(str(raw.get("conditions")).strip() or None) if raw.get("conditions") else None,
        pet_id=(str(raw.get("pet_id")).strip() or None) if raw.get("pet_id") else None,
    )
    return pet


def _yes_no(value) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip().lower() in {"yes", "y", "true", "1"}


# ----------------------------------------------------------------------
# 4. Match the pet to the closest profile in the dataset
# ----------------------------------------------------------------------
def _age_in_band(age: float, band: str) -> bool:
    """Is age inside a band string like '1-10' or '0-1'?"""
    try:
        lo, hi = band.split("-")
        return float(lo) <= age <= float(hi)
    except ValueError:
        return False


def match_profile(pet: Pet, animals: list[AnimalProfile] | None = None) -> AnimalProfile:
    """Find the best vital-range profile for this pet.

    Tries, in order:
      1. same species + same breed + age inside the band,
      2. same species + same breed (closest age band),
      3. same species only (closest breed/age) — a safe fallback.
    Raises IntakeError if the species is unknown.
    """
    animals = animals or load_animals()
    species_rows = [a for a in animals if a.species.lower() == pet.species.lower()]
    if not species_rows:
        known = sorted({a.species for a in animals})
        raise IntakeError(
            f"We don't have data for {pet.species!r} yet. "
            f"Known species: {', '.join(known)}."
        )

    breed_rows = [a for a in species_rows
                  if a.breed_or_type.lower() == pet.breed.lower()]
    pool = breed_rows or species_rows

    # 1. exact age-band hit
    for a in pool:
        if _age_in_band(pet.age_years, a.age_range_yrs):
            pet.profile_key = a.key
            return a

    # 2/3. no exact band — pick the band whose midpoint is closest to the age
    def band_mid(a: AnimalProfile) -> float:
        try:
            lo, hi = a.age_range_yrs.split("-")
            return (float(lo) + float(hi)) / 2
        except ValueError:
            return 0.0

    best = min(pool, key=lambda a: abs(band_mid(a) - pet.age_years))
    pet.profile_key = best.key
    return best


# ----------------------------------------------------------------------
# 5. Save / load the customer's pets
# ----------------------------------------------------------------------
def save_pet(pet: Pet, path: str | Path | None = None) -> None:
    """Add (or update) one pet in the saved list."""
    path = Path(path) if path else _PETS_PATH
    pets = load_pets(path)
    # replace a pet with the same id or same name+breed, else append
    def same(p: dict) -> bool:
        if pet.pet_id and p.get("pet_id") == pet.pet_id:
            return True
        return p.get("pet_name") == pet.pet_name and p.get("breed") == pet.breed
    pets = [p for p in pets if not same(p)]
    pets.append(asdict(pet))
    path.write_text(json.dumps(pets, indent=2), encoding="utf-8")


def load_pets(path: str | Path | None = None) -> list[dict]:
    """Return every saved pet (empty list if none yet)."""
    path = Path(path) if path else _PETS_PATH
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# 6. One-call convenience: validate -> match -> save
# ----------------------------------------------------------------------
def intake(raw: dict, save: bool = True) -> tuple[Pet, AnimalProfile]:
    """Full flow for one customer submission."""
    pet = build_pet(raw)
    profile = match_profile(pet)
    if save:
        save_pet(pet)
    return pet, profile
