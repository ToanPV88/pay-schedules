"""Neighbouring districts (PLAN Công đoạn 3, bước 5): same county, plus the nearest by distance.

Distances are great-circle kilometres between district office coordinates (EDGE). A district
without coordinates gets only same-county neighbours, with an unknown distance.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088
NEAREST = 10
SAME_COUNTY_MAX = 10


@dataclass(frozen=True)
class Point:
    nces_id: str
    county_key: str | None
    """State + county code (e.g. '06037'); None when unknown."""
    lat: float | None
    lng: float | None


@dataclass(frozen=True)
class Neighbor:
    district: str
    neighbor: str
    distance_km: float | None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def _cell(lat: float, lng: float) -> tuple[int, int]:
    return (math.floor(lat), math.floor(lng))


def compute_neighbors(
    points: Iterable[Point], nearest: int = NEAREST, same_county_max: int = SAME_COUNTY_MAX
) -> list[Neighbor]:
    pts = sorted(points, key=lambda p: p.nces_id)
    grid: dict[tuple[int, int], list[tuple[Point, float, float]]] = defaultdict(list)
    for p in pts:
        if p.lat is not None and p.lng is not None:
            grid[_cell(p.lat, p.lng)].append((p, p.lat, p.lng))
    by_county: dict[str, list[Point]] = defaultdict(list)
    for p in pts:
        if p.county_key:
            by_county[p.county_key].append(p)

    def dist(a: Point, b: Point) -> float | None:
        if a.lat is None or a.lng is None or b.lat is None or b.lng is None:
            return None
        return haversine_km(a.lat, a.lng, b.lat, b.lng)

    def nearest_of(p: Point, lat: float, lng: float) -> list[tuple[float, Point]]:
        ci, cj = _cell(lat, lng)
        found: list[tuple[float, Point]] = []
        ring = 0
        # Grow the search square until it holds enough points and one more ring cannot hold a
        # closer one (a ring is at least ~ring*111 km * cos(lat) away; we use a safe bound).
        while ring < 60:
            for i in range(ci - ring, ci + ring + 1):
                for j in range(cj - ring, cj + ring + 1):
                    if max(abs(i - ci), abs(j - cj)) != ring:
                        continue
                    for q, qlat, qlng in grid.get((i, j), ()):
                        if q.nces_id != p.nces_id:
                            found.append((haversine_km(lat, lng, qlat, qlng), q))
            if len(found) >= nearest:
                found.sort(key=lambda x: (x[0], x[1].nces_id))
                kth = found[nearest - 1][0]
                min_lng_km = 111.0 * max(math.cos(math.radians(abs(lat) + ring + 1)), 0.05)
                if kth <= ring * min(111.0, min_lng_km):
                    break
            ring += 1
        found.sort(key=lambda x: (x[0], x[1].nces_id))
        return found[:nearest]

    out: list[Neighbor] = []
    for p in pts:
        chosen: dict[str, float | None] = {}
        if p.lat is not None and p.lng is not None:
            for km, q in nearest_of(p, p.lat, p.lng):
                chosen[q.nces_id] = km
        if p.county_key:
            same = [q for q in by_county[p.county_key] if q.nces_id != p.nces_id]
            ranked = sorted(
                same,
                key=lambda q: (dist(p, q) is None, dist(p, q) or 0.0, q.nces_id),
            )
            for q in ranked[:same_county_max]:
                chosen.setdefault(q.nces_id, dist(p, q))
        for qid in sorted(chosen, key=lambda k: (chosen[k] is None, chosen[k] or 0.0, k)):
            km_or_none = chosen[qid]
            rounded = None if km_or_none is None else round(km_or_none, 2)
            out.append(Neighbor(p.nces_id, qid, rounded))
    return out
