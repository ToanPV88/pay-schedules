"""State schedule import, end to end on SYNTHETIC files shaped like the real ones.

* California J-90: a ZIP named like the CDE self-extracting file holds a placeholder .accdb; the
  Access tables are served by a fake ``mdb-export`` with the column names of the 2024-25 readme.
* Kentucky: a workbook with the KDE sheet layout, built with openpyxl.
* NCES CCD directory with ST_LEAID / UNION columns.

Names contain "Test"; the generated SQL runs against the real D1 schema in SQLite.
"""

# ruff: noqa: E501  (bảng dữ liệu giả lập để dễ đọc theo hàng)

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from collections.abc import Sequence
from pathlib import Path

import openpyxl
import pytest

from pay_pipeline.catalog.d1sql import render_sql
from pay_pipeline.schedules import ca_j90, ky_kde
from pay_pipeline.schedules.d1sql import AS_REPORTED, AUTO_RESOLVED, schedules_sql
from pay_pipeline.schedules.state_import import (
    CatalogDistrict,
    ImportResult,
    build_import,
    load_catalog,
    load_holds,
    load_published,
    render_report,
)

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO / "packages" / "db" / "migrations").glob("*.sql"))
TODAY = dt.date(2026, 11, 12)
NOW = dt.datetime(2026, 11, 12, 8, 0, tzinfo=dt.UTC)
SUPT_PAY = "987654.32"  # superintendent salary in the fake TSAL1: must never be imported

# ---------------------------------------------------------------- California (fake Access)

T1_COLS = ["COUNTY", "DISTRICT", "CDS", "TS1_DNAME", "TS1_COUNTY", "TS1_TYPE", "TS1_RDAYS",
           "TS1_EFFDAT", "TS1_MBONAM", "TS1_O1BONA", "TS1_O1DESC", "TS1_SUPT", "TS1_PRINE"]  # fmt: skip
T1 = [
    [
        "01",
        "00001",
        "0100001",
        "TEST ALPHA UNIFIED",
        "Test",
        "4",
        "185",
        "07/01/2024",
        "1500",
        "14",
        "Test SLP yr 1-5",
        SUPT_PAY,
        "123456",
    ],
    [
        "01",
        "00002",
        "0100002",
        "TEST BETA ELEMENTARY",
        "Test",
        "1",
        "184",
        "07/01/2024",
        "0",
        "0",
        "",
        SUPT_PAY,
        "0",
    ],
    [
        "01",
        "00003",
        "0100003",
        "TEST CITY SCHOOLS",
        "Test",
        "3",
        "186",
        "07/01/2024",
        "0",
        "0",
        "",
        SUPT_PAY,
        "0",
    ],
    [
        "01",
        "00009",
        "0100009",
        "TEST CHARTER DISTRICT",
        "Test",
        "1",
        "180",
        "07/01/2024",
        "0",
        "0",
        "",
        SUPT_PAY,
        "0",
    ],
]
T2_COLS = [
    "COUNTY",
    "DISTRICT",
    "CDS",
    "TS2_COL",
    "TS2_COL1",
    "TS2_COL1A",
    "TS2_COL2",
    "TS2_COL3",
    "TS2_COL3A",
    "TS2_ID",
]
T2 = [
    ["01", "00001", "0100001", "1", "BA      ", "", "", "", "", "1"],
    ["01", "00001", "0100001", "2", "BA+30 OR", "MA", "", "", "", "2"],
    ["01", "00002", "0100002", "1", "BA", "", "", "", "", "3"],
    ["01", "00002", "0100002", "2", "BA+30", "", "", "", "", "4"],
]
T3_COLS = [
    "COUNTY",
    "DISTRICT",
    "CDS",
    "TS3_COL",
    "TS3_STEP",
    "TS3_SALARY",
    "TS3_FTE",
    "TS3_ID",
    "TS3_SALCOST",
]
T3 = [
    # Alpha: 3 steps x 2 columns, column 2 has no step 3 (blank cell with a note)
    ["01", "00001", "0100001", "1", "1", "60000", "3", "1", "180000"],
    ["01", "00001", "0100001", "1", "2", "62000", "1", "2", "62000"],
    ["01", "00001", "0100001", "1", "3", "64000", "1", "3", "64000"],
    ["01", "00001", "0100001", "2", "1", "65000", "2", "4", "130000"],
    ["01", "00001", "0100001", "2", "2", "67000.5", "1", "5", "67000.5"],
    # Beta: the BA+30 column pays less than the BA column -> review
    ["01", "00002", "0100002", "1", "1", "70000", "1", "6", "70000"],
    ["01", "00002", "0100002", "2", "1", "65000", "1", "7", "65000"],
    # City schools (supervisory union): one column, two steps
    ["01", "00003", "0100003", "1", "1", "55000", "1", "8", "55000"],
    ["01", "00003", "0100003", "1", "2", "56000", "1", "9", "56000"],
    ["01", "00009", "0100009", "1", "1", "50000", "1", "10", "50000"],
]  # fmt: skip


