"""District catalogue import, end to end on SYNTHETIC CCD-shaped files.

The files mimic the 2024-25 layout (column names checked on the real files); names contain
"Test" and websites use example.invalid. The generated SQL runs against the real D1 schema
(packages/db/migrations) in SQLite.
"""

# ruff: noqa: E501  (bảng dữ liệu giả lập để dễ đọc theo hàng)

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from pay_pipeline.catalog.ccd import DIRECTORY_COLUMNS, MEMBERSHIP_TOTAL, NYC_LEAID
from pay_pipeline.catalog.d1sql import MAX_STATEMENT_BYTES, catalog_sql, quote, render_sql
from pay_pipeline.catalog.districts import (
    build_catalog,
    normalize_website,
    reconcile,
    render_report,
)
from pay_pipeline.cli import load_existing_slugs

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO / "packages" / "db" / "migrations").glob("*.sql"))
NOW = dt.datetime(2026, 11, 12, 8, 0, tzinfo=dt.UTC)

# (LEAID, ST, name, LEA_TYPE, SY_STATUS, UNION, website, enrollment, county code, county name, lat, lng)
LEAS = [
    ("0600001", "CA", "Test Alpha Unified", "1", "1", "", "www.alpha.example.invalid", 5000, "06001", "Test County", 37.0, -122.0),
    ("0600002", "CA", "Test Beta Elementary", "1", "1", "", "", 800, "06001", "Test County", 37.1, -122.1),
    ("0600003", "CA", "Test Gamma Charter", "7", "1", "", "", 300, "06001", "Test County", 37.2, -122.2),
    ("0600004", "CA", "Test Closed District", "1", "2", "", "", None, "06003", "Other Test County", 38.0, -121.0),
    ("0600005", "CA", "Test Beta Elementary", "1", "3", "", "", 120, "06003", "Other Test County", 38.1, -121.1),
    ("0600006", "CA", "Test Union Office", "3", "1", "", "", None, "06003", "Other Test County", 38.2, -121.2),
    ("5000001", "VT", "Test Member School District", "2", "1", "001", "", 90, "50001", "Test VT County", 44.0, -72.0),
    ("3600001", "NY", "TEST NYC GEOGRAPHIC DISTRICT # 1", "2", "1", "300", "", 1000, "36061", "New York County", 40.7, -74.0),
    ("3600002", "NY", "TEST NYC GEOGRAPHIC DISTRICT # 2", "2", "1", "300", "", 2000, "36061", "New York County", 40.8, -74.0),
    (NYC_LEAID, "NY", "TEST NYC CHANCELLOR'S OFFICE", "3", "1", "300", "http://nyc.example.invalid", None, "36061", "New York County", 40.71, -74.01),
    ("7200001", "PR", "Test Territory Agency", "1", "1", "", "", 10, "72001", "Test Municipio", 18.0, -66.0),
]  # fmt: skip

SUMMARY = {"California": 5, "Vermont": 1, "New York": 1}  # NYC counted as one LEA


def _zip(path: Path, member: str, text: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(member, text.encode("utf-8-sig"))


def write_sources(directory: Path, leas: list[tuple[object, ...]] = LEAS) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[*DIRECTORY_COLUMNS, "LEA_TYPE_TEXT"])
    w.writeheader()
    for leaid, st, name, typ, status, union, web, *_ in leas:
        w.writerow(
            {
                "SCHOOL_YEAR": "2024-2025",
                "ST": st,
                "LEA_NAME": name,
                "LEAID": leaid,
                "UNION": union,
                "LCITY": "Testville",
                "WEBSITE": web,
                "SY_STATUS": status,
                "LEA_TYPE": typ,
                "LEA_TYPE_TEXT": "",
            }
        )
    _zip(
        directory / "ccd_lea_029_2425_w_1a_000000.zip",
        "ccd_lea_029_2425_w_1a_000000.csv",
        buf.getvalue(),
    )

    buf = io.StringIO()
    w2 = csv.writer(buf)
    w2.writerow(["LEAID", "GRADE", "STUDENT_COUNT", "TOTAL_INDICATOR"])
    for leaid, *_, enrollment, _c, _n, _la, _lo in leas:
        w2.writerow([leaid, "", "" if enrollment is None else enrollment, MEMBERSHIP_TOTAL])
        w2.writerow([leaid, "01", 1, "Subtotal 4 - By Grade"])
    _zip(
        directory / "ccd_lea_052_2425_l_1a_000000.zip",
        "ccd_lea_052_2425_l_1a_000000.csv",
        buf.getvalue(),
    )

    lines = []
    for leaid, st, name, *_, code, county, lat, lng in leas:
        lines.append(
            "|".join(
                [
                    str(leaid),
                    str(name),
                    "",
                    "",
                    "Testville",
                    str(st),
                    "",
                    "",
                    str(code),
                    str(county),
                    str(lat),
                    str(lng),
                ]
            )
        )
    _zip(
        directory / "EDGE_GEOCODE_PUBLICLEA_2425.zip",
        "EDGE_GEOCODE_PUBLICLEA_2425.TXT",
        "\n".join(lines) + "\n",
    )

    rows = "".join(
        f"<tr><th>{name}</th><td>1</td><td>{n}</td><td></td><td>1,000</td></tr>"
        for name, n in SUMMARY.items()
    )
    (directory / "ccd_202425_summary_2.html").write_text(
        f'<p class="title">Table 2. Test: School year 2024&ndash;25</p><table><tbody>{rows}</tbody></table>',
        encoding="utf-8",
    )
    return directory


