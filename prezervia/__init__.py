"""
prezervia — animal vital-range data model for the Prezervia tracker app.

A tiny, dependency-free module your app can import in the background to:
  * load the vital-range dataset (bundled CSV),
  * look up the normal range for an animal + signal,
  * classify a live sensor reading as LOW / NORMAL / HIGH,
  * run the abnormal-activity alarm rule.

INSTALL (editable, from this folder):
    pip install -e .
IMPORT:
    from prezervia import load_animals, classify, check_alarm

Data source: Merck Veterinary Manual, VCA, Cornell Feline Health, zoo-vet refs.
Values are RESTING ranges for a healthy animal of that type / age band.
`movement_score` is a 0–100 activity proxy (NOT a clinical vital).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

__version__ = "0.3.0"

# The CSV ships next to this module so the data travels with the install.
_CSV_PATH = Path(__file__).with_name("animal_vitals.csv")

Signal = Literal["hr", "resp", "temp", "movement"]
Status = Literal["LOW", "NORMAL", "HIGH"]


@dataclass(frozen=True)
class AnimalProfile:
    """One animal type, at one age band, with its healthy resting ranges."""
    animal_group: str
    species: str
    breed_or_type: str
    age_range_yrs: str
    typical_lifespan_yrs: str
    height_cm: tuple[int, int]
    hr: tuple[int, int]            # beats / minute
    resp: tuple[int, int]          # breaths / minute
    temp_c: tuple[float, float]    # degrees Celsius
    movement: tuple[int, int]      # 0–100 activity proxy
    source: str = ""

    @property
    def key(self) -> str:
        """A stable, human-readable id, e.g. 'Dog/Labrador Retriever/1-6'."""
        return f"{self.species}/{self.breed_or_type}/{self.age_range_yrs}"

    def range_for(self, signal: Signal) -> tuple[float, float]:
        return {
            "hr": self.hr,
            "resp": self.resp,
            "temp": self.temp_c,
            "movement": self.movement,
        }[signal]


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------
def load_animals(csv_path: str | Path | None = None) -> list[AnimalProfile]:
    """Read the dataset and return a list of AnimalProfile rows."""
    path = Path(csv_path) if csv_path else _CSV_PATH
    out: list[AnimalProfile] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(AnimalProfile(
                animal_group=r["animal_group"],
                species=r["species"],
                breed_or_type=r["breed_or_type"],
                age_range_yrs=r["age_range_yrs"],
                typical_lifespan_yrs=r["typical_lifespan_yrs"],
                height_cm=(int(r["height_cm_min"]), int(r["height_cm_max"])),
                hr=(int(r["hr_min"]), int(r["hr_max"])),
                resp=(int(r["resp_min"]), int(r["resp_max"])),
                temp_c=(float(r["temp_min_c"]), float(r["temp_max_c"])),
                movement=(int(r["movement_score_min"]), int(r["movement_score_max"])),
                source=r.get("source", ""),
            ))
    return out


def index_by_key(animals: list[AnimalProfile] | None = None) -> dict[str, AnimalProfile]:
    """Dict of profile.key -> AnimalProfile, for fast lookup in the app."""
    animals = animals or load_animals()
    return {a.key: a for a in animals}


def find(species: str, breed: str, age_range: str,
         animals: list[AnimalProfile] | None = None) -> AnimalProfile:
    """Look up one profile, or raise KeyError with a helpful message."""
    key = f"{species}/{breed}/{age_range}"
    idx = index_by_key(animals)
    if key not in idx:
        raise KeyError(f"No profile for {key!r}. "
                       f"Known example: {next(iter(idx))!r}")
    return idx[key]


# ----------------------------------------------------------------------
# Analysis — the health rule
# ----------------------------------------------------------------------
def classify(profile: AnimalProfile, signal: Signal, value: float) -> Status:
    """Is one reading LOW, NORMAL or HIGH for this animal?"""
    lo, hi = profile.range_for(signal)
    if value < lo:
        return "LOW"
    if value > hi:
        return "HIGH"
    return "NORMAL"


@dataclass
class AlarmResult:
    animal: str
    abnormal: list[str] = field(default_factory=list)   # which signals tripped
    alarm: bool = False
    detail: dict[str, Status] = field(default_factory=dict)


def check_alarm(profile: AnimalProfile, readings: dict[Signal, float]) -> AlarmResult:
    """Run every signal against its range. Alarm if ANY signal is abnormal.

    readings example: {"hr": 150, "resp": 40, "temp": 39.0, "movement": 10}
    """
    res = AlarmResult(animal=profile.key)
    for sig, val in readings.items():
        status = classify(profile, sig, val)
        res.detail[sig] = status
        if status != "NORMAL":
            res.abnormal.append(f"{sig}={val} ({status})")
    res.alarm = bool(res.abnormal)
    return res


# ----------------------------------------------------------------------
# Quick self-test — see __main__.py (run: python -m prezervia)
# ----------------------------------------------------------------------
