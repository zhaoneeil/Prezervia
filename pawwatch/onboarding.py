"""
pawwatch.onboarding — help a brand-new customer trust the app.

Answers the new-user questions:

  #2  "He's a rescue mix — I don't know the breed."
         -> match_unknown_breed() picks a profile by SIZE (shoulder height or
            weight) within the species, so you still get sensible normal ranges
            without knowing the breed.

  #10 "It's my first week. Does it even know what's normal for my pet yet?"
         -> confidence() tells the owner plainly: "Still learning" until there
            are enough readings, then "Knows your pet".

  Info / policy text the app should show (you gave the answers):
  #1  how to fit the collar      -> INFO["fit"]      (placeholder text to refine)
  #5  reading through fur        -> INFO["fur"]      (placeholder text to refine)
  #11 where the numbers come from-> INFO["sources"]  (official vet websites)
  #12 not a vet (disclaimer)     -> INFO["disclaimer"]
  #13 your data                  -> INFO["privacy"]  (stays on your device)

Dependency-free.

IMPORT:
    from pawwatch.onboarding import match_unknown_breed, confidence, INFO
"""

from __future__ import annotations

from . import AnimalProfile, load_animals
from .monitor import get_history


# ----------------------------------------------------------------------
# #2 — unknown rescue-mix breed: match by size within the species
# ----------------------------------------------------------------------
def match_unknown_breed(species: str, age_years: float,
                        height_cm: float | None = None,
                        weight_kg: float | None = None) -> dict:
    """Pick a profile when the breed is unknown.

    Strategy:
      * keep only rows of the same species,
      * if we have a height, pick the breed whose size band is closest,
      * else fall back to the species average,
      * then pick the age band closest to the pet's age.
    Returns the chosen profile key and how we matched.
    """
    animals = load_animals()
    rows = [a for a in animals if a.species.lower() == species.lower()]
    if not rows:
        known = sorted({a.species for a in animals})
        return {"matched": False,
                "message": f"No data for {species!r}. Known: {', '.join(known)}."}

    how = "species average"
    pool = rows

    if height_cm is not None:
        # closest by the middle of each breed's height band
        def size_gap(a: AnimalProfile) -> float:
            mid = (a.height_cm[0] + a.height_cm[1]) / 2
            return abs(mid - height_cm)
        best_breed = min(rows, key=size_gap).breed_or_type
        pool = [a for a in rows if a.breed_or_type == best_breed]
        how = f"closest size to {height_cm} cm -> {best_breed}"

    # now pick the closest age band inside the chosen pool
    def age_gap(a: AnimalProfile) -> float:
        try:
            lo, hi = a.age_range_yrs.split("-")
            mid = (float(lo) + float(hi)) / 2
        except ValueError:
            mid = 0.0
        return abs(mid - age_years)

    chosen = min(pool, key=age_gap)
    return {
        "matched": True,
        "profile_key": chosen.key,
        "breed_used": chosen.breed_or_type,
        "how": how,
        "hr_normal": chosen.hr,
        "message": (f"We don't know the exact breed, so we matched by size: "
                    f"using {chosen.breed_or_type} ranges. You can change this "
                    f"any time if you learn the breed."),
    }


# ----------------------------------------------------------------------
# #10 — first-week confidence: does the app know this pet yet?
# ----------------------------------------------------------------------
_LEARN_ENOUGH = 20     # readings before we say we "know" the pet


def confidence(pet_name: str) -> dict:
    """Tell the owner how well the app knows their pet, in plain words."""
    n = len(get_history(pet_name))
    if n == 0:
        state, msg = "new", ("Just getting started. We're using the breed's "
                             "normal ranges until we learn your pet.")
    elif n < _LEARN_ENOUGH:
        state, msg = "learning", (f"Still learning your pet ({n} of "
                                  f"{_LEARN_ENOUGH} readings). We use breed "
                                  f"ranges for now and tune them as we go.")
    else:
        state, msg = "knows", (f"We know your pet now ({n} readings). Alerts "
                               f"use your pet's own normal, not just the breed.")
    return {"pet_name": pet_name, "readings": n, "state": state,
            "percent": min(100, round(100 * n / _LEARN_ENOUGH)),
            "message": msg}


# ----------------------------------------------------------------------
# Info / policy text the app shows (your answers; refine the wording freely)
# ----------------------------------------------------------------------
INFO = {
    "fit": ("Put the collar high on the neck, snug but not tight — you should "
            "fit two fingers underneath. [Replace with your real fitting guide.]"),
    "fur": ("For thick-furred pets, part the fur so the sensor sits against the "
            "skin. [Replace with your real sensor guidance.]"),
    "sources": ("Normal ranges are collected from official veterinary websites "
                "(e.g. Merck Veterinary Manual, VCA, Cornell Feline Health). "
                "They are healthy resting ranges by species, breed and age."),
    "disclaimer": ("PawWatch helps you spot unusual readings early. It is NOT a "
                   "substitute for a veterinarian. If you are worried about your "
                   "pet, call your vet."),
    "connectivity": ("The collar works over your home wifi. Readings sync when "
                     "the collar is in wifi range; you can check your pet from "
                     "anywhere once they've synced."),
    "privacy": ("Your pet's data stays on your device. We do not sell it. "
                "[Replace with your final privacy policy.]"),
    "goal": ("PawWatch's job is simple: watch your pet's vitals and tell you "
             "when something is unusual — early, before it becomes an emergency."),
}


def get_info(topic: str) -> str:
    """Return the app text for one topic, or a list of topics if unknown."""
    if topic in INFO:
        return INFO[topic]
    return f"Unknown topic. Available: {', '.join(INFO)}."


# ----------------------------------------------------------------------
# Self-test: python -m pawwatch.onboarding
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake
    from .monitor import record_reading

    print("--- #2 unknown rescue-mix dog, ~40 cm tall ---")
    m = match_unknown_breed("Dog", age_years=4, height_cm=40)
    print("  ", m["how"])
    print("  ", m["message"])

    print("\n--- #2 unknown, no size given (species average) ---")
    print("  ", match_unknown_breed("Cat", age_years=2)["message"])

    print("\n--- #10 confidence: brand new pet ---")
    intake({"pet_name": "Scout", "species": "Dog", "breed": "Beagle",
            "age_years": 4}, save=True)
    print("  ", confidence("Scout")["message"])

    for i in range(5):
        record_reading("Scout", {"hr": 110, "resp": 22, "temp": 38.6, "movement": 40})
    print("   after 5 readings:", confidence("Scout")["state"],
          confidence("Scout")["percent"], "%")

    print("\n--- info / policy text ---")
    for topic in ("goal", "sources", "disclaimer", "privacy", "connectivity"):
        print(f"   [{topic}] {get_info(topic)}")