def schema_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    for m in MIGRATIONS:
        db.executescript(m.read_text(encoding="utf-8"))
    return db


@pytest.fixture
def catalog(tmp_path: Path):  # type: ignore[no-untyped-def]
    return build_catalog(write_sources(tmp_path / "src"), {})


class TestBuild:
    def test_keeps_only_operating_regular_districts_in_scope(self, catalog) -> None:  # type: ignore[no-untyped-def]
        kept = {d.nces_id for d in catalog.districts}
        assert kept == {"0600001", "0600002", "0600005", "5000001", NYC_LEAID}
        ca = catalog.by_state["CA"]
        assert ca.operating == 5  # closed one excluded from "operating"
        assert ca.excluded == {"type_7": 1, "type_3": 1}
        assert catalog.out_of_scope == {"PR": 1}

    def test_nyc_components_fold_into_chancellors_office(self, catalog) -> None:  # type: ignore[no-untyped-def]
        nyc = next(d for d in catalog.districts if d.nces_id == NYC_LEAID)
        assert nyc.enrollment == 3000  # sum of the components
        assert catalog.by_state["NY"].excluded == {"nyc_component": 2}

    def test_reconcile_matches_summary_and_explains_nyc(self, catalog) -> None:  # type: ignore[no-untyped-def]
        rec = {code: (op, exp, note) for code, op, exp, note in reconcile(catalog)}
        assert rec["CA"] == (5, 5, "")
        assert rec["VT"] == (1, 1, "")
        op, exp, note = rec["NY"]
        assert (op, exp) == (3, 1) and "NYC" in note
        assert rec["TX"][1] is None  # no row in the synthetic table

    def test_slugs_unique_and_disambiguated_by_county(self, catalog) -> None:  # type: ignore[no-untyped-def]
        slugs = {d.nces_id: d.slug for d in catalog.districts}
        assert slugs["0600002"] == "test-beta-elementary-test-county"
        assert slugs["0600005"] == "test-beta-elementary-other-test-county"
        assert len({(d.state, d.slug) for d in catalog.districts}) == len(catalog.districts)

    def test_fields_mapped(self, catalog) -> None:  # type: ignore[no-untyped-def]
        a = next(d for d in catalog.districts if d.nces_id == "0600001")
        assert (a.county, a.lat, a.lng, a.enrollment) == ("Test County", 37.0, -122.0, 5000)
        assert a.website == "http://www.alpha.example.invalid"

    def test_report_mentions_sample_and_reconciliation(self, catalog) -> None:  # type: ignore[no-untyped-def]
        text = render_report(catalog)
        assert "Đối chiếu" in text and "ngẫu nhiên" in text and "| CA |" in text

    def test_rejects_file_without_required_column(self, tmp_path: Path) -> None:
        src = write_sources(tmp_path / "src")
        _zip(next(src.glob("ccd_lea_029_*.zip")), "x.csv", "LEAID,LEA_NAME\n1,Test\n")
        with pytest.raises(ValueError, match="thiếu cột"):
            build_catalog(src, {})


@pytest.mark.parametrize(
    ("raw", "url"),
    [
        ("www.x.example.invalid", "http://www.x.example.invalid"),
        ("https://x.example.invalid/a", "https://x.example.invalid/a"),
        ("", None),
        ("n/a", None),
        ("two words.example", None),
    ],
)
def test_normalize_website(raw: str, url: str | None) -> None:
    assert normalize_website(raw) == url


