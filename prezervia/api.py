"""Prezervia API — exposes the REAL detector to a web app over HTTP.

This is a thin bridge. Every route calls the real prezervia functions
(record_reading, rate_alert, exertion_check, home_screen, intake, load_pets),
so the web page shows genuine detector answers, never fake data.

Standard-library only — no Flask/FastAPI install needed (memory-friendly).

Run:
    .venv/bin/python -m prezervia.api            # serves on 127.0.0.1:8808
    .venv/bin/python -m prezervia.api 9000       # custom port

Routes (all JSON):
    GET  /api/pets                     -> saved pets + their status dot
    POST /api/intake   {pet fields}    -> sign up a pet, match ranges
    POST /api/reading  {name,hr,...}   -> record a reading, get alarm + reasons
    POST /api/severity {name,hr,...}   -> rate how bad (watch/call soon/call now)
    POST /api/exertion {name,hr,movement} -> running vs sick
    GET  /api/home                     -> multi-pet home screen (which needs me now)
    GET  /api/herd?species=Goat        -> herd rolling average + mass-shift warning
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from prezervia import monitor, severity, exertion, household, intake
from prezervia.intake import load_pets
from prezervia import connection
from prezervia.collar import Collar


# device links kept alive between calls, one per pet+transport
_LINKS: dict[str, "connection.Link"] = {}


def _device_connect(body: dict) -> dict:
    """Attach a Bluetooth or WiFi device to a pet and pair it (real Link)."""
    name = body.get("name") or body.get("pet_name") or ""
    how = (body.get("how") or "bluetooth").lower()
    if how not in ("bluetooth", "wifi"):
        raise ValueError("how must be 'bluetooth' or 'wifi'")
    link = connection.connect(name, how)
    paired = link.pair()
    _LINKS[f"{name}:{how}"] = link
    return {"pet_name": name, "how": how, "paired": bool(paired)}


def _device_upload(body: dict) -> dict:
    """Upload ONE reading from the attached device, through the real link.

    If explicit vitals are given, send those; otherwise the collar simulates
    one reading. Either way it travels through Link.send -> the app ingests it
    (history + notify-on-abnormal), exactly like the real wire.
    """
    name = body.get("name") or body.get("pet_name") or ""
    how = (body.get("how") or "bluetooth").lower()
    key = f"{name}:{how}"
    link = _LINKS.get(key)
    if link is None:                      # auto-connect if not paired yet
        link = connection.connect(name, how)
        link.pair()
        _LINKS[key] = link

    battery = body.get("battery_pct")
    vitals = {k: float(body[k]) for k in ("hr", "resp", "temp", "movement") if k in body}

    if vitals:
        # Build the wire packet directly (JSON-safe), send it over the real
        # transport, then run the app-side ingest — the same path Link.send
        # takes, so history + notify-on-abnormal behave identically.
        from prezervia.connection import CollarMessage, SendResult
        from datetime import datetime, timezone
        msg = CollarMessage(
            pet_name=name,
            when=datetime.now(timezone.utc).isoformat(),
            readings=vitals,
            gps=body.get("gps"),
            battery_pct=battery,
        )
        try:
            link.transport.send(msg)              # travels over BT/WiFi
            out = link._ingest(msg)               # app receives + records
            result = SendResult(ok=True, how=link.transport.name,
                                pet_name=name, alarm=out["alarm"],
                                reasons=out["reasons"], notified=out["notified"])
        except Exception as exc:
            result = SendResult(ok=False, how=link.transport.name,
                                pet_name=name, error=str(exc))
    else:
        # simulate a reading inside the pet's own matched profile
        from prezervia.intake import build_pet, match_profile
        from prezervia.connection import CollarMessage, SendResult
        from datetime import datetime, timezone
        import random
        saved = next((p for p in load_pets() if _pet_name(p) == name), None)
        if saved is None:
            raise KeyError(f"No saved pet named {name!r}. Add them in intake first.")
        pet = build_pet(_intake_form({
            "name": name, "species": saved.get("species", ""),
            "breed": saved.get("breed", ""), "age": saved.get("age_years", 1),
        }))
        prof = match_profile(pet)
        def span(rng):
            lo, hi = rng
            return round(random.uniform(lo, hi), 1)
        vit = {"hr": span(prof.hr), "resp": span(prof.resp),
               "temp": span(prof.temp_c), "movement": span(prof.movement)}
        msg = CollarMessage(pet_name=name,
                            when=datetime.now(timezone.utc).isoformat(),
                            readings=vit, battery_pct=battery)
        try:
            link.transport.send(msg)
            o = link._ingest(msg)
            out = {"ok": True, "how": link.transport.name, "pet_name": name,
                   "alarm": o["alarm"], "reasons": o["reasons"],
                   "notified": o["notified"], "vitals": vit}
        except Exception as exc:
            out = {"ok": False, "how": link.transport.name,
                   "pet_name": name, "error": str(exc)}
        return out

    return getattr(result, "__dict__", {"result": str(result)})


# ---- helpers that wrap the real detector -------------------------------

def _safe(fn, *a, **k):
    """Call a detector fn; turn any error into a clean JSON-able dict."""
    try:
        return {"ok": True, "data": fn(*a, **k)}
    except Exception as exc:  # pragma: no cover - defensive bridge
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _pet_name(pet: dict) -> str:
    """Saved pets use 'pet_name'; tolerate 'name' too."""
    return pet.get("pet_name") or pet.get("name") or ""


def _pets_with_status() -> list[dict]:
    out = []
    for pet in load_pets():
        name = _pet_name(pet)
        dot = _safe(_status_dot, name)
        out.append({"pet": pet, "status": dot.get("data")})
    return out


def _intake_form(body: dict) -> dict:
    """Map a friendly web form to the detector's required field names."""
    return {
        "pet_name": body.get("pet_name") or body.get("name") or "",
        "species": body.get("species", ""),
        "breed": body.get("breed", ""),
        "age_years": body.get("age_years") or body.get("age") or "",
        "weight_kg": body.get("weight_kg") or body.get("weight") or "",
        "height_cm": body.get("height_cm") or body.get("height") or "",
        "sex": body.get("sex", ""),
        "neutered": body.get("neutered", ""),
        "conditions": body.get("conditions", ""),
        "pet_id": body.get("pet_id", ""),
    }