def _csv(columns: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()


def fake_mdb(args: Sequence[str]) -> str:
    if args[0] == "mdb-tables":
        return "tsal125\ntsal225\ntsal325\ntsal425\n"
    table = args[2]
    return {
        "tsal125": _csv(T1_COLS, T1),
        "tsal225": _csv(T2_COLS, T2),
        "tsal325": _csv(T3_COLS, T3),
    }[table]


# ---------------------------------------------------------------- Kentucky workbook


def ky_block(code: str, name: str, fy: str, base: float) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = [
        ("Fiscal Year", f"{code} {name}", "Rank", "Years", None, "I", "II", "III")
    ]
    for rank, bump in (("I", 6000), ("II", 3000), ("III", 0), ("IV", None), ("V", None)):
        for years in range(4):
            amount = "0.00" if bump is None else f"{base + bump + 1000 * years:,.2f}"
            rows.append((fy, f"{code} {name}", rank, years, None, amount, "0.00", "0.00"))
    return rows


def write_ky(path: Path) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    for end, bases in (
        (2026, (41000.0, 52000.0)),
        (2025, (40000.0, 40000.0)),
        (2024, (39000.0, 39000.0)),
    ):
        ws = wb.create_sheet(f"{end} Certified Salary Schedule")
        fy = f"{end - 1} - {end}"
        ws.append(("Certified Salary Report",))
        ws.append(("Date Generated: test",))
        ws.append((f"Fiscal Year: {fy}",))
        ws.append(("", "", "", "", None, "Step", None, None))
        for row in ky_block("001", "Test County", fy, bases[0]) + ky_block(
            "002", "Test Independent", fy, bases[1]
        ):
            ws.append(row)
        ws.append(("", "State Summary:", "", "", None, "", "", ""))
    # fixed document dates: the same content always has the same sha256
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 1, 1)  # noqa: DTZ001
    wb.save(path)
    _fix_zip_times(path)


FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _fix_zip_times(path: Path) -> None:
    """Rewrite a zip with fixed member times, so its bytes do not depend on the clock."""
    with zipfile.ZipFile(path) as zf:
        members = [(i.filename, zf.read(i)) for i in zf.infolist()]
    # openpyxl stamps the save time into docProps/core.xml whatever the workbook says.
    members = [
        (
            name,
            re.sub(
                rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                rb"\g<1>2026-01-01T00:00:00Z\g<2>",
                data,
            )
            if name == "docProps/core.xml"
            else data,
        )
        for name, data in members
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(zipfile.ZipInfo(name, FIXED_ZIP_TIME), data)


# ---------------------------------------------------------------- CCD + catalogue

CCD = [
    # ST, ST_LEAID, LEAID, LEA_NAME, LEA_TYPE, LEA_TYPE_TEXT, SY_STATUS, UNION
    ("CA", "CA-0100001", "0600001", "Test Alpha Unified", "1", "Regular local school district", "1", ""),
    ("CA", "CA-0100002", "0600002", "Test Beta Elementary", "1", "Regular local school district", "1", ""),
    ("CA", "CA-0100003", "0600003", "Test City Elementary/High", "3", "Supervisory union", "1", "010"),
    ("CA", "CA-0100004", "0600004", "Test City Elementary", "2", "Component", "1", "010"),
    ("CA", "CA-0100005", "0600005", "Test City High", "2", "Component", "1", "010"),
    ("CA", "CA-0100009", "0600009", "Test Charter District", "7", "Independent charter district", "1", ""),
    ("KY", "KY-001001000", "2100001", "Test County", "1", "Regular local school district", "1", ""),
    ("KY", "KY-002002000", "2100002", "Test Independent", "1", "Regular local school district", "1", ""),
]  # fmt: skip
CATALOG = {
    "0600001": ("CA", "Test Alpha Unified"),
    "0600002": ("CA", "Test Beta Elementary"),
    "0600004": ("CA", "Test City Elementary"),
    "0600005": ("CA", "Test City High"),
    "0600006": ("CA", "Test Missing Unified"),
    "2100001": ("KY", "Test County"),
    "2100002": ("KY", "Test Independent"),
}


def write_sources(root: Path, ky_sha: str | None = None) -> tuple[Path, Path]:
    src = root / "sources"
    src.mkdir(parents=True)
    with zipfile.ZipFile(src / "j902425.exe", "w") as zf:
        zf.writestr(zipfile.ZipInfo("j902425readme.docx", FIXED_ZIP_TIME), b"readme")
        zf.writestr(zipfile.ZipInfo("tsal2425.accdb", FIXED_ZIP_TIME), b"not really access")
    write_ky(src / "ky_certified_salary_schedule_2014-2026.xlsx")
    files = []
    for name, url in (
        ("j902425.exe", "https://www3.cde.ca.gov/ds-downloads/fd/cs/j902425.exe"),
        ("ky_certified_salary_schedule_2014-2026.xlsx", "https://www.education.ky.gov/x.xlsx"),
    ):
        data = (src / name).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if name.startswith("ky") and ky_sha:
            sha = ky_sha
        files.append({"name": name, "url": url, "final_url": url, "fetched_at": "2026-11-12T11:00:00Z",
                      "sha256": sha, "bytes": len(data), "content_type": "application/octet-stream"})  # fmt: skip
    (src / "manifest.json").write_text(json.dumps({"release_prefix": "src-test", "files": files}))

    ccd = root / "ccd"
    ccd.mkdir()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["ST", "ST_LEAID", "LEAID", "LEA_NAME", "LEA_TYPE", "LEA_TYPE_TEXT", "SY_STATUS", "UNION"]
    )
    writer.writerows(CCD)
    with zipfile.ZipFile(ccd / "ccd_lea_029_2425_w_test.zip", "w") as zf:
        zf.writestr("ccd_lea_029_2425_w_test.csv", buf.getvalue().encode("utf-8-sig"))
    return src, ccd


def catalog() -> dict[str, CatalogDistrict]:
    return {k: CatalogDistrict(k, st, name, True) for k, (st, name) in CATALOG.items()}


def run_import(
    tmp_path: Path, ky_sha: str | None = None, holds: dict[tuple[str, str, str], str] | None = None
) -> ImportResult:
    src, ccd = write_sources(tmp_path, ky_sha)
    return build_import(
        src, ccd, catalog(), [], "src-test-1", TODAY, ky_years=2, runner=fake_mdb, holds=holds
    )


def fresh_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    for path in MIGRATIONS:
        db.executescript(path.read_text(encoding="utf-8"))
    db.execute(
        "INSERT INTO states (code, name, slug) VALUES ('CA', 'California', 'california'), ('KY', 'Kentucky', 'kentucky')"
    )
    for nces, (st, name) in CATALOG.items():
        db.execute(
            "INSERT INTO districts (nces_id, name, slug, state) VALUES (?, ?, ?, ?)",
            (nces, name, name.lower().replace(" ", "-"), st),
        )
    return db


def load(db: sqlite3.Connection, result: ImportResult) -> None:
    db.executescript(render_sql(schedules_sql(result, now=NOW)))


def counts(db: sqlite3.Connection) -> dict[str, int]:
    tables = ("source_documents", "extraction_runs", "schedules", "lanes", "steps", "cells",
              "stipends", "review_queue", "district_summary", "cache_purge_queue")  # fmt: skip
    return {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}  # noqa: S608


# ---------------------------------------------------------------- tests


