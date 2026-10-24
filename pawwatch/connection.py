"""
pawwatch.connection — connect a collar to the app and send readings to it.

This is the "pipe" between two sides:

    COLLAR side  ──(Bluetooth or WiFi)──▶  APP side

The collar packs one sensor reading into a tiny message, sends it over the
link the owner picked (Bluetooth OR WiFi), and the app receives the message
and feeds it into pawwatch exactly like a reading that arrived any other way
(``record_reading`` — history + notify-on-abnormal).

Nothing changes about how the app decides "abnormal". This file only MOVES
the numbers from the collar to the app.

No real radio is attached in this demo, so each transport is FAKED: it just
hands the message straight to the other side in memory. Swap the ``send`` /
``_deliver`` body of a transport for a real Bluetooth (e.g. ``bleak``) or
WiFi (e.g. an HTTP POST / MQTT publish) driver when real hardware exists —
nothing else in the app changes.

IMPORT:
    from pawwatch.connection import connect, Link

    link = connect("Rex", how="bluetooth")   # or how="wifi"
    link.pair()                               # one-time handshake
    result = link.send(collar.tick())         # push one reading to the app
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

from .collar import CollarReport, SensorReading
from .monitor import record_reading


# ----------------------------------------------------------------------
# How a collar may connect
# ----------------------------------------------------------------------
HOW_BLUETOOTH = "bluetooth"
HOW_WIFI = "wifi"
VALID_HOWS = (HOW_BLUETOOTH, HOW_WIFI)


# ----------------------------------------------------------------------
# One message on the wire — what the collar sends to the app
# ----------------------------------------------------------------------
@dataclass
class CollarMessage:
    """The small packet the collar sends for one reading.

    Tagged by pet_id so two collars never mix up, and carries battery so the
    app can warn before the collar dies. Everything is plain JSON-safe types,
    so the same packet works over Bluetooth, WiFi, or a file.
    """
    pet_name: str
    when: str                       # ISO time, UTC
    readings: dict                  # {"hr":.., "resp":.., "temp":.., "movement":..}
    gps: dict | None = None         # {"lat":.., "lon":..} if the collar has GPS
    sound: float | None = None      # 0-100 loudness proxy, if measured
    battery_pct: float | None = None

    def to_json(self) -> str:
        """Serialize for sending over a real link."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "CollarMessage":
        """Rebuild a message the app received over a real link."""
        return cls(**json.loads(text))

    @classmethod
    def from_report(cls, pet_name: str, report: CollarReport,
                    battery_pct: float | None = None) -> "CollarMessage":
        """Pack a collar's reading bundle into one message to send."""
        r: SensorReading = report.reading
        gps = None
        if r.fix is not None:
            gps = {"lat": r.fix.lat, "lon": r.fix.lon}
        return cls(
            pet_name=pet_name,
            when=datetime.fromtimestamp(r.at, timezone.utc).isoformat(),
            readings=r.vitals(),            # the four per-breed signals
            gps=gps,
            sound=r.sound,
            battery_pct=battery_pct,
        )


# ----------------------------------------------------------------------
# A transport = one way to move a message (Bluetooth or WiFi)
# ----------------------------------------------------------------------
class Transport:
    """Base for a connection type. A real one talks to a real radio.

    Subclasses override pair() and send(). The demo versions just hand the
    message to the app in memory, so you can run everything with no hardware.
    """

    name = "transport"

    def __init__(self) -> None:
        self.paired = False

    def pair(self) -> bool:
        """One-time handshake before sending. Returns True when linked."""
        self.paired = True
        return True

    def send(self, message: CollarMessage) -> None:
        """Push one message to the app side. Overridden by real drivers."""
        raise NotImplementedError

    def close(self) -> None:
        """Hang up the link."""
        self.paired = False


class BluetoothTransport(Transport):
    """Short-range link, used when the phone is near the pet (at home, on a walk).

    REAL DRIVER: replace pair() with a BLE scan + connect (e.g. the ``bleak``
    library), and send() with a GATT characteristic write of
    ``message.to_json()``. Nothing above this class changes.
    """

    name = HOW_BLUETOOTH

    def __init__(self, deliver, device: str = "PawWatch-Collar") -> None:
        super().__init__()
        self._deliver = deliver          # app-side callback (fake wire)
        self.device = device

    def pair(self) -> bool:
        # REAL: scan for self.device, bond, open the GATT connection.
        time.sleep(0)                    # placeholder for the handshake
        self.paired = True
        return True

    def send(self, message: CollarMessage) -> None:
        if not self.paired:
            raise ConnectionError("Bluetooth not paired. Call pair() first.")
        # REAL: write message.to_json() to the collar's GATT characteristic.
        self._deliver(message)           # FAKE wire: straight to the app


class WifiTransport(Transport):
    """Long-range link, used when the pet is away from the phone (collar on Wi-Fi).

    REAL DRIVER: replace pair() with a join to the saved network + a reachable
    check, and send() with an HTTP POST of ``message.to_json()`` to the app's
    ingest URL (or an MQTT publish). Nothing above this class changes.
    """

    name = HOW_WIFI

    def __init__(self, deliver, endpoint: str = "https://app.local/ingest") -> None:
        super().__init__()
        self._deliver = deliver
        self.endpoint = endpoint

    def pair(self) -> bool:
        # REAL: join the saved Wi-Fi, confirm self.endpoint answers.
        time.sleep(0)
        self.paired = True
        return True

    def send(self, message: CollarMessage) -> None:
        if not self.paired:
            raise ConnectionError("Wi-Fi not connected. Call pair() first.")
        # REAL: requests.post(self.endpoint, data=message.to_json()).
        self._deliver(message)           # FAKE wire: straight to the app


