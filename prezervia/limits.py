"""
prezervia.limits — be honest about what we can't do, and guard the learning.

Two things a skeptical customer rightly pushed on:

  #3  "What can't it catch?"
         -> what_we_cannot_detect() is a plain, honest list. We detect unusual
            NUMBERS (heart, breathing, temperature, movement, location). We do
            NOT see pain, a limp, a lump, vomiting, or diagnose any illness.
            Saying this out loud is what earns trust.

  #12 "I override alerts. What if I'm wrong and teach it to ignore real illness?"
         -> override_guard() decides whether an override is SAFE to learn from.
            Some readings must NEVER be learned as 'normal', no matter how many
            times the owner dismisses them:
              * a fever or very low temperature (clinical, not age/fitness),
              * a value that is FAR outside normal (not a little-old-dog drift),
              * a reading that is part of a worsening trend.
            Those overrides still dismiss the single alert, but they are NOT
            fed into the learned 'new normal'. So a mistaken override can't
            quietly blind the app to a real problem.

We are an abnormal-NUMBER detector, not an illness detector. These tools keep
that promise honest.

IMPORT:
    from prezervia.limits import what_we_cannot_detect, override_guard
"""

from __future__ import annotations

from .personalize import personalized_profile


# ----------------------------------------------------------------------
# #3 — the honest "what we can't see" list
# ----------------------------------------------------------------------
def what_we_cannot_detect() -> dict:
    """Plain, honest limits. Show this in the app's info screen."""
    return {
        "we_detect": [
            "Unusual heart rate",
            "Unusual breathing rate",
            "Unusual body temperature",
            "Unusual movement / stillness",
            "Where your pet is, and if they leave a safe zone",
        ],
        "we_cannot_detect": [
            "Pain, a limp, or how your pet is standing",
            "A lump, a wound, or a skin problem",
            "Vomiting, diarrhea, or what they ate",
            "Coughing, limping, or changes you'd see by looking",
            "Any specific illness or diagnosis",
        ],
        "message": ("Prezervia flags unusual NUMBERS early so you can act sooner. "
                    "It cannot see pain, lumps, or symptoms you'd notice by "
                    "looking, and it does not diagnose illness. It is a heads-up, "
                    "not a vet. When in doubt, see your vet."),
    }


# ----------------------------------------------------------------------
# #12 — guard: can we safely LEARN from this override?
# ----------------------------------------------------------------------
# A value this many 'normal widths' past the edge is too far to ever call normal.
_FAR_OUT_WIDTHS = 1.0


def override_guard(pet_name: str, readings: dict,
                   worsening: bool = False) -> dict:
    """Decide if an owner's override may be used to widen the learned normal.

    Returns {"learnable": bool, "blocked_signals": [...], "reason": ...}.

    The override ALWAYS dismisses the one alert (that's the owner's right).
    This only controls whether the reading is allowed to teach the app a new
    'normal' — because a wrong override must not blind us to a real problem.
    """
    profile = personalized_profile(pet_name)
    blocked = []
    reasons = []

    for sig, val in readings.items():
        # 1. temperature is clinical — never learn a fever/hypothermia as normal
        if sig == "temp":
            lo, hi = profile.range_for(sig)
            if val < lo or val > hi:
                blocked.append(sig)
                reasons.append("temperature out of range is never treated as "
                               "normal (a fever is a fever at any age)")
            continue

        # 2. a value FAR outside normal is not an old-dog drift
        lo, hi = profile.range_for(sig)
        width = max(hi - lo, 1e-6)
        if val > hi and (val - hi) / width > _FAR_OUT_WIDTHS:
            blocked.append(sig)
            reasons.append(f"{sig} is far above normal — too far to call normal")
        elif val < lo and (lo - val) / width > _FAR_OUT_WIDTHS:
            blocked.append(sig)
            reasons.append(f"{sig} is far below normal — too far to call normal")

    # 3. if the pet is trending worse, don't learn this away either
    if worsening and not blocked:
        blocked = [s for s in readings if s != "temp"]
        reasons.append("readings are trending worse — not a stable new normal")

    learnable = not blocked
    return {
        "pet_name": pet_name,
        "learnable": learnable,
        "blocked_signals": sorted(set(blocked)),
        "reason": ("Safe to learn from this override."
                   if learnable else "; ".join(sorted(set(reasons)))),
        "note": ("The alert is still dismissed for you — we just won't teach the "
                 "app to ignore this pattern in future." if not learnable else ""),
    }


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.limits
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake

    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 14, "weight_kg": 2.5}, save=True)

    print("--- #3 what we can't detect ---")
    lim = what_we_cannot_detect()
    print("   WE DETECT:   ", "; ".join(lim["we_detect"][:3]), "...")
    print("   WE CANNOT:   ", "; ".join(lim["we_cannot_detect"][:3]), "...")
    print("  ", lim["message"])

    print("\n--- #12 override guard ---")
    # a) old dog moving a little slow -> safe to learn
    print("   slow movement (old dog):")
    print("     ", override_guard("Rex", {"movement": 15}))
    # b) a fever the owner tries to dismiss -> NEVER learned
    print("   owner overrides a fever:")
    g = override_guard("Rex", {"temp": 40.6})
    print("     ", "learnable:", g["learnable"], "| reason:", g["reason"])
    print("     ", g["note"])
    # c) heart racing far out -> NEVER learned
    print("   owner overrides a racing heart (far out):")
    g = override_guard("Rex", {"hr": 260})
    print("     ", "learnable:", g["learnable"], "| reason:", g["reason"])