class TestReaders:
    def test_j90_tables_and_cells(self, tmp_path: Path) -> None:
        accdb = ca_j90.extract_accdb(write_sources(tmp_path)[0] / "j902425.exe", tmp_path / "x")
        assert accdb.name == "tsal2425.accdb"
        data = ca_j90.read_j90(accdb, fake_mdb)
        assert data.school_year == "2024-25"
        alpha = next(s for s in ca_j90.j90_schedules(data) if s.state_district_id == "0100001")
        assert [ln.label_raw for ln in alpha.lanes] == ["BA", "BA+30 OR MA"]
        assert [ln.lane_normalized for ln in alpha.lanes] == ["BA", None]
        assert alpha.amount(1, 1) == 6700050
        assert alpha.cells[(2, 1)] == ca_j90.Cell(None, ca_j90.MISSING_CELL_NOTE)
        assert alpha.contract_days == 185
        assert alpha.source_sheet == "TSAL325"
        assert [(s.name, s.amount_cents, s.amount_raw) for s in alpha.stipends] == [
            ("Master's degree", 150000, None),
            ("Test SLP yr 1-5", None, "14"),
        ]
        # Individual pay (superintendent, principals) never leaves the reader.
        assert "987654" not in repr(data) and "123456" not in repr(data)

    def test_j90_rejects_unexpected_tables(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="TSAL1/2/3"):
            ca_j90.read_j90(tmp_path / "x.accdb", lambda args: "tsal125\ntsal224\n")

    def test_ky_sheets_ranks_and_zero_cells(self, tmp_path: Path) -> None:
        path = tmp_path / "ky.xlsx"
        write_ky(path)
        sheets = ky_kde.list_sheets(path)
        assert [s.school_year for s in sheets] == ["2023-24", "2024-25", "2025-26"]
        county = ky_kde.read_sheet(path, sheets[-1])[0]
        assert (county.state_district_id, county.district_name) == ("001", "Test County")
        assert [ln.label_raw for ln in county.lanes] == ["Rank III", "Rank II", "Rank I"]
        assert [ln.lane_normalized for ln in county.lanes] == ["BA", "MA", "MA+30"]
        assert [s.years_experience for s in county.steps] == [0, 1, 2, 3]
        assert county.amount(0, 0) == 4100000 and county.amount(3, 2) == 5000000


class TestBuildImport:
    def test_mapping_statuses_and_skips(self, tmp_path: Path) -> None:
        result = run_import(tmp_path)
        by = {(p.nces_id, p.draft.school_year): p for p in result.prepared}
        assert by[("0600001", "2024-25")].status == "published"
        beta = by[("0600002", "2024-25")]
        # D-028: odd figures in a state file are published as reported, findings kept
        assert beta.status == "published" and beta.reasons == []
        assert beta.accepted_reasons[0].startswith("[monotonic_lane]")
        # Supervisory union -> both member districts, with a note
        for member in ("0600004", "0600005"):
            assert "Shared schedule of Test City Elementary/High" in (
                by[(member, "2024-25")].draft.notes or ""
            )
        assert [(k.state_district_id, "LEA_TYPE 7" in k.reason) for k in result.skipped] == [
            ("0100009", True)
        ]
        # Kentucky: two latest sheets only; +30 % start pay at Test Independent: as reported
        assert {y for (_, y) in by if _.startswith("21")} == {"2024-25", "2025-26"}
        assert by[("2100001", "2025-26")].status == "published"
        assert by[("2100002", "2025-26")].status == "published"
        assert by[("2100002", "2025-26")].accepted_reasons[0].startswith("[start_change]")

    def test_report(self, tmp_path: Path) -> None:
        report = render_report(run_import(tmp_path))
        assert "| CA | 2024-25 | 4 | 3 | 75.0% | 1 | 4 | 4 | 0 |" in report
        assert "| KY | 2025-26 | 2 | 2 | 100.0% | 0 | 2 | 2 | 0 |" in report
        assert "| CA | 2024-25 | monotonic_lane | 0 | 1 |" in report
        assert "1 / 5 học khu còn thiếu" in report and "Test Missing Unified" in report
        assert "start_change" in report


KY_2526 = (
    "SELECT s.id, s.status FROM schedules s JOIN districts x ON x.id = s.district_id"
    " WHERE x.nces_id = '2100001' AND s.school_year = '2025-26'"
)
HOLD_KEY = ("KY", "001", "2025-26")
HOLD = {HOLD_KEY: "Kiểm tra chéo: ô lệch tài liệu học khu"}