def _status_dot(name: str):
    from prezervia.alerts import status_dot
    return status_dot(name)


def _reading_result(body: dict) -> dict:
    name = body.get("name") or body.get("pet_name") or ""
    readings = {
        k: body[k] for k in ("hr", "resp", "temp", "movement")
        if k in body and body[k] is not None
    }
    gps = body.get("gps")
    battery = body.get("battery_pct")
    res = monitor.record_reading(name, readings, gps=gps, battery_pct=battery)
    # record_reading returns a dict-like; normalise reasons to plain text.
    data = res if isinstance(res, dict) else {"result": str(res)}
    return data


def _severity_result(body: dict) -> dict:
    name = body.get("name") or ""
    readings = {k: body[k] for k in ("hr", "resp", "temp", "movement") if k in body}
    return severity.rate_alert(name, readings)


def _exertion_result(body: dict) -> dict:
    name = body.get("name") or ""
    hr = float(body.get("hr", 0))
    movement = float(body.get("movement", 0))
    r = exertion.exertion_check(name, hr, movement)
    # ExertionResult is a dataclass; expose its fields.
    return getattr(r, "__dict__", {"result": str(r)})


def _seed_sample_pets(body: dict) -> dict:
    """Create a varied set of demo pets — distinct names, species, breeds.

    Breeds are picked from the real dataset so each pet matches a profile.
    """
    import csv, random
    from collections import defaultdict
    from pathlib import Path

    # read real species -> breeds from the dataset
    csv_path = Path(__file__).with_name("animal_vitals.csv")
    by_species = defaultdict(list)
    try:
        with open(csv_path) as f:
            for r in csv.DictReader(f):
                sp = r.get("species") or r.get("Species")
                br = (r.get("breed_or_type") or r.get("breed") or r.get("Breed"))
                if sp and br:
                    by_species[sp].append(br)
    except Exception:
        pass

    names = ["Luna", "Milo", "Clover", "Pepper", "Juniper", "Biscuit",
             "Willow", "Gus", "Maple", "Rico", "Olive", "Dash",
             "Hazel", "Tofu", "Sunny", "Bramble"]
    random.shuffle(names)

    count = int(body.get("count", 5))
    species_pool = [s for s in by_species if by_species[s]]
    random.shuffle(species_pool)
    species_pick = species_pool[:count]           # distinct species, no repeats

    made = []
    used_names = set()
    for sp in species_pick:
        nm = next((n for n in names if n not in used_names), None)
        if nm is None:
            break
        used_names.add(nm)
        breed = random.choice(by_species[sp])
        age = random.choice([1, 2, 3, 4, 5, 6, 7])
        try:
            intake.intake(_intake_form({"name": nm, "species": sp,
                                        "breed": breed, "age": str(age)}))
            # one fresh reading so each has a status
            monitor.record_reading(nm, _sample_reading(sp, nm))
            made.append({"name": nm, "species": sp, "breed": breed})
        except Exception:
            pass
    return {"added": made, "count": len(made)}


