"""
pawwatch.sound — listen to the collar microphone and say what the sound is.

Dependency-free, like the rest of pawwatch. It can:
  * load the sound reference list (bundled CSV),
  * take one "sound reading" from the collar (loudness + pitch + how long),
  * guess which sound type it is for that animal,
  * say if the sound is normal or abnormal,
  * turn it into a plain message for the customer.

WHERE THE SENSOR IS
    A tiny microphone sits in the collar box, under the chin, on the
    throat side. That spot sits right over the voice box and windpipe,
    so it hears barks, coughs and breathing clearly and ignores most
    wind and footstep noise. We are only the app — a real collar would
    send these sound readings over the air; here we feed them in, the
    same way the vitals and GPS are faked.

WHAT THE COLLAR SENDS US
    We do NOT send raw audio. The collar chip turns each short clip into
    three plain numbers, so nothing private travels and the battery lasts:
      * loudness  — how loud, 0 (silent) to 100 (very loud),
      * pitch_hz  — how high the sound is, in hertz (low = deep, high = squeaky),
      * seconds   — how long the sound lasted.

HOW IT GUESSES
    Each known sound has three bands: a pitch band, a loudness band and a
    length band. The reading is scored against every sound for this animal,
    and the best fit wins. Using all three numbers (not pitch alone) tells
    apart sounds that share a pitch — a loud short cough vs a quiet long pant.

IMPORT:
    from pawwatch.sound import SoundReading, identify_sound, sound_report
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# The CSV ships next to this module so the data travels with the install.
_CSV_PATH = Path(__file__).with_name("animal_sounds.csv")

# How quiet counts as "silence" for the too-quiet check.
_SILENCE_LOUDNESS = 5

# Catch-all rows that should only win when no real sound fits.
_CATCH_ALL = ("silence_unusual", "generic_distress")


@dataclass(frozen=True)
class SoundType:
    """One kind of sound an animal can make, and what it means."""
    sound_type: str
    applies_to: str          # species name, or "Any"
    is_normal: bool
    hz_min: int
    hz_max: int
    loud_min: int            # 0–100
    loud_max: int
    sec_min: float
    sec_max: float
    urgency: int             # 0 none, 1 low, 2 watch, 3 urgent
    plain_meaning: str
    what_to_do: str


@dataclass(frozen=True)
class SoundReading:
    """One sound the collar heard, as three plain numbers."""
    loudness: float          # 0–100
    pitch_hz: float          # hertz
    seconds: float = 1.0     # how long it lasted


@dataclass
class SoundResult:
    """What pawwatch thinks the sound was."""
    species: str
    sound_type: str          # best guess, e.g. "cough"
    is_normal: bool
    urgency: int             # 0–3
    meaning: str             # plain words for the customer
    advice: str              # what the customer should do
    abnormal: bool = False   # True if this sound should worry the owner


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------
def load_sounds(csv_path: str | Path | None = None) -> list[SoundType]:
    """Read the sound list and return a list of SoundType rows."""
    path = Path(csv_path) if csv_path else _CSV_PATH
    out: list[SoundType] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(SoundType(
                sound_type=r["sound_type"],
                applies_to=r["applies_to"],
                is_normal=(r["is_normal"].strip().lower() == "yes"),
                hz_min=int(r["hz_min"]),
                hz_max=int(r["hz_max"]),
                loud_min=int(r["loud_min"]),
                loud_max=int(r["loud_max"]),
                sec_min=float(r["sec_min"]),
                sec_max=float(r["sec_max"]),
                urgency=int(r["urgency"]),
                plain_meaning=r["plain_meaning"],
                what_to_do=r["what_to_do"],
            ))
    return out


def sounds_for(species: str,
               sounds: list[SoundType] | None = None) -> list[SoundType]:
    """Every sound type that applies to this species (plus the 'Any' ones)."""
    sounds = sounds or load_sounds()
    return [s for s in sounds
            if s.applies_to == species or s.applies_to == "Any"]


# ----------------------------------------------------------------------
# Scoring — how well does one reading fit one sound?
# ----------------------------------------------------------------------
def _miss(value: float, lo: float, hi: float, width_hint: float) -> float:
    """0 if value is inside [lo, hi]; grows the further outside it falls.

    Scaled by width_hint so pitch (hundreds of hertz) and loudness (0–100)
    count about the same.
    """
    if lo <= value <= hi:
        return 0.0
    gap = (lo - value) if value < lo else (value - hi)
    return gap / width_hint


def _tightness(s: SoundType) -> float:
    """Smaller = more specific bands. Used to break a scoring tie."""
    return ((s.hz_max - s.hz_min) / 1000.0
            + (s.loud_max - s.loud_min) / 40.0
            + (s.sec_max - s.sec_min) / 5.0)


def _score(s: SoundType, r: SoundReading) -> float:
    """Total miss across pitch, loudness and length. Lower is a better fit."""
    return (_miss(r.pitch_hz, s.hz_min, s.hz_max, 1000.0)
            + _miss(r.loudness, s.loud_min, s.loud_max, 40.0)
            + _miss(r.seconds, s.sec_min, s.sec_max, 5.0))


# ----------------------------------------------------------------------
# The guess — which sound is it?
# ----------------------------------------------------------------------
def identify_sound(species: str, reading: SoundReading,
                   sounds: list[SoundType] | None = None) -> SoundResult:
    """Take one collar sound reading and guess what it is for this animal.

    How it decides, in order:
      1. Too quiet for too long  -> a "too quiet" warning.
      2. Score every real sound; the best fit wins.
      3. No sound fits well, but it is loud -> a generic distress warning.
      4. Nothing notable -> a normal, quiet moment.
    """
    choices = sounds_for(species, sounds)

    # 1. Unusual silence: a quiet collar for a long time from a vocal pet.
    if reading.loudness <= _SILENCE_LOUDNESS and reading.seconds >= 30:
        quiet = _by_name(choices, "silence_unusual")
        if quiet:
            return _result(species, quiet)

    # 2. Score every real (non-catch-all) sound; lowest miss wins.
    real = [s for s in choices if s.sound_type not in _CATCH_ALL]
    if real and reading.loudness > _SILENCE_LOUDNESS:
        # best fit first; on a tie, the more specific (tighter) sound wins
        best = min(real, key=lambda s: (_score(s, reading), _tightness(s)))
        if _score(best, reading) <= 1.0:
            return _result(species, best)

    # 3. Loud but nothing fit well -> generic distress (abnormal).
    if reading.loudness >= 50:
        generic = _by_name(choices, "generic_distress")
        if generic:
            return _result(species, generic)

    # 4. Nothing notable: a normal quiet moment.
    return SoundResult(
        species=species,
        sound_type="quiet",
        is_normal=True,
        urgency=0,
        meaning="Nothing unusual. The animal is quiet.",
        advice="Nothing to do.",
        abnormal=False,
    )


def _by_name(choices: list[SoundType], name: str) -> SoundType | None:
    for s in choices:
        if s.sound_type == name:
            return s
    return None


def _result(species: str, s: SoundType) -> SoundResult:
    return SoundResult(
        species=species,
        sound_type=s.sound_type,
        is_normal=s.is_normal,
        urgency=s.urgency,
        meaning=s.plain_meaning,
        advice=s.what_to_do,
        abnormal=not s.is_normal,
    )


# ----------------------------------------------------------------------
# The customer message
# ----------------------------------------------------------------------
def sound_report(pet_name: str, species: str,
                 reading: SoundReading,
                 sounds: list[SoundType] | None = None) -> str:
    """One short message the app can show the customer about a sound."""
    r = identify_sound(species, reading, sounds)
    bell = {0: "🟢", 1: "🔵", 2: "🟠", 3: "🔴"}.get(r.urgency, "🟢")
    head = "All good" if not r.abnormal else "Heads up"
    if r.urgency == 3:
        head = "Check now"
    return (f"{bell} {head} — {pet_name} ({species})\n"
            f"Sound: {r.sound_type}\n"
            f"What it means: {r.meaning}\n"
            f"What to do: {r.advice}")


# ----------------------------------------------------------------------
# Self-test: run `python -m pawwatch.sound`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    samples = [
        ("A dog barking (normal)",       "Rex",  "Dog", SoundReading(loudness=75, pitch_hz=1200, seconds=0.5)),
        ("A dog coughing (abnormal)",    "Rex",  "Dog", SoundReading(loudness=55, pitch_hz=500,  seconds=0.4)),
        ("A dog yelping in pain (urgent)","Rex", "Dog", SoundReading(loudness=85, pitch_hz=2500, seconds=0.2)),
        ("A cat hissing (abnormal)",     "Milo", "Cat", SoundReading(loudness=65, pitch_hz=5000, seconds=1.0)),
        ("A cat purring (normal)",       "Milo", "Cat", SoundReading(loudness=20, pitch_hz=80,   seconds=10)),
        ("A horse groaning (urgent)",    "Bella","Horse",SoundReading(loudness=50, pitch_hz=150,  seconds=3)),
        ("Too quiet for too long",       "Rex",  "Dog", SoundReading(loudness=2,  pitch_hz=0,    seconds=60)),
    ]
    for label, name, species, reading in samples:
        print(f"--- {label} ---")
        print(sound_report(name, species, reading))
        print()