class TestSql:
    def test_load_is_idempotent_and_consistent(self, tmp_path: Path) -> None:
        result = run_import(tmp_path)
        db = fresh_db()
        load(db, result)
        first = counts(db)
        load(db, result)
        assert counts(db) == first
        assert first["source_documents"] == 2 and first["extraction_runs"] == 2
        assert first["schedules"] == 8
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE '\\_imp%' ESCAPE '\\'"
            ).fetchall()
            == []
        )
        status = dict(
            db.execute("SELECT status, count(*) FROM schedules GROUP BY status").fetchall()
        )
        assert status == {"published": 8}
        # findings of the two schedules published as reported are kept, already resolved (D-028)
        rows = db.execute("SELECT resolved_at IS NOT NULL, resolution FROM review_queue").fetchall()
        assert len(rows) == 2 and all(r == (1, AS_REPORTED) for r in rows)
        rows = db.execute(
            "SELECT s.school_year, d.url, d.release_tag, d.asset_name FROM schedules s"
            " JOIN source_documents d ON d.id = s.source_document_id"
        ).fetchall()
        assert all(
            r[0] and r[1].startswith("https://") and r[2] == "src-test-1" and r[3] for r in rows
        )
        # cells: blank cell kept with its note; superintendent pay nowhere in the SQL
        assert (
            db.execute(
                "SELECT count(*) FROM cells WHERE amount_cents IS NULL AND note IS NOT NULL"
            ).fetchone()[0]
            == 1
        )
        assert SUPT_PAY not in render_sql(schedules_sql(result, now=NOW))
        summary = db.execute(
            "SELECT start_ba_cents, max_salary_cents FROM district_summary s"
            " JOIN districts d ON d.id = s.district_id WHERE d.nces_id = '2100001' AND s.school_year = '2025-26'"
        ).fetchone()
        assert summary == (4100000, 5000000)
        # every district with a schedule is queued once for the website cache purge (D-023)
        queued = db.execute("SELECT count(*) FROM cache_purge_queue").fetchone()[0]
        assert (
            queued == db.execute("SELECT count(DISTINCT district_id) FROM schedules").fetchone()[0]
        )

    def test_new_source_supersedes_published(self, tmp_path: Path) -> None:
        db = fresh_db()
        load(db, run_import(tmp_path / "a"))
        load(db, run_import(tmp_path / "b", ky_sha="f" * 64))
        rows = db.execute(
            "SELECT s.status, s.superseded_by IS NOT NULL, d.sha256 = ? FROM schedules s"
            " JOIN source_documents d ON d.id = s.source_document_id"
            " JOIN districts x ON x.id = s.district_id WHERE x.nces_id = '2100001' AND s.school_year = '2025-26'"
            " ORDER BY s.id",
            ("f" * 64,),
        ).fetchall()
        assert rows == [("superseded", 1, 0), ("published", 0, 1)]
        # California came from the same file both times: nothing new
        assert (
            db.execute(
                "SELECT count(*) FROM schedules s JOIN districts x ON x.id = s.district_id WHERE x.state = 'CA'"
            ).fetchone()[0]
            == 4
        )

    def test_hold_sends_published_schedule_back_to_review(self, tmp_path: Path) -> None:
        db = fresh_db()
        load(db, run_import(tmp_path / "a"))
        hold = {("KY", "001", "2025-26"): "Kiểm tra chéo: ô lệch tài liệu học khu"}
        load(db, run_import(tmp_path / "b", holds=hold))
        row = db.execute(
            "SELECT s.status, s.published_at, (SELECT group_concat(reason) FROM review_queue r"
            " WHERE r.schedule_id = s.id) FROM schedules s JOIN districts x ON x.id = s.district_id"
            " WHERE x.nces_id = '2100001' AND s.school_year = '2025-26'"
        ).fetchone()
        assert row == ("draft", None, "[cross_check] Kiểm tra chéo: ô lệch tài liệu học khu")
        years = db.execute(
            "SELECT s.school_year FROM district_summary s JOIN districts x ON x.id = s.district_id"
            " WHERE x.nces_id = '2100001'"
        ).fetchall()
        assert years == [("2024-25",)]
        assert db.execute("SELECT count(*) FROM schedules").fetchone()[0] == 8

    def open_reasons(self, db: sqlite3.Connection, schedule_id: int) -> list[str]:
        rows = db.execute(
            "SELECT reason FROM review_queue WHERE schedule_id = ? AND resolved_at IS NULL",
            (schedule_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def test_reasons_no_longer_given_are_closed_and_schedule_published(
        self, tmp_path: Path
    ) -> None:
        # D-024: a re-import with changed checks releases what now passes.
        db = fresh_db()
        load(db, run_import(tmp_path / "a", holds=HOLD))
        sid, status = db.execute(KY_2526).fetchone()
        assert status == "draft" and len(self.open_reasons(db, sid)) == 1
        load(db, run_import(tmp_path / "b"))
        assert db.execute(KY_2526).fetchone() == (sid, "published")
        assert self.open_reasons(db, sid) == []
        resolution = db.execute(
            "SELECT resolution FROM review_queue WHERE schedule_id = ?", (sid,)
        ).fetchone()[0]
        assert resolution == AUTO_RESOLVED

    def test_open_finding_of_a_state_file_is_closed_as_reported(self, tmp_path: Path) -> None:
        # A schedule held under the old rule (open monotonic reason) is published on re-import.
        db = fresh_db()
        load(db, run_import(tmp_path / "a"))
        sid = db.execute(
            "SELECT s.id FROM schedules s JOIN districts x ON x.id = s.district_id"
            " WHERE x.nces_id = '0600002'"
        ).fetchone()[0]
        db.execute("UPDATE review_queue SET resolved_at = NULL, resolution = NULL")
        db.execute(
            "UPDATE schedules SET status = 'draft', published_at = NULL WHERE id = ?", (sid,)
        )
        load(db, run_import(tmp_path / "b"))
        assert db.execute("SELECT status FROM schedules WHERE id = ?", (sid,)).fetchone()[0] == (
            "published"
        )
        rows = db.execute(
            "SELECT resolution FROM review_queue WHERE schedule_id = ?", (sid,)
        ).fetchall()
        assert rows == [(AS_REPORTED,)]

    def test_rejected_draft_is_not_published_by_a_re_import(self, tmp_path: Path) -> None:
        db = fresh_db()
        load(db, run_import(tmp_path / "a", holds=HOLD))
        sid, _ = db.execute(KY_2526).fetchone()
        db.execute(
            "UPDATE review_queue SET resolved_at = '2026-11-13T00:00:00Z',"
            " resolution = 'rejected: không phải bảng giáo viên' WHERE schedule_id = ?",
            (sid,),
        )
        load(db, run_import(tmp_path / "b"))
        assert db.execute(KY_2526).fetchone() == (sid, "draft")
        load(db, run_import(tmp_path / "c", holds={HOLD_KEY: "lý do khác"}))
        assert self.open_reasons(db, sid) == []

    def test_approved_schedule_is_not_sent_back_by_a_re_import(self, tmp_path: Path) -> None:
        db = fresh_db()
        load(db, run_import(tmp_path / "a", holds=HOLD))
        sid, _ = db.execute(KY_2526).fetchone()
        db.execute(
            "UPDATE schedules SET status = 'published', published_at = '2026-11-13T00:00:00Z'"
            " WHERE id = ?",
            (sid,),
        )
        db.execute(
            "UPDATE review_queue SET resolved_at = '2026-11-13T00:00:00Z',"
            " resolution = 'approved (0 cell edits)' WHERE schedule_id = ?",
            (sid,),
        )
        load(db, run_import(tmp_path / "b", holds=HOLD))
        assert db.execute(KY_2526).fetchone() == (sid, "published")
        assert self.open_reasons(db, sid) == []

    def test_holds_file(self, tmp_path: Path) -> None:
        path = tmp_path / "h.json"
        path.write_text(
            json.dumps(
                {
                    "holds": [
                        {
                            "state": "CA",
                            "state_district_id": "1",
                            "school_year": "2024-25",
                            "reason": "x",
                        }
                    ]
                }
            )
        )
        assert load_holds(path) == {("CA", "1", "2024-25"): "x"}
        path.write_text(
            json.dumps(
                {
                    "holds": [
                        {
                            "state": "CA",
                            "state_district_id": "1",
                            "school_year": "2024-25",
                            "reason": " ",
                        }
                    ]
                }
            )
        )
        with pytest.raises(ValueError):
            load_holds(path)
        assert load_holds(REPO / "pipeline" / "review-holds.json")


class TestWranglerJson:
    def test_catalog_and_published(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "results": [
                            {"nces_id": "0600001", "state": "CA", "name": "T", "active": 1}
                        ],
                        "success": True,
                    }
                ]
            )
        )
        assert load_catalog(path)["0600001"].active is True
        pub = tmp_path / "p.json"
        pub.write_text(
            json.dumps(
                [
                    {
                        "results": [
                            {
                                "nces_id": "0600001",
                                "school_year": "2023-24",
                                "schedule_type": "teacher",
                                "title": "",
                                "start_cents": 5000000,
                            }
                        ]
                    }
                ]
            )
        )
        assert load_published(pub)[0].start_cents == 5000000
        with pytest.raises(FileNotFoundError):
            load_catalog(tmp_path / "missing.json")