class TestSql:
    def test_quote(self) -> None:
        assert quote("O'Brien") == "'O''Brien'"
        assert quote(None) == "NULL" and quote(3) == "3" and quote(1.5) == "1.5"

    def test_statements_under_limit(self, catalog) -> None:  # type: ignore[no-untyped-def]
        assert all(len(s.encode()) <= MAX_STATEMENT_BYTES for s in catalog_sql(catalog, NOW))

    def test_loads_into_real_schema_and_is_idempotent(self, tmp_path: Path, catalog) -> None:  # type: ignore[no-untyped-def]
        db = schema_db()
        db.executescript(render_sql(catalog_sql(catalog, NOW)))
        count = db.execute("SELECT COUNT(*), SUM(active) FROM districts").fetchone()
        assert count == (5, 5)
        assert db.execute("SELECT COUNT(*) FROM states").fetchone() == (51,)
        assert db.execute("SELECT COUNT(*) FROM district_neighbors").fetchone()[0] > 0
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '\\_import%' ESCAPE '\\'"
        ).fetchall()

        # Second run with the slugs now stored: nothing rewritten.
        existing = {
            r[0]: (r[1], r[2]) for r in db.execute("SELECT nces_id, state, slug FROM districts")
        }
        again = build_catalog(tmp_path / "src", existing)
        later = NOW + dt.timedelta(days=1)
        db.executescript(render_sql(catalog_sql(again, later)))
        assert db.execute("SELECT MAX(updated_at) FROM districts").fetchone() == (
            "2026-11-12T08:00:00Z",
        )

    def test_missing_district_becomes_inactive_not_deleted(self, tmp_path: Path, catalog) -> None:  # type: ignore[no-untyped-def]
        db = schema_db()
        db.executescript(render_sql(catalog_sql(catalog, NOW)))
        slug_before = db.execute("SELECT slug FROM districts WHERE nces_id = '0600002'").fetchone()
        smaller = build_catalog(
            write_sources(tmp_path / "src2", [x for x in LEAS if x[0] != "0600001"]),
            {r[0]: (r[1], r[2]) for r in db.execute("SELECT nces_id, state, slug FROM districts")},
        )
        db.executescript(render_sql(catalog_sql(smaller, NOW + dt.timedelta(days=1))))
        assert db.execute("SELECT active FROM districts WHERE nces_id = '0600001'").fetchone() == (
            0,
        )
        assert db.execute("SELECT COUNT(*) FROM districts").fetchone() == (5,)
        # Without 0600001 the name is no longer ambiguous, but the stored slug is kept.
        assert (
            db.execute("SELECT slug FROM districts WHERE nces_id = '0600002'").fetchone()
            == slug_before
        )
        inactive_neighbors = db.execute(
            "SELECT COUNT(*) FROM district_neighbors n JOIN districts d ON d.id = n.district_id"
            " WHERE d.nces_id = '0600001'"
        ).fetchone()
        assert inactive_neighbors == (0,)

    def test_search_index_follows_import(self, catalog) -> None:  # type: ignore[no-untyped-def]
        db = schema_db()
        db.executescript(render_sql(catalog_sql(catalog, NOW)))
        hits = db.execute(
            "SELECT d.nces_id FROM districts_fts f JOIN districts d ON d.id = f.rowid"
            " WHERE districts_fts MATCH 'gamma OR alpha'"
        ).fetchall()
        assert hits == [("0600001",)]  # the charter (Gamma) was not imported


def test_load_existing_slugs_reads_wrangler_json(tmp_path: Path) -> None:
    path = tmp_path / "existing.json"
    path.write_text(
        json.dumps(
            [{"results": [{"nces_id": "0600001", "state": "CA", "slug": "x"}], "success": True}]
        )
    )
    assert load_existing_slugs(path) == {"0600001": ("CA", "x")}
    assert load_existing_slugs(None) == {}
    with pytest.raises(FileNotFoundError):
        load_existing_slugs(tmp_path / "missing.json")


class TestSchoolWebsites:
    """D-035: website of a district derived from its schools when the LEA file has none."""

    def _schools(self, path: Path, rows: list[tuple[str, str]]) -> Path:
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["LEAID", "SCH_NAME", "WEBSITE"])
        for i, (leaid, site) in enumerate(rows):
            w.writerow([leaid, f"School {i}", site])
        _zip(path, "ccd_sch_029_2425_w_1a_073025.csv", out.getvalue())
        return path

    def test_rules(self) -> None:
        from collections import Counter

        from pay_pipeline.catalog.ccd import SchoolSites
        from pay_pipeline.catalog.districts import school_website

        assert school_website(SchoolSites(5, Counter({"beta.k12.ca.us": 4, "x.org": 1}))) == (
            "http://beta.k12.ca.us"
        )
        assert school_website(SchoolSites(1, Counter({"one.org": 1}))) == "http://one.org"
        # One school of many is not the district's site; a split vote is not either.
        assert school_website(SchoolSites(9, Counter({"school.org": 1}))) is None
        assert school_website(SchoolSites(4, Counter({"a.org": 2, "b.org": 2}))) is None
        assert school_website(SchoolSites(3, Counter({"facebook.com": 3}))) is None
        assert school_website(SchoolSites(3, Counter({"district.k12.ga.gov": 3}))) is None
        assert school_website(None) is None

    def test_build_fills_only_missing_websites(self, tmp_path: Path) -> None:
        schools = self._schools(
            tmp_path / "sch.zip",
            [
                ("0600001", "www.other.example.invalid"),
                ("0600001", "www.other.example.invalid"),
                ("0600002", "http://www.beta.example.invalid/elementary"),
                ("0600002", "beta.example.invalid."),
                ("0600002", ""),
                ("0600005", "solo.example.invalid"),
            ],
        )
        cat = build_catalog(write_sources(tmp_path / "src"), {}, schools=schools)
        site = {d.nces_id: d.website for d in cat.districts}
        assert site["0600001"] == "http://www.alpha.example.invalid"  # LEA file wins
        assert site["0600002"] == "http://beta.example.invalid"
        assert site["0600005"] == "http://solo.example.invalid"
        assert site["5000001"] is None
        assert cat.websites_from_schools == 2
        assert "đã suy 2 website" in render_report(cat)
