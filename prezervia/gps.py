"""
prezervia.gps — where the collar is, and is it safe.

Dependency-free, like the rest of prezervia. It can:
  * hold a GPS point (latitude, longitude, time),
  * measure how far apart two points are, in metres,
  * set a "safe zone" circle (home) and tell if the pet is inside it,
  * watch a stream of points and raise a fence alarm when the pet leaves,
  * guess how fast the pet is moving between points,
  * report how far the pet moved (walked vs straight line),
  * follow a saved route to a destination and tell how far is left.

A real collar would send these points over the air. Here we just feed
the points in, same as the vitals are faked in the app.

IMPORT:
    from prezervia.gps import Fix, SafeZone, GpsTracker
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# Earth radius in metres, for the distance maths.
_EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class Fix:
    """One GPS reading: where the collar was, and when."""
    lat: float          # latitude, degrees
    lon: float          # longitude, degrees
    at: float = field(default_factory=time.time)   # unix seconds

    def distance_to(self, other: "Fix") -> float:
        """Metres between this point and another (great-circle / haversine)."""
        return haversine_m(self.lat, self.lon, other.lat, other.lon)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two lat/lon points on the Earth."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class SafeZone:
    """A circle the pet should stay inside: a centre point and a radius."""
    center: Fix
    radius_m: float

    def contains(self, fix: Fix) -> bool:
        """True if this point is inside the circle."""
        return self.center.distance_to(fix) <= self.radius_m

    def distance_outside(self, fix: Fix) -> float:
        """Metres past the edge. 0 if still inside."""
        gap = self.center.distance_to(fix) - self.radius_m
        return max(0.0, gap)


@dataclass
class GpsResult:
    """What the tracker thinks after the latest point."""
    fix: Fix
    inside_safe_zone: bool
    metres_from_home: float
    metres_outside: float
    speed_mps: float            # metres per second since the last point
    fence_alarm: bool           # pet left the safe zone
    metres_to_destination: float | None = None   # None if no destination set
    arrived: bool = False       # pet reached the destination


@dataclass
class DistanceReport:
    """How far the pet moved, measured a few ways."""
    points: int                 # how many GPS points we have
    path_length_m: float        # total walked, point to point
    straight_line_m: float      # first point to last point, as the crow flies
    net_from_start_m: float     # same as straight_line, named for the app


@dataclass
class RouteProgress:
    """How a saved route to a destination is going."""
    destination: Fix
    reached: list[Fix]          # waypoints already passed
    remaining: list[Fix]        # waypoints still ahead
    metres_to_destination: float
    route_length_m: float       # length of the whole saved route
    arrived: bool


class GpsTracker:
    """Feed it GPS points one at a time; it tracks the pet and the fence.

    Example:
        home = Fix(37.7749, -122.4194)
        t = GpsTracker(SafeZone(home, radius_m=100))
        out = t.update(Fix(37.7751, -122.4190))
        print(out.fence_alarm, round(out.metres_from_home))

    Give it a destination route too:
        t.set_route([Fix(37.7760, -122.4180), Fix(37.7790, -122.4150)])
    """

    def __init__(self, safe_zone: SafeZone, arrive_radius_m: float = 20.0):
        self.safe_zone = safe_zone
        self.arrive_radius_m = arrive_radius_m   # "close enough" to a point
        self.last_fix: Fix | None = None
        self.track: list[Fix] = []
        self.route: list[Fix] = []               # planned waypoints to walk
        self._route_done: list[bool] = []        # which waypoints are passed

    # ---- destination route -------------------------------------------
    def set_route(self, waypoints: list[Fix]) -> None:
        """Save the planned path. Last waypoint is the destination."""
        self.route = list(waypoints)
        self._route_done = [False] * len(self.route)

    @property
    def destination(self) -> Fix | None:
        """The last waypoint, or None if no route is set."""
        return self.route[-1] if self.route else None

    def route_length_m(self) -> float:
        """Length of the whole planned route, start to destination."""
        return sum(a.distance_to(b)
                   for a, b in zip(self.route, self.route[1:]))

    def route_progress(self) -> RouteProgress | None:
        """How the saved route is going, based on the latest point."""
        if not self.route or self.last_fix is None:
            return None
        dest = self.route[-1]
        reached = [w for w, done in zip(self.route, self._route_done) if done]
        remaining = [w for w, done in zip(self.route, self._route_done) if not done]
        return RouteProgress(
            destination=dest,
            reached=reached,
            remaining=remaining,
            metres_to_destination=self.last_fix.distance_to(dest),
            route_length_m=self.route_length_m(),
            arrived=all(self._route_done),
        )

    # ---- live update -------------------------------------------------
    def update(self, fix: Fix) -> GpsResult:
        """Take one new point and report where the pet is."""
        speed = 0.0
        if self.last_fix is not None:
            dt = fix.at - self.last_fix.at
            if dt > 0:
                speed = self.last_fix.distance_to(fix) / dt

        # Tick off any waypoint the pet is now close enough to.
        for i, w in enumerate(self.route):
            if not self._route_done[i] and fix.distance_to(w) <= self.arrive_radius_m:
                self._route_done[i] = True

        dest = self.route[-1] if self.route else None
        to_dest = fix.distance_to(dest) if dest else None
        arrived = bool(self.route) and all(self._route_done)

        inside = self.safe_zone.contains(fix)
        result = GpsResult(
            fix=fix,
            inside_safe_zone=inside,
            metres_from_home=self.safe_zone.center.distance_to(fix),
            metres_outside=self.safe_zone.distance_outside(fix),
            speed_mps=speed,
            fence_alarm=not inside,
            metres_to_destination=to_dest,
            arrived=arrived,
        )
        self.last_fix = fix
        self.track.append(fix)
        return result

    # ---- how far did it move ----------------------------------------
    def total_distance_m(self) -> float:
        """How far the pet has walked in total, along every point so far."""
        return sum(a.distance_to(b)
                   for a, b in zip(self.track, self.track[1:]))

    def distance_report(self) -> DistanceReport:
        """Walked distance, straight-line distance, and point count."""
        straight = (self.track[0].distance_to(self.track[-1])
                    if len(self.track) >= 2 else 0.0)
        return DistanceReport(
            points=len(self.track),
            path_length_m=self.total_distance_m(),
            straight_line_m=straight,
            net_from_start_m=straight,
        )
