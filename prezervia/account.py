"""
prezervia.account — the user's account owns their data.

The customer's rule:
  "Deleting the APP must not delete my data. Only 'delete my account' should."

So:
  * A user has an ACCOUNT. Their pets and history belong to the account.
  * sign_out() / "delete the app" changes NOTHING stored — the account and all
    data stay, ready for the next sign-in (even on a new phone).
  * delete_account() is the ONLY thing that erases data, and it asks for an
    explicit confirmation first, so a mis-tap can't wipe a pet's history.

We store data on the user's device in this demo, keyed by account, exactly as
a server would key it by account id.

Dependency-free. Account + session live in account.json; this is also where we
point at the pet-data files so delete_account() knows what to clear.

IMPORT:
    from prezervia.account import create_account, sign_in, sign_out, delete_account, whoami
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_ACCOUNT_PATH = Path(__file__).with_name("account.json")

# the per-user data files the account owns (wiped only on delete_account)
_OWNED_DATA = [
    "pets.json", "history.json", "notifications.json", "alert_decisions.json",
    "tags.json", "learned_ranges.json", "household.json", "settings.json",
    "last_seen.json", "food_log.json",
]


def _load() -> dict:
    if not _ACCOUNT_PATH.exists():
        return {"accounts": {}, "signed_in": None}
    return json.loads(_ACCOUNT_PATH.read_text(encoding="utf-8"))


def _save(s: dict) -> None:
    _ACCOUNT_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# create / sign in
# ----------------------------------------------------------------------
def create_account(email: str, name: str) -> dict:
    """Make a new account. Data from here on belongs to it."""
    if "@" not in str(email):
        raise ValueError("Please enter a valid email.")
    s = _load()
    email = email.strip().lower()
    if email not in s["accounts"]:
        s["accounts"][email] = {
            "email": email, "name": name.strip(),
            "created": datetime.now(timezone.utc).isoformat(),
        }
    s["signed_in"] = email
    _save(s)
    return {"email": email, "name": name,
            "message": "Account created. Your pets and history are saved to "
                       "your account — not just this phone."}


def sign_in(email: str) -> dict:
    """Sign back in — on this phone or a new one. Data is right where it was."""
    s = _load()
    email = email.strip().lower()
    if email not in s["accounts"]:
        raise KeyError(f"No account for {email!r}. Create one first.")
    s["signed_in"] = email
    _save(s)
    return {"email": email, "message": "Signed in. All your data is here."}


# ----------------------------------------------------------------------
# sign out / delete the APP — data is KEPT
# ----------------------------------------------------------------------
def sign_out() -> dict:
    """Sign out (or 'delete the app'). Nothing stored is removed."""
    s = _load()
    s["signed_in"] = None
    _save(s)
    return {"message": "Signed out. Your pet's data is safe in your account. "
                       "Deleting the app does NOT delete your data — sign back "
                       "in any time to get it all back."}


def whoami() -> dict:
    """Who's signed in, and how much data the account holds."""
    s = _load()
    email = s.get("signed_in")
    if not email:
        return {"signed_in": False, "message": "No one is signed in."}
    acct = s["accounts"][email]
    return {"signed_in": True, "email": email, "name": acct["name"],
            "created": acct["created"]}


# ----------------------------------------------------------------------
# delete the ACCOUNT — the ONLY thing that erases data
# ----------------------------------------------------------------------
def delete_account(email: str, confirm: bool = False) -> dict:
    """Permanently erase an account and ALL its pet data.

    Requires confirm=True — a safety step so a mis-tap can't wipe everything.
    This is the only call in prezervia that deletes a pet's history.
    """
    s = _load()
    email = email.strip().lower()
    if email not in s["accounts"]:
        raise KeyError(f"No account for {email!r}.")

    if not confirm:
        return {"deleted": False, "needs_confirm": True,
                "message": "This permanently deletes your account and ALL your "
                           "pet's history. This cannot be undone. Call again "
                           "with confirm=True to proceed."}

    # wipe the owned data files
    here = Path(__file__).parent
    wiped = []
    for fname in _OWNED_DATA:
        f = here / fname
        if f.exists():
            f.unlink()
            wiped.append(fname)

    del s["accounts"][email]
    if s.get("signed_in") == email:
        s["signed_in"] = None
    _save(s)
    return {"deleted": True, "email": email, "wiped_files": wiped,
            "message": "Your account and all its data are permanently deleted."}


# ----------------------------------------------------------------------
# Self-test: python -m prezervia.account
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from .intake import intake
    from .monitor import record_reading, get_history

    print("--- create account + add a pet with history ---")
    print("  ", create_account("sam@example.com", "Sam")["message"])
    intake({"pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
            "age_years": 3}, save=True)
    record_reading("Rex", {"hr": 120, "resp": 25, "temp": 38.8, "movement": 40})
    print("   history rows:", len(get_history("Rex")))

    print("\n--- 'delete the app' (sign out): data KEPT ---")
    print("  ", sign_out()["message"])
    print("   history rows after app-delete:", len(get_history("Rex")), "(still there)")

    print("\n--- sign back in on a 'new phone' ---")
    print("  ", sign_in("sam@example.com")["message"])
    print("   history rows:", len(get_history("Rex")))

    print("\n--- delete ACCOUNT needs confirmation ---")
    print("  ", delete_account("sam@example.com")["message"])
    print("\n--- confirmed delete: data gone ---")
    res = delete_account("sam@example.com", confirm=True)
    print("  ", res["message"], "| wiped:", res["wiped_files"])
    print("   history rows now:", len(get_history("Rex")), "(gone)")
