#!/usr/bin/env python3
"""
summarize.py  —  PawWatch data summary + charts.

Reads animal_vitals.csv, prints a plain-language summary, and saves charts
the main app can display. Also writes animal_vitals.json so the web app can
load the SAME numbers instead of hard-coding them.

Run:
    pip install pandas matplotlib
    python3 summarize.py

Outputs (in this folder):
    animal_vitals.json          -> feed the web app
    chart_hr_by_species.png     -> heart-rate range per animal
    chart_hr_vs_size.png        -> how heart rate falls as size grows
    summary.txt                 -> plain-text summary
"""

import json
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no screen needed; just save files
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
CSV = HERE / "animal_vitals.csv"


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df["hr_mid"] = (df["hr_min"] + df["hr_max"]) / 2
    df["resp_mid"] = (df["resp_min"] + df["resp_max"]) / 2
    df["temp_mid"] = (df["temp_min_c"] + df["temp_max_c"]) / 2
    df["height_mid_cm"] = (df["height_cm_min"] + df["height_cm_max"]) / 2
    return df


# ------------------------------------------------------------------
# 1. Plain-text summary
# ------------------------------------------------------------------
def write_summary(df: pd.DataFrame) -> None:
    lines = []
    lines.append("PawWatch — animal vital summary")
    lines.append("=" * 40)
    lines.append(f"Animals in dataset: {df['breed_or_type'].nunique()} "
                 f"types across {df['species'].nunique()} species.\n")

    by_species = (df.groupby("species")[["hr_mid", "resp_mid", "temp_mid"]]
                    .mean().round(1)
                    .sort_values("hr_mid", ascending=False))
    lines.append("Average heart rate, breathing, temp per species")
    lines.append("(sorted: fastest heart first)\n")
    lines.append(by_species.to_string())

    fastest = by_species.index[0]
    slowest = by_species.index[-1]
    lines.append(
        f"\nBiggest animals have the slowest hearts. "
        f"{fastest} is fastest; {slowest} is slowest."
    )

    out = HERE / "summary.txt"
    out.write_text("\n".join(lines))
    print(out.read_text())
    print(f"\n[saved] {out}")


# ------------------------------------------------------------------
# 2. Chart: heart-rate range (min..max) per animal type
# ------------------------------------------------------------------
def chart_hr_range(df: pd.DataFrame) -> None:
    d = df.sort_values("hr_mid")
    fig, ax = plt.subplots(figsize=(9, 11))
    y = range(len(d))
    ax.hlines(y, d["hr_min"], d["hr_max"], color="#4da3ff", linewidth=6, alpha=.8)
    ax.plot(d["hr_mid"], y, "o", color="#ff5468")
    ax.set_yticks(list(y))
    ax.set_yticklabels(d["breed_or_type"], fontsize=8)
    ax.set_xlabel("Heart rate (beats per minute) — healthy resting range")
    ax.set_title("Healthy heart-rate range by animal")
    ax.grid(axis="x", alpha=.3)
    fig.tight_layout()
    path = HERE / "chart_hr_by_species.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"[saved] {path}")


# ------------------------------------------------------------------
# 3. Chart: heart rate vs real body height (cm)
# ------------------------------------------------------------------
def chart_hr_vs_size(df: pd.DataFrame) -> None:
    d = df.sort_values("height_mid_cm")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(d["height_mid_cm"], d["hr_mid"], color="#3ad29f", s=60, alpha=.8)
    ax.set_xlabel("Body height at shoulder (cm)")
    ax.set_ylabel("Average heart rate (bpm)")
    ax.set_title("Taller body → slower heart")
    ax.set_xscale("log")
    for _, r in d.iterrows():
        ax.annotate(r["species"], (r["height_mid_cm"], r["hr_mid"]),
                    fontsize=7, alpha=.7, xytext=(3, 3), textcoords="offset points")
    ax.grid(alpha=.3)
    fig.tight_layout()
    path = HERE / "chart_hr_vs_size.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"[saved] {path}")


# ------------------------------------------------------------------
# 3b. Chart: all collar signals for ONE animal, each as a normal band
#     This is what the collar checks a live reading against.
# ------------------------------------------------------------------
def chart_collar_bands(df: pd.DataFrame,
                       species: str = "Dog",
                       breed: str = "Labrador Retriever") -> None:
    row = df[(df["species"] == species) &
             (df["breed_or_type"] == breed)]
    if row.empty:
        print(f"[skip] no row for {species} / {breed}")
        return
    r = row.iloc[0]

    # Each collar signal: its healthy low..high, scaled 0..1 so very
    # different units (bpm, breaths, °C, 0-100) sit on one chart.
    signals = [
        ("Heart rate (bpm)",   r["hr_min"],   r["hr_max"],   40,  200),
        ("Breathing (/min)",   r["resp_min"], r["resp_max"], 5,   60),
        ("Temperature (°C)",   r["temp_min_c"], r["temp_max_c"], 36, 42),
        ("Movement (0-100)",   r["movement_score_min"], r["movement_score_max"], 0, 100),
        ("Sound (0-100)",      0,             70,            0,   100),   # NEW: collar rule
    ]

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (name, lo, hi, axmin, axmax) in enumerate(signals):
        n_lo = (lo - axmin) / (axmax - axmin)
        n_hi = (hi - axmin) / (axmax - axmin)
        ax.barh(i, n_hi - n_lo, left=n_lo, height=.5,
                color="#3ad29f", alpha=.7)
        ax.text(n_lo, i, f" {lo:g}", va="center", ha="right", fontsize=8)
        ax.text(n_hi, i, f"{hi:g} ", va="center", ha="left", fontsize=8)

    ax.set_yticks(range(len(signals)))
    ax.set_yticklabels([s[0] for s in signals])
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_xlabel("← low        healthy band        high →")
    ax.set_title(f"What the collar calls NORMAL — {breed}")
    ax.invert_yaxis()
    fig.tight_layout()
    path = HERE / "chart_collar_bands.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"[saved] {path}")


# ------------------------------------------------------------------
# 4. Export JSON the web app can load directly
# ------------------------------------------------------------------
def export_json(df: pd.DataFrame) -> None:
    data: dict = {}
    for _, r in df.iterrows():
        sp = r["species"]
        data.setdefault(sp, {"temp": {"min": r["temp_min_c"],
                                      "max": r["temp_max_c"], "unit": "°C"},
                             "breeds": {}})
        label = (f'{r["breed_or_type"]} — age {r["age_range_yrs"]} yr '
                 f'({r["height_cm_min"]}-{r["height_cm_max"]} cm, '
                 f'lifespan {r["typical_lifespan_yrs"]} yr)')
        data[sp]["breeds"][label] = {
            "hr": [int(r["hr_min"]), int(r["hr_max"])],
            "resp": [int(r["resp_min"]), int(r["resp_max"])],
            "activity": [int(r["movement_score_min"]), int(r["movement_score_max"])],
        }
    path = HERE / "animal_vitals.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[saved] {path}")


def main() -> None:
    df = load()
    write_summary(df)
    chart_hr_range(df)
    chart_hr_vs_size(df)
    chart_collar_bands(df)
    export_json(df)
    print("\nDone. Feed animal_vitals.json to the web app, and show the PNG charts.")


if __name__ == "__main__":
    main()