def _sample_reading(species: str, name: str) -> dict:
    """A plausible in-range reading for a pet, using its matched profile."""
    import random
    from prezervia.intake import load_pets, build_pet, match_profile
    saved = next((p for p in load_pets() if _pet_name(p) == name), None)
    if not saved:
        return {"hr": 100, "resp": 24, "temp": 38.6, "movement": 40}
    try:
        pet = build_pet(_intake_form({"name": name,
                                      "species": saved.get("species", ""),
                                      "breed": saved.get("breed", ""),
                                      "age": saved.get("age_years", 1)}))
        prof = match_profile(pet)
        def span(rng):
            lo, hi = rng
            return round(random.uniform(lo, hi), 1)
        return {"hr": span(prof.hr), "resp": span(prof.resp),
                "temp": span(prof.temp_c), "movement": span(prof.movement)}
    except Exception:
        return {"hr": 100, "resp": 24, "temp": 38.6, "movement": 40}


def _vet_bundle(body: dict) -> dict:
    """Assemble a REAL report for a vet: latest reading, reasons, severity, GPS."""
    from prezervia.history import get_history
    name = body.get("name") or body.get("pet_name") or ""
    hist = _safe(get_history, name).get("data") or []
    if not hist:
        return {"pet_name": name, "has_data": False,
                "text": f"No readings yet for {name}. Take a vital check first."}
    newest = hist[0]
    r = newest.get("readings", newest)
    vitals = {k: r.get(k) for k in ("hr", "resp", "temp", "movement")}
    sev = _safe(severity.rate_alert, name, {k: v for k, v in vitals.items() if v is not None})
    sev_data = sev.get("data") or {}
    gps = newest.get("gps") or r.get("gps")
    when = newest.get("when", "")

    lines = [f"Prezervia report for {name}", f"Time: {when}", ""]
    lines.append("Latest vitals:")
    for k, label in (("hr", "Heart rate"), ("resp", "Breathing"),
                     ("temp", "Temperature"), ("movement", "Movement")):
        if vitals.get(k) is not None:
            lines.append(f"  {label}: {vitals[k]}")
    if sev_data:
        lines.append("")
        lines.append(f"Assessment: {sev_data.get('verdict', '')}")
    if gps:
        lines.append(f"Location: {gps.get('lat')}, {gps.get('lon')}")
    text = "\n".join(lines)
    return {"pet_name": name, "has_data": True, "vitals": vitals,
            "severity": sev_data, "gps": gps, "when": when, "text": text}


def _seed_demo_herd(body: dict) -> dict:
    """Sign up a small demo herd and give them readings, so herd analytics shows."""
    species = body.get("species", "Goat")
    breed = {"Goat": "Nubian", "Sheep": "Merino", "Cow": "Holstein",
             "Dog": "Labrador Retriever", "Cat": "Domestic Shorthair"}.get(species, "Mixed")
    made = []
    # two steady, two hot — so the mass-shift warning can trigger
    plan = [("Billy", 39.0), ("Nanny", 39.1), ("Daisy", 40.1), ("Clover", 40.3)]
    for nm, temp in plan:
        try:
            intake.intake(_intake_form({"name": nm, "species": species,
                                        "breed": breed, "age": "4"}))
            monitor.record_reading(nm, {"hr": 90, "resp": 22, "temp": temp, "movement": 35})
            made.append(nm)
        except Exception:
            pass
    return {"species": species, "added": made}


