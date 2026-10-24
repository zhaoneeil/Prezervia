"""
pawwatch.collar — read the collar's sensors and find what is not normal.

This is the "app installation" side: the code that would run on (or next to)
the neck collar, read each sensor once a second, bundle the numbers into one
reading, and check that reading against the animal's healthy ranges.

Sensors on the collar:
    * heart rate     -> beats per minute        (optical / ECG sensor)
    * breathing      -> breaths per minute       (chest-movement sensor)
    * temperature    -> degrees Celsius          (skin temp sensor)
    * movement       -> 0-100 activity proxy      (accelerometer)
    * sound          -> 0-100 loudness proxy      (microphone)   [NEW]
    * gps            -> latitude / longitude      (GPS chip)      [NEW]

The first four have per-breed healthy ranges and go through pawwatch's
`check_alarm`. Sound and GPS do not have a vet range per breed, so they use
one shared rule each, set here on the collar.

No hardware is attached in this demo, so each sensor is FAKED the same way the
app fakes vitals. Swap the `read()` body of each sensor for the real driver
call when a real collar exists; nothing else changes.

IMPORT:
    from pawwatch.collar import Collar
    from pawwatch import find

    profile = find("Dog", "Labrador Retriever", "1-7")
    collar  = Collar(profile)
    reading = collar.read_all()          # one bundle of every sensor
    report  = collar.check(reading)      # what is abnormal, and whether to alarm
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from . import AnimalProfile, check_alarm, AlarmResult
from .gps import Fix, SafeZone, GpsTracker


# ----------------------------------------------------------------------
# Shared rules for the two NEW signals (not per-breed)
# ----------------------------------------------------------------------
# Sound is a 0-100 loudness proxy from the collar microphone. A pet that is
# crying, whining or barking non-stop is loud for a long time. One loud bark
# is normal; sustained loudness is not. We flag a reading above this line.
SOUND_LOUD_OVER = 70          # 0-100; above this = "loud right now"

# Barely any sound for a very long time can also matter (an unconscious pet),
# but silence alone is usually fine, so we only flag LOUD here.

# GPS speed: a collar moving far too fast for the animal usually means the pet
# is in a car / being carried / the reading is wrong — worth a glance.
SPEED_FAST_OVER_MPS = 8.0     # ~29 km/h; faster than a pet runs on its own


# ----------------------------------------------------------------------
# One bundle of everything the collar measured at one moment
# ----------------------------------------------------------------------
@dataclass
class SensorReading:
    """Every sensor on the collar, read at the same moment."""
    at: float = field(default_factory=time.time)   # unix seconds
    hr: float = 0.0            # heart beats / minute
    resp: float = 0.0          # breaths / minute
    temp: float = 0.0          # degrees Celsius
    movement: float = 0.0      # 0-100 activity proxy
    sound: float = 0.0         # 0-100 loudness proxy          [NEW]
    fix: Fix | None = None     # GPS point                      [NEW]

    def vitals(self) -> dict[str, float]:
        """Just the four per-breed signals, for pawwatch.check_alarm."""
        return {"hr": self.hr, "resp": self.resp,
                "temp": self.temp, "movement": self.movement}


# ----------------------------------------------------------------------
# What the collar thinks after one reading
# ----------------------------------------------------------------------
@dataclass
class CollarReport:
    """The full verdict: vitals, sound, location — and one overall alarm."""
    reading: SensorReading
    vitals: AlarmResult                   # hr / resp / temp / movement verdict
    sound_loud: bool = False
    moving_too_fast: bool = False
    outside_safe_zone: bool = False
    metres_from_home: float = 0.0
    reasons: list[str] = field(default_factory=list)   # plain-language flags
    alarm: bool = False                   # True if ANYTHING is abnormal


# ----------------------------------------------------------------------
# The collar
# ----------------------------------------------------------------------
class Collar:
    """Reads the collar's sensors and checks them against the animal.

    Give it the animal's profile (from pawwatch.find) and, if you want the
    GPS fence, a SafeZone. Call read_all() to get one reading, then check()
    to get the verdict. Or call tick() to do both at once.
    """

    def __init__(self, profile: AnimalProfile,
                 safe_zone: SafeZone | None = None,
                 seed: int | None = None):
        self.profile = profile
        self._rng = random.Random(seed)
        self._gps = GpsTracker(safe_zone) if safe_zone else None
        self._home = safe_zone.center if safe_zone else None

    # ---- read each sensor (FAKED — swap for the real driver) ---------
    def _read_hr(self) -> float:
        lo, hi = self.profile.hr
        return round(self._rng.uniform(lo, hi), 1)

    def _read_resp(self) -> float:
        lo, hi = self.profile.resp
        return round(self._rng.uniform(lo, hi), 1)

    def _read_temp(self) -> float:
        lo, hi = self.profile.temp_c
        return round(self._rng.uniform(lo, hi), 1)

    def _read_movement(self) -> float:
        lo, hi = self.profile.movement
        return round(self._rng.uniform(lo, hi), 1)

    def _read_sound(self) -> float:
        # Mostly quiet, with the odd louder moment.
        base = self._rng.uniform(5, 35)
        if self._rng.random() < 0.15:          # sometimes a bark / whine
            base = self._rng.uniform(55, 90)
        return round(base, 1)

    def _read_fix(self) -> Fix | None:
        if self._home is None:
            return None
        # Drift a few metres around home (~0.00003 deg ≈ 3 m).
        jitter = lambda: self._rng.uniform(-0.00005, 0.00005)
        return Fix(self._home.lat + jitter(), self._home.lon + jitter())

    def read_all(self) -> SensorReading:
        """Read every sensor once and bundle the numbers."""
        return SensorReading(
            hr=self._read_hr(),
            resp=self._read_resp(),
            temp=self._read_temp(),
            movement=self._read_movement(),
            sound=self._read_sound(),
            fix=self._read_fix(),
        )

    # ---- check a reading against the rules ---------------------------
    def check(self, reading: SensorReading) -> CollarReport:
        """Turn one reading into a verdict with plain-language reasons."""
        vitals = check_alarm(self.profile, reading.vitals())
        report = CollarReport(reading=reading, vitals=vitals)
        report.reasons.extend(vitals.abnormal)   # hr/resp/temp/movement flags

        # NEW signal 1: sound
        if reading.sound > SOUND_LOUD_OVER:
            report.sound_loud = True
            report.reasons.append(
                f"loud for this long (sound={reading.sound}/100)")

        # NEW signal 2: GPS — speed and safe zone
        if reading.fix is not None and self._gps is not None:
            gps = self._gps.update(reading.fix)
            report.metres_from_home = round(gps.metres_from_home, 1)
            if gps.speed_mps > SPEED_FAST_OVER_MPS:
                report.moving_too_fast = True
                report.reasons.append(
                    f"moving very fast ({round(gps.speed_mps, 1)} m/s)")
            if gps.fence_alarm:
                report.outside_safe_zone = True
                report.reasons.append(
                    f"left the safe zone ({round(gps.metres_outside)} m past it)")

        report.alarm = bool(report.reasons)
        return report

    # ---- do both at once ---------------------------------------------
    def tick(self) -> CollarReport:
        """Read every sensor and return the verdict in one call."""
        return self.check(self.read_all())


# ----------------------------------------------------------------------
# Tiny demo — run: python -m pawwatch.collar
# ----------------------------------------------------------------------
def _demo() -> None:
    from . import find

    profile = find("Dog", "Labrador Retriever", "1-6")
    home = Fix(37.7749, -122.4194)           # a home point
    collar = Collar(profile, safe_zone=SafeZone(home, radius_m=50), seed=1)

    print(f"Collar on: {profile.key}")
    print("Reading the collar 5 times (once a 'second'):\n")
    for i in range(5):
        reading = collar.read_all()
        reading.at = home.at + i          # space readings 1 second apart
        if reading.fix is not None:
            reading.fix = Fix(reading.fix.lat, reading.fix.lon, at=home.at + i)
        report = collar.check(reading)
        r = report.reading
        line = (f"[{i+1}] hr={r.hr} resp={r.resp} temp={r.temp} "
                f"move={r.movement} sound={r.sound}")
        print(line)
        if report.alarm:
            print("     ⚠ ALARM:", "; ".join(report.reasons))
        else:
            print("     ok — all normal")


if __name__ == "__main__":
    _demo()
