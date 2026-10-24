"""
prezervia.food — optional food-intake tracking.

Food is OPTIONAL. If the owner wants to log meals, the app can line feeding up
against the vitals history ("he ate less the two days his heart rate was up").
We are an abnormal-number detector, not a diet planner — we just collect what
the owner gives us and show simple patterns.

IMPORT:
    from prezervia.food import FoodLog, Meal
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Meal:
    """One feeding the owner logged. Only pet_name + when are required."""
    pet_name: str
    when: str                         # ISO time
    food: str | None = None           # "kibble", "wet food", "treat"
    amount_g: float | None = None     # grams, if the owner measured
    ate_all: bool | None = None       # did they finish it?
    note: str | None = None           # "skipped breakfast", "new brand"


class FoodLog:
    """Collect and read a pet's food intake. Everything optional.

    Example:
        log = FoodLog()
        log.add_meal("Rex", food="kibble", amount_g=120, ate_all=True)
        log.today("Rex")              # grams eaten today, meals, skipped?
        log.recent("Rex", days=7)     # list of recent meals
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path(__file__).with_name("food_log.json")

    # ---- write ----------------------------------------------------
    def add_meal(self, pet_name: str, food: str | None = None,
                 amount_g: float | None = None, ate_all: bool | None = None,
                 note: str | None = None, when: datetime | None = None) -> dict:
        """Log one meal. Returns the stored record."""
        if not str(pet_name).strip():
            raise ValueError("pet_name is required.")
        if amount_g is not None:
            try:
                amount_g = float(amount_g)
            except (TypeError, ValueError):
                raise ValueError("amount_g must be a number of grams.")
            if amount_g < 0:
                raise ValueError("amount_g can't be negative.")
        meal = Meal(
            pet_name=pet_name.strip(),
            when=(when or datetime.now(timezone.utc)).isoformat(),
            food=(food.strip() if food else None),
            amount_g=amount_g,
            ate_all=ate_all,
            note=(note.strip() if note else None),
        )
        rows = self._read()
        rows.append(asdict(meal))
        self._write(rows)
        return asdict(meal)

    # ---- read -----------------------------------------------------
    def recent(self, pet_name: str, days: int = 7) -> list[dict]:
        """Meals for one pet over the last N days, newest first."""
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        out = [m for m in self._read()
               if m.get("pet_name") == pet_name
               and _ts(m["when"]) >= cutoff]
        out.sort(key=lambda m: m["when"], reverse=True)
        return out

    def today(self, pet_name: str, now: datetime | None = None) -> dict:
        """A simple summary of today's eating."""
        now = now or datetime.now(timezone.utc)
        day = now.date().isoformat()
        meals = [m for m in self._read()
                 if m.get("pet_name") == pet_name and m["when"][:10] == day]
        grams = sum(m["amount_g"] for m in meals if m.get("amount_g") is not None)
        skipped = [m for m in meals if m.get("ate_all") is False
                   or (m.get("note") and "skip" in m["note"].lower())]
        return {
            "pet_name": pet_name, "date": day,
            "meals": len(meals),
            "grams_eaten": round(grams, 1) if grams else 0,
            "any_skipped": bool(skipped),
            "message": (f"{pet_name} ate {len(meals)} meal(s) today"
                        + (f", about {round(grams)} g" if grams else "")
                        + (" — some food was left." if skipped else ".")),
        }

    def eating_trend(self, pet_name: str, days: int = 7) -> dict:
        """Average grams/day this week vs last week — a gentle 'eating less?' flag."""
        meals = [m for m in self._read()
                 if m.get("pet_name") == pet_name and m.get("amount_g") is not None]
        now = datetime.now(timezone.utc).timestamp()
        this_week = [m["amount_g"] for m in meals
                     if now - _ts(m["when"]) <= days * 86400]
        last_week = [m["amount_g"] for m in meals
                     if days * 86400 < now - _ts(m["when"]) <= 2 * days * 86400]

        def per_day(xs):
            return round(sum(xs) / days, 1) if xs else None

        a, b = per_day(this_week), per_day(last_week)
        eating_less = (a is not None and b is not None and a < b * 0.75)
        return {"pet_name": pet_name, "this_week_g_per_day": a,
                "last_week_g_per_day": b, "eating_less": eating_less,
                "message": ("Eating noticeably less than last week — worth a look."
                            if eating_less else "Eating looks steady.")}

    # ---- storage --------------------------------------------------
    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _ts(iso: str) -> float:
    dt = datetime.fromisoformat(iso)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.food
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta

    log = FoodLog(Path(__file__).with_name("food_log.json"))
    # clean start
    if log.path.exists():
        log.path.unlink()

    now = datetime.now(timezone.utc)
    print("--- log today's meals ---")
    log.add_meal("Rex", food="kibble", amount_g=120, ate_all=True, when=now.replace(hour=8))
    log.add_meal("Rex", food="kibble", amount_g=100, ate_all=False,
                 note="left some", when=now.replace(hour=18))
    print("  ", log.today("Rex", now)["message"])

    print("\n--- optional: owner logs nothing but the fact he ate ---")
    log.add_meal("Milo")   # no amounts — still fine
    print("   stored a bare meal with no numbers: OK")

    print("\n--- eating trend (this week vs last) ---")
    for d in range(7, 14):           # last week: ~220g/day
        log.add_meal("Rex", amount_g=110, when=now - timedelta(days=d, hours=8))
        log.add_meal("Rex", amount_g=110, when=now - timedelta(days=d, hours=18))
    for d in range(1, 7):            # this week: ~130g/day (eating less)
        log.add_meal("Rex", amount_g=130, when=now - timedelta(days=d, hours=8))
    print("  ", log.eating_trend("Rex")["message"])

    log.path.unlink()   # clean up test file
