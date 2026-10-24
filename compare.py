#!/usr/bin/env python3
"""
compare.py — put a few animals side by side and pick which data to show.

Example: show 3 dogs, but only their breathing (resp) numbers.

    python compare.py --species Dog --limit 3 --columns resp
    python compare.py --species Dog --breed "Labrador Retriever,Beagle,Pug" --columns resp
    python compare.py --species Cat --columns hr,resp,temp

The table has one row per animal. You choose the columns, so you only see
the data you care about.
"""

from __future__ import annotations

import argparse

from pawwatch import load_animals, AnimalProfile


# Every column you can ask for, and how to read it off one animal.
# label        -> what shows in the table header
# value(a)     -> the text for that animal's cell
COLUMNS: dict[str, dict] = {
    "species":  {"label": "Species",        "value": lambda a: a.species},
    "breed":    {"label": "Breed / type",   "value": lambda a: a.breed_or_type},
    "age":      {"label": "Age (yrs)",      "value": lambda a: a.age_range_yrs},
    "lifespan": {"label": "Lifespan (yrs)", "value": lambda a: a.typical_lifespan_yrs},
    "height":   {"label": "Height (cm)",    "value": lambda a: f"{a.height_cm[0]}-{a.height_cm[1]}"},
    "hr":       {"label": "Heart rate",     "value": lambda a: f"{a.hr[0]}-{a.hr[1]} bpm"},
    "resp":     {"label": "Breathing",      "value": lambda a: f"{a.resp[0]}-{a.resp[1]} /min"},
    "temp":     {"label": "Temperature",    "value": lambda a: f"{a.temp_c[0]}-{a.temp_c[1]} C"},
    "movement": {"label": "Movement",       "value": lambda a: f"{a.movement[0]}-{a.movement[1]}"},
}

# What you get if you do not ask for any columns.
DEFAULT_COLUMNS = ["breed", "age", "hr", "resp", "temp"]


def pick_animals(species: str | None,
                 breeds: list[str] | None,
                 limit: int | None,
                 animals: list[AnimalProfile]) -> list[AnimalProfile]:
    """Choose which animals go in the table."""
    rows = animals
    if species:
        rows = [a for a in rows if a.species.lower() == species.lower()]
    if breeds:
        wanted = [b.strip().lower() for b in breeds]
        # keep the order the user listed the breeds in
        rows = sorted(
            [a for a in rows if a.breed_or_type.lower() in wanted],
            key=lambda a: wanted.index(a.breed_or_type.lower()),
        )
    if limit:
        rows = rows[:limit]
    return rows


def build_table(rows: list[AnimalProfile], columns: list[str]) -> tuple[list[str], list[list[str]]]:
    """Make a header row and the body rows, using only the chosen columns."""
    # "breed" is always nice to keep so you know which animal each row is.
    if "breed" not in columns and "species" not in columns:
        columns = ["breed"] + columns

    header = [COLUMNS[c]["label"] for c in columns]
    body = [[COLUMNS[c]["value"](a) for c in columns] for a in rows]
    return header, body


def print_table(header: list[str], body: list[list[str]]) -> None:
    """Print a plain, lined-up text table."""
    all_rows = [header] + body
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    print(line(header))
    print("-+-".join("-" * w for w in widths))
    for r in body:
        print(line(r))


def parse_columns(raw: str | None) -> list[str]:
    """Turn 'resp,hr' into ['resp', 'hr'] and check each name is real."""
    if not raw:
        return DEFAULT_COLUMNS
    cols = [c.strip().lower() for c in raw.split(",") if c.strip()]
    bad = [c for c in cols if c not in COLUMNS]
    if bad:
        ok = ", ".join(COLUMNS)
        raise SystemExit(f"Unknown column(s): {', '.join(bad)}. Pick from: {ok}")
    return cols


def main() -> None:
    p = argparse.ArgumentParser(description="Compare animals side by side.")
    p.add_argument("--species", help="e.g. Dog, Cat, Horse")
    p.add_argument("--breed", help="comma list of breeds, e.g. 'Beagle,Pug,Chihuahua'")
    p.add_argument("--limit", type=int, help="max number of animals to show")
    p.add_argument("--columns",
                   help=f"comma list; pick from: {', '.join(COLUMNS)}. "
                        f"Default: {', '.join(DEFAULT_COLUMNS)}")
    args = p.parse_args()

    animals = load_animals()
    breeds = args.breed.split(",") if args.breed else None
    rows = pick_animals(args.species, breeds, args.limit, animals)

    if not rows:
        raise SystemExit("No animals matched. Try a different --species or --breed.")

    columns = parse_columns(args.columns)
    header, body = build_table(rows, columns)
    print_table(header, body)
    print(f"\n{len(rows)} animal(s), showing: {', '.join(columns)}")


if __name__ == "__main__":
    main()
