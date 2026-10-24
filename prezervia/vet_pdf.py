"""Build a clean, printable PDF report for a veterinarian.

It shows the pet's recorded data — profile, a vitals table, and trend graphs —
and nothing else. It does NOT diagnose, does NOT say "normal" or "abnormal",
and offers no assessment: reading the data is the vet's job. The only verdict
on the page is a line stating exactly that.

Uses matplotlib (already installed) to lay out the page and save it as PDF.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                       # no display needed
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from prezervia.history import get_history
from prezervia.intake import load_pets, build_pet, match_profile


_SIGNALS = [("hr", "Heart rate", "bpm"),
            ("resp", "Breathing", "/min"),
            ("temp", "Temperature", "°C"),
            ("movement", "Movement", "/100")]


def _pet_record(name: str) -> dict | None:
    for p in load_pets():
        if (p.get("pet_name") or p.get("name")) == name:
            return p
    return None


def _series(history: list[dict], key: str):
    """Return (x indices, values) for one signal, oldest→newest."""
    rows = list(reversed(history))          # history is newest-first
    xs, ys = [], []
    for i, row in enumerate(rows):
        r = row.get("readings", row)
        v = r.get(key)
        if isinstance(v, (int, float)):
            xs.append(i); ys.append(v)
    return xs, ys


def build_vet_pdf(name: str, out_path: str | Path) -> str:
    """Write a vet PDF for one pet. Returns the path written."""
    history = get_history(name) or []
    pet = _pet_record(name) or {}
    ranges = {}
    try:
        p = build_pet({"pet_name": name,
                       "species": pet.get("species", ""),
                       "breed": pet.get("breed", ""),
                       "age_years": pet.get("age_years", 1)})
        prof = match_profile(p)
        ranges = {"hr": prof.hr, "resp": prof.resp,
                  "temp": prof.temp_c, "movement": prof.movement}
    except Exception:
        ranges = {}

    out_path = str(out_path)
    with PdfPages(out_path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))     # A4 portrait
        fig.patch.set_facecolor("white")

        # --- header ---
        fig.text(0.07, 0.95, "Prezervia", fontsize=22, fontweight="bold",
                 color="#2B2320")
        fig.text(0.07, 0.925, "Animal monitoring report", fontsize=11,
                 color="#8A7E76")
        fig.text(0.93, 0.95, datetime.now().strftime("%d %b %Y, %H:%M"),
                 fontsize=10, color="#8A7E76", ha="right")
        fig.add_artist(plt.Line2D([0.07, 0.93], [0.915, 0.915],
                                  color="#ECE4DB", lw=1, transform=fig.transFigure))

        # --- pet profile block ---
        prof_lines = [
            f"Name: {name}",
            f"Species / breed: {pet.get('species','—')} / {pet.get('breed','—')}",
            f"Age: {pet.get('age_years','—')} years",
        ]
        if pet.get("weight_kg"):
            prof_lines.append(f"Weight: {pet['weight_kg']} kg")
        fig.text(0.07, 0.885, "Patient", fontsize=12, fontweight="bold",
                 color="#2B2320")
        fig.text(0.07, 0.86, "\n".join(prof_lines), fontsize=10,
                 color="#2B2320", va="top", linespacing=1.6)

        # --- reference ranges (the vet's own baselines, shown as data) ---
        if ranges:
            rl = ["Reference ranges used (source: Merck / VCA):"]
            for k, label, unit in _SIGNALS:
                if k in ranges:
                    lo, hi = ranges[k]
                    rl.append(f"   {label}: {lo}–{hi} {unit}")
            fig.text(0.52, 0.885, "Baselines", fontsize=12, fontweight="bold",
                     color="#2B2320")
            fig.text(0.52, 0.86, "\n".join(rl[1:]), fontsize=9.5,
                     color="#2B2320", va="top", linespacing=1.6)

        # --- trend graphs: one small axis per signal ---
        if history:
            positions = [(0.08, 0.50), (0.56, 0.50), (0.08, 0.26), (0.56, 0.26)]
            for (key, label, unit), (left, bottom) in zip(_SIGNALS, positions):
                ax = fig.add_axes([left, bottom, 0.37, 0.17])
                xs, ys = _series(history, key)
                if ys:
                    ax.plot(xs, ys, color="#B8784A", lw=1.8, marker="o",
                            markersize=3)
                    if key in ranges:
                        lo, hi = ranges[key]
                        ax.axhspan(lo, hi, color="#7FC9A0", alpha=0.12)
                        ax.axhline(lo, color="#cdeedb", lw=0.8)
                        ax.axhline(hi, color="#cdeedb", lw=0.8)
                ax.set_title(f"{label} ({unit})", fontsize=10,
                             color="#2B2320", loc="left")
                ax.tick_params(labelsize=7, colors="#8A7E76")
                for s in ax.spines.values():
                    s.set_color("#ECE4DB")
                ax.set_xlabel("reading #", fontsize=7, color="#8A7E76")
        else:
            fig.text(0.5, 0.4, "No readings recorded yet.",
                     fontsize=12, color="#8A7E76", ha="center")

        # --- latest-reading table ---
        if history:
            newest = history[0]
            r = newest.get("readings", newest)
            rows = []
            for k, label, unit in _SIGNALS:
                v = r.get(k)
                rows.append([label, f"{v} {unit}" if v is not None else "—"])
            ax = fig.add_axes([0.08, 0.10, 0.84, 0.10]); ax.axis("off")
            ax.set_title("Most recent reading", fontsize=12, fontweight="bold",
                         color="#2B2320", loc="left", pad=10)
            tbl = ax.table(cellText=rows, colLabels=["Signal", "Value"],
                           cellLoc="left", loc="center")
            tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.5)

        # --- the ONLY verdict on the page ---
        fig.text(0.07, 0.055,
                 "This report shows recorded data only. Prezervia does not "
                 "diagnose and makes no assessment of whether these values are "
                 "healthy. Interpretation is for the attending veterinarian.",
                 fontsize=9, color="#8A7E76", va="top", wrap=True)

        pdf.savefig(fig)
        plt.close(fig)

    return out_path


if __name__ == "__main__":
    print(build_vet_pdf("Rex", "vet_report.pdf"))
