"""
prezervia.history — all the "reading history" code in one place.

Every reading a pet's collar sends is saved here, healthy or not. This file
holds everything about that log: what one saved reading looks like, where the
file lives, how a reading is added, and how the app reads "last week" back out
for its charts.

Notifications and the tap-the-alert "why" text live in prezervia.monitor, which
imports from here. The app can keep importing those names from monitor as
before — monitor re-exports what moved.

IMPORT:
    from prezervia.history import HistoryEntry, add_history, get_history

Dependency-free; writes JSON next to the module, like prezervia.intake.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

# The readings log lives next to the module, like pets.json.
_HISTORY_PATH = Path(__file__).with_name("history.json")


# ----------------------------------------------------------------------
# One stored reading
# ----------------------------------------------------------------------
@dataclass
class HistoryEntry:
    pet_name: str
    when: str                       # ISO time, UTC
    readings: dict                  # {"hr": 210, ...}
    alarm: bool                     # was it abnormal?
    abnormal: list = field(default_factory=list)   # ["hr=210 (HIGH)", ...]
    reasons: list = field(default_factory=list)    # list of reason sentences
    gps: dict | None = None         # {"lat":.., "lon":..} if provided


# ----------------------------------------------------------------------
# Writing one reading into the log
# ----------------------------------------------------------------------
def add_history(entry: HistoryEntry) -> dict:
    """Append one reading to the history log (always — healthy or not).

    Returns the saved record as a plain dict.
    """
    record = asdict(entry)
    _append_json(_HISTORY_PATH, record)
    return record


# ----------------------------------------------------------------------
# Reading history back out — for charts / "last week"
# ----------------------------------------------------------------------
def get_history(pet_name: str | None = None, limit: int | None = None) -> list[dict]:
    """Return saved readings, newest first.

    pet_name : filter to one pet, or None for all pets.
    limit    : keep only the newest N.
    """
    rows = _read_json(_HISTORY_PATH)
    if pet_name:
        rows = [r for r in rows if r.get("pet_name") == pet_name]
    rows.sort(key=lambda r: r.get("when", ""), reverse=True)
    return rows[:limit] if limit else rows


# ----------------------------------------------------------------------
# Small JSON helpers (same style as intake.py) — shared with monitor
# ----------------------------------------------------------------------
def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _append_json(path: Path, record: dict) -> None:
    rows = _read_json(path)
    rows.append(record)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# Self-test: run `python -m prezervia.history`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("--- add two readings ---")
    add_history(HistoryEntry(
        pet_name="Rex", when="2026-10-24T19:00:00+00:00",
        readings={"hr": 120}, alarm=False))
    add_history(HistoryEntry(
        pet_name="Rex", when="2026-10-24T19:03:00+00:00",
        readings={"hr": 210}, alarm=True, abnormal=["hr=210 (HIGH)"]))

    print("--- history (newest first) ---")
    for h in get_history("Rex"):
        print(f"   {h['when'][:19]}  alarm={h['alarm']}  {h['readings']}")