# ----------------------------------------------------------------------
# The Link — the collar's end of the connection
# ----------------------------------------------------------------------
@dataclass
class SendResult:
    """What the app said back after one message was received."""
    ok: bool
    how: str                             # "bluetooth" / "wifi"
    pet_name: str
    alarm: bool = False
    reasons: list = field(default_factory=list)
    notified: bool = False
    error: str = ""


class Link:
    """One collar connected to the app over one transport.

    Create it with connect(), then:
        link.pair()                 # handshake once
        link.send(collar.tick())    # push a reading; app ingests it
        link.switch("wifi")         # change transport (pet left the house)
    """

    def __init__(self, pet_name: str, transport: Transport) -> None:
        self.pet_name = pet_name
        self.transport = transport

    # ---- the app side: what happens when a message arrives -----------
    @staticmethod
    def _ingest(message: CollarMessage) -> dict:
        """App side of the wire: feed a received message into pawwatch.

        This is the ONLY place the connection touches the app, and it reuses
        the existing record_reading — so history + notify-on-abnormal behave
        exactly as before.
        """
        return record_reading(
            pet_name=message.pet_name,
            readings=message.readings,
            gps=message.gps,
            when=datetime.fromisoformat(message.when),
            battery_pct=message.battery_pct,
        )

    # ---- the collar side: connect, then send -------------------------
    def pair(self) -> bool:
        """Open the link once before sending."""
        return self.transport.pair()

    def send(self, report: CollarReport,
             battery_pct: float | None = None) -> SendResult:
        """Pack one collar reading, send it over the link, return the verdict."""
        message = CollarMessage.from_report(self.pet_name, report,
                                            battery_pct=battery_pct)
        try:
            # On a real link this travels over Bluetooth/WiFi and the app's
            # own _ingest runs on the other end. In the demo the transport's
            # fake wire calls our _ingest directly.
            self.transport.send(message)
            out = self._ingest(message)
            return SendResult(
                ok=True, how=self.transport.name, pet_name=self.pet_name,
                alarm=out["alarm"], reasons=out["reasons"],
                notified=out["notified"],
            )
        except Exception as exc:                       # link dropped, etc.
            return SendResult(
                ok=False, how=self.transport.name,
                pet_name=self.pet_name, error=str(exc),
            )

    def switch(self, how: str) -> None:
        """Change the connection type, e.g. Bluetooth at home -> WiFi away."""
        self.transport.close()
        self.transport = _make_transport(how, self._ingest)
        self.transport.pair()

    def close(self) -> None:
        self.transport.close()


def _make_transport(how: str, deliver) -> Transport:
    how = (how or "").lower()
    if how == HOW_BLUETOOTH:
        return BluetoothTransport(deliver)
    if how == HOW_WIFI:
        return WifiTransport(deliver)
    raise ValueError(f"Unknown connection {how!r}. Use 'bluetooth' or 'wifi'.")


def connect(pet_name: str, how: str = HOW_BLUETOOTH) -> Link:
    """Make a link between one pet's collar and the app.

    how = "bluetooth" (near the phone) or "wifi" (away from the phone).
    """
    # The app-side ingest is bound to the transport as its "wire" so the demo
    # can run with no hardware. A real driver sends bytes instead.
    link = Link(pet_name, transport=None)              # placeholder
    link.transport = _make_transport(how, link._ingest)
    return link


# ----------------------------------------------------------------------
# Self-test: run `python -m pawwatch.connection`
# ----------------------------------------------------------------------
def _demo() -> None:
    from . import find
    from .collar import Collar
    from .gps import Fix, SafeZone
    from .intake import intake

    # make sure one pet exists (same pet the other demos use)
    intake({
        "pet_name": "Rex", "species": "Dog", "breed": "Chihuahua",
        "age_years": 3, "weight_kg": 2.5,
    }, save=True)

    profile = find("Dog", "Chihuahua", "1-10")
    home = Fix(37.7749, -122.4194)
    collar = Collar(profile, safe_zone=SafeZone(home, radius_m=50), seed=1)

    print("=== Bluetooth: collar near the phone ===")
    link = connect("Rex", how="bluetooth")
    print("paired:", link.pair(), "| via:", link.transport.name)
    res = link.send(collar.tick(), battery_pct=88)
    print(f"sent over {res.how}: ok={res.ok} alarm={res.alarm} "
          f"notified={res.notified} battery=88%")

    print("\n=== Switch to Wi-Fi: pet left the house ===")
    link.switch("wifi")
    print("now via:", link.transport.name)
    res = link.send(collar.tick(), battery_pct=80)
    print(f"sent over {res.how}: ok={res.ok} alarm={res.alarm}")

    print("\n=== One message on the wire (JSON that crosses the link) ===")
    msg = CollarMessage.from_report("Rex", collar.tick(), battery_pct=80)
    wire = msg.to_json()
    print("   ", wire[:90], "...")
    back = CollarMessage.from_json(wire)       # app rebuilds it on the far end
    print("    rebuilt ok:", back.pet_name == "Rex" and back.readings == msg.readings)

    print("\n=== Trying to send before pairing (should fail cleanly) ===")
    bad = connect("Rex", how="wifi")
    res = bad.send(collar.tick())
    print(f"ok={res.ok} error={res.error!r}")


if __name__ == "__main__":
    _demo()