def _herd_result(species: str) -> dict:
    """Rolling group average for one species + a mass-shift warning.

    Reads each pet's newest reading from history and aggregates by species.
    """
    from prezervia.history import get_history  # real history reader

    members, temps, hrs = [], [], []
    for pet in load_pets():
        if str(pet.get("species", "")).lower() != species.lower():
            continue
        name = _pet_name(pet)
        hist = _safe(get_history, name).get("data") or []
        newest = hist[0] if hist else None
        if not newest:
            continue
        r = newest.get("readings", newest)
        members.append({"name": name, "temp": r.get("temp"), "hr": r.get("hr")})
        if isinstance(r.get("temp"), (int, float)):
            temps.append(r["temp"])
        if isinstance(r.get("hr"), (int, float)):
            hrs.append(r["hr"])

    avg_temp = round(sum(temps) / len(temps), 2) if temps else None
    avg_hr = round(sum(hrs) / len(hrs), 1) if hrs else None

    # Mass-illness signal: most of the herd running hot at once.
    hot = [t for t in temps if t and t >= 39.5]
    share_hot = (len(hot) / len(temps)) if temps else 0.0
    mass_warning = len(temps) >= 3 and share_hot >= 0.6

    return {
        "species": species,
        "count": len(members),
        "avg_temp": avg_temp,
        "avg_hr": avg_hr,
        "members": members,
        "share_hot": round(share_hot, 2),
        "mass_illness_warning": mass_warning,
    }


# ---- HTTP plumbing -----------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):  # CORS preflight
        self._send({}, 204)

    def log_message(self, *a):  # quiet server
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)
        if path == "/api/pets":
            self._send({"ok": True, "pets": _pets_with_status()})
        elif path == "/api/home":
            self._send(_safe(household.home_screen))
        elif path == "/api/herd":
            species = (q.get("species") or [""])[0]
            if not species:
                self._send({"ok": False, "error": "species required"}, 400)
            else:
                self._send({"ok": True, "data": _herd_result(species)})
        elif path in ("/api/health", "/health"):
            self._send({"ok": True, "service": "prezervia-api"})
        elif path == "/api/vet/pdf":
            name = (q.get("name") or [""])[0]
            if not name:
                self._send({"ok": False, "error": "name required"}, 400); return
            try:
                import tempfile, os
                from prezervia.vet_pdf import build_vet_pdf
                tmp = os.path.join(tempfile.gettempdir(), f"prezervia_{name}.pdf")
                build_vet_pdf(name, tmp)
                data = open(tmp, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition",
                                 f'inline; filename="Prezervia-{name}.pdf"')
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                self._send({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        else:
            self._send({"ok": False, "error": "unknown route"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        if path == "/api/intake":
            self._send(_safe(lambda: intake.intake(_intake_form(body))[0].__dict__))
        elif path == "/api/reading":
            self._send(_safe(_reading_result, body))
        elif path == "/api/severity":
            self._send(_safe(_severity_result, body))
        elif path == "/api/exertion":
            self._send(_safe(_exertion_result, body))
        elif path == "/api/device/connect":
            self._send(_safe(_device_connect, body))
        elif path == "/api/device/upload":
            self._send(_safe(_device_upload, body))
        elif path == "/api/vet/bundle":
            self._send(_safe(_vet_bundle, body))
        elif path == "/api/herd/demo":
            self._send(_safe(_seed_demo_herd, body))
        elif path == "/api/pets/sample":
            self._send(_safe(_seed_sample_pets, body))
        else:
            self._send({"ok": False, "error": "unknown route"}, 404)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    port = int(argv[0]) if argv else 8808
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Prezervia API on http://127.0.0.1:{port}  (real detector, Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
