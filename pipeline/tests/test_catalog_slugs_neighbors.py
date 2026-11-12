"""Slug and neighbour tests. Synthetic districts only (names contain 'Test')."""

# ruff: noqa: S311  (random only builds synthetic test data)

from __future__ import annotations

import random

from pay_pipeline.catalog.neighbors import Point, compute_neighbors, haversine_km
from pay_pipeline.catalog.slugs import SlugInput, assign_slugs, slugify


class TestSlugify:
    def test_basic(self) -> None:
        assert (
            slugify("Test Valley Unified School District") == "test-valley-unified-school-district"
        )

    def test_accents_and_symbols(self) -> None:
        assert slugify("Cañon Test R-1 / Ward & Co.") == "canon-test-r-1-ward-and-co"

    def test_length_limit(self) -> None:
        assert len(slugify("Test " * 40)) <= 80


class TestAssignSlugs:
    def test_unique_names_get_plain_slug(self) -> None:
        r = assign_slugs([SlugInput("0000001", "ZZ", "Test A District", "Alpha County")], {})
        assert r.slugs == {"0000001": "test-a-district"}
        assert r.disambiguated == []

    def test_duplicate_names_in_state_get_county(self) -> None:
        rows = [
            SlugInput("0000002", "ZZ", "Test Union School District", "Beta County"),
            SlugInput("0000001", "ZZ", "Test Union School District", "Alpha County"),
            SlugInput("0000003", "YY", "Test Union School District", "Gamma County"),
        ]
        r = assign_slugs(rows, {})
        assert r.slugs["0000001"] == "test-union-school-district-alpha-county"
        assert r.slugs["0000002"] == "test-union-school-district-beta-county"
        # Different state: no clash.
        assert r.slugs["0000003"] == "test-union-school-district"

    def test_same_name_same_county_falls_back_to_nces_id(self) -> None:
        rows = [
            SlugInput("0000001", "ZZ", "Test Twin District", "Alpha County"),
            SlugInput("0000002", "ZZ", "Test Twin District", "Alpha County"),
        ]
        r = assign_slugs(rows, {})
        assert r.slugs["0000001"] == "test-twin-district-alpha-county"
        assert r.slugs["0000002"] == "test-twin-district-0000002"

    def test_existing_slug_is_kept_even_if_name_changed(self) -> None:
        r = assign_slugs(
            [SlugInput("0000001", "ZZ", "Test Renamed District", None)],
            {"0000001": ("ZZ", "test-old-name")},
        )
        assert r.slugs["0000001"] == "test-old-name"

    def test_new_district_cannot_take_existing_slug(self) -> None:
        r = assign_slugs(
            [
                SlugInput("0000001", "ZZ", "Test Old", None),
                SlugInput("0000009", "ZZ", "Test Old", "Delta County"),
            ],
            {"0000001": ("ZZ", "test-old")},
        )
        assert r.slugs["0000001"] == "test-old"
        assert r.slugs["0000009"] == "test-old-delta-county"

    def test_deterministic_and_unique(self) -> None:
        rnd = random.Random(7)
        rows = [
            SlugInput(
                f"{i:07d}", "ZZ", f"Test {rnd.choice('ABC')} District", rnd.choice(["X", "Y"])
            )
            for i in range(60)
        ]
        a = assign_slugs(rows, {})
        b = assign_slugs(list(reversed(rows)), {})
        assert a.slugs == b.slugs
        assert len(set(a.slugs.values())) == len(rows)


class TestNeighbors:
    def test_haversine_known_distance(self) -> None:
        # One degree of latitude is about 111 km.
        assert 110.5 < haversine_km(40.0, -100.0, 41.0, -100.0) < 111.5

    def test_nearest_and_same_county(self) -> None:
        pts = [
            Point("A", "01001", 40.00, -100.00),
            Point("B", "01001", 40.10, -100.00),  # ~11 km
            Point("C", "01003", 40.00, -100.20),  # ~17 km, other county
            Point("D", "01001", 45.00, -100.00),  # far, same county
            Point("E", "01001", None, None),  # no coordinates, same county
        ]
        result = compute_neighbors(pts, nearest=2, same_county_max=10)
        of_a = [(n.neighbor, n.distance_km) for n in result if n.district == "A"]
        names = [x for x, _ in of_a]
        assert names[:2] == ["B", "C"]  # nearest two first
        assert "D" in names and "E" in names  # same county
        assert dict(of_a)["E"] is None
        assert all(n.district != n.neighbor for n in result)

    def test_grid_search_matches_brute_force(self) -> None:
        rnd = random.Random(42)
        pts = [
            Point(f"{i:04d}", None, rnd.uniform(25, 49), rnd.uniform(-124, -67)) for i in range(300)
        ]
        result = compute_neighbors(pts, nearest=5, same_county_max=0)
        got: dict[str, list[str]] = {}
        for n in result:
            got.setdefault(n.district, []).append(n.neighbor)
        for p in pts[:40]:
            assert p.lat is not None and p.lng is not None
            brute = sorted(
                (
                    (haversine_km(p.lat, p.lng, q.lat, q.lng), q.nces_id)
                    for q in pts
                    if q.nces_id != p.nces_id and q.lat is not None and q.lng is not None
                ),
            )[:5]
            assert got[p.nces_id] == [qid for _, qid in brute]
