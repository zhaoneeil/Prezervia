"""
prezervia.menu — a pet picker for homes with more than one pet.

When a customer has several pets, the app shows a menu: one row per pet.
They tap a pet to open just that pet's data — its profile, its latest
reading, and its recent history.

Everything here reuses what already exists:
  * prezervia.intake.load_pets  — the saved pets,
  * prezervia.watch.check_pet   — normal-vs-alarm for a live reading,
  * prezervia.monitor           — latest reading, history, notifications.

IMPORT:
    from prezervia.menu import list_pets, open_pet, menu
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .intake import load_pets
from .watch import check_pet
from .monitor import get_history, get_notifications, explain


# ----------------------------------------------------------------------
# 1. The menu — one short row per pet
# ----------------------------------------------------------------------
@dataclass
class MenuItem:
    """One tappable row in the pet menu."""
    pet_name: str
    species: str
    breed: str
    age_years: float
    has_alert: bool = False          # a red dot if the newest reading alarmed

    @property
    def label(self) -> str:
        dot = " 🔴" if self.has_alert else ""
        return f"{self.pet_name} — {self.breed} {self.species}{dot}"


def list_pets() -> list[MenuItem]:
    """Build the menu: every saved pet, newest-alert flag included."""
    items: list[MenuItem] = []
    for p in load_pets():
        name = p.get("pet_name", "")
        newest = get_history(name, limit=1)
        has_alert = bool(newest and newest[-1].get("alarm"))
        items.append(MenuItem(
            pet_name=name,
            species=p.get("species", ""),
            breed=p.get("breed", ""),
            age_years=p.get("age_years", 0),
            has_alert=has_alert,
        ))
    return items


# ----------------------------------------------------------------------
# 2. Open one pet — everything the pet's own screen shows
# ----------------------------------------------------------------------
@dataclass
class PetView:
    """All the data for one pet's screen."""
    pet_name: str
    species: str
    breed: str
    age_years: float
    profile_key: str = ""
    latest: dict | None = None            # newest saved reading
    latest_reasons: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)


def _find_pet(pet_name: str) -> dict:
    for p in load_pets():
        if p.get("pet_name") == pet_name:
            return p
    raise KeyError(f"No saved pet named {pet_name!r}.")


def open_pet(pet_name: str, history_limit: int = 20) -> PetView:
    """Return one pet's full screen data: profile, latest reading, history."""
    pet = _find_pet(pet_name)

    hist = get_history(pet_name, limit=history_limit)
    latest = hist[0] if hist else None    # history is newest-first, so [0] is newest

    reasons: list[str] = []
    if latest:
        # rebuild plain-language lines from the latest reading
        reasons = [r.text for r in explain(pet, latest["readings"])]

    return PetView(
        pet_name=pet.get("pet_name", ""),
        species=pet.get("species", ""),
        breed=pet.get("breed", ""),
        age_years=pet.get("age_years", 0),
        profile_key=pet.get("profile_key", ""),
        latest=latest,
        latest_reasons=reasons,
        history=hist,
        notifications=get_notifications(pet_name),
    )


# ----------------------------------------------------------------------
# 3. One call for the app: the menu, or one open pet
# ----------------------------------------------------------------------
def menu(pet_name: str | None = None):
    """No name -> the menu of pets. A name -> that pet's screen."""
    if pet_name is None:
        return list_pets()
    return open_pet(pet_name)


# ----------------------------------------------------------------------
# Self-test: run `python -m prezervia.menu`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("Pet menu:")
    rows = list_pets()
    if not rows:
        print("  (no pets saved yet — add one with prezervia.intake)")
    for i, row in enumerate(rows, 1):
        print(f"  {i}. {row.label}")

    if rows:
        first = rows[0].pet_name
        print(f"\nOpening {first!r}:")
        view = open_pet(first)
        print(f"  profile: {view.profile_key}")
        if view.latest:
            print(f"  latest reading: {view.latest['readings']}")
            print(f"  alarm: {view.latest.get('alarm')}")
        for line in view.latest_reasons:
            print("   -", line)
        print(f"  history rows: {len(view.history)}")
        print(f"  unread alerts: {len(view.notifications)}")
