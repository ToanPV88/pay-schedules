"""Federal pay tables (D-065): OPM HTML pages and the VA nurse workbook."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import openpyxl

from pay_pipeline.federal.tables import load_sources, pay_tables_sql, read_opm, read_va

FIXTURES = Path(__file__).parent / "fixtures"
EFF = dt.datetime(2026, 9, 20)  # noqa: DTZ001 (Excel dates have no zone)


def test_opm_locality_page() -> None:
    t = read_opm((FIXTURES / "opm_2026_ATL.html").read_text(), "opm_2026_ATL.html")
    assert t.problems == []
    assert (t.family, t.code, t.year) == ("gs_locality", "ATL", 2026)
    assert t.slug == "atlanta-athens-clarke-county-sandy-springs-ga-al"
    assert t.rows[0] == "GS-1" and t.rows[-1] == "GS-15"
    assert t.cols == [f"Step {i}" for i in range(1, 11)]
    assert t.grid[0][0].amount_cents == 2_795_700
    assert (t.grid[14][9].amount_cents, t.grid[14][9].note) == (19_720_000, "*")
    assert t.notes is not None and t.notes.startswith("* Rate limited")
    assert "Locality Payment of 23.79%" in t.title


def test_opm_base_page_ignores_wgi_column() -> None:
    html = (FIXTURES / "opm_2026_ATL.html").read_text()
    html = html.replace("Salary Table 2026-ATL", "Salary Table 2026-GS")
    html = html.replace("Step&nbsp;10</th>", "Step&nbsp;10</th><th>WGI</th>")
    html = html.replace("<p>34968</p></td>", "<p>34968</p></td><td><p>VARIES</p></td>")
    t = read_opm(html, "opm_2026_GS.html")
    assert (t.family, t.slug) == ("gs", "base")
    assert len(t.grid[0]) == 10 and t.problems == []


def _va_workbook(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Nurses"
    ws.append(["Current as of 4 Nov 2026"])
    head = ["Station", "Set ID", "Sal Plan", "Eff Date", "Pay Table Ind", "Schedule Title",
            "Geoloc Cd (City,State,County)", "Occ Series", "Assignment Cd", "Step Increment",
            "Pay Cap Override Type", "Nurse Level", "Nurse Step", "Grade"]  # fmt: skip
    ws.append(head + [f"Step {i}" for i in range(1, 27)])
    geo = "471750149 - MURFREESBORO, TN, RUTHERFORD;  471760037 - NASHVILLE, TN, DAVIDSON"
    for level, grade, base in ((2, "01", 87769), (3, "01", 87769), (0, "02", 103562)):
        steps = [base + 2633 * i for i in range(12)]
        ws.append(["626", "VN", "N001", EFF, "Nurse",
                   "RN STAFF - GASTROINTESTINAL SP-0610-GI", geo, "0610", "GI", 2633,
                   "Registered Nurse", level, None, grade, *steps])  # fmt: skip
    wb.save(path)


def test_va_workbook(tmp_path: Path) -> None:
    path = tmp_path / "va_nurse_lps_2026.xlsx"
    _va_workbook(path)
    [t] = read_va(path, path.name)
    assert t.problems == []
    assert (t.family, t.code, t.slug, t.group_slug) == (
        "va_nurse",
        "626-N001",
        "station-626-n001",
        "station-626",
    )
    assert t.rows == ["Nurse I, Level 2", "Nurse I, Level 3", "Nurse II"]
    assert len(t.cols) == 12 and t.grid[2][0].amount_cents == 10_356_200
    assert (t.state, t.year, t.effective_date) == ("TN", 2026, "2026-09-20")
    assert t.area == "Murfreesboro, TN; Nashville, TN"


def test_sql_replaces_family_year(tmp_path: Path) -> None:
    (tmp_path / "opm_2026_ATL.html").write_text((FIXTURES / "opm_2026_ATL.html").read_text())
    _va_workbook(tmp_path / "va_nurse_lps_2026.xlsx")
    files = [
        {"name": n, "url": f"https://example.gov/{n}", "sha256": "a" * 64,
         "fetched_at": "2026-11-16T00:00:00Z"}
        for n in ("opm_2026_ATL.html", "va_nurse_lps_2026.xlsx")
    ]  # fmt: skip
    (tmp_path / "manifest.json").write_text(json.dumps({"files": files}))
    tables, by_name = load_sources(tmp_path)
    sql = "\n".join(pay_tables_sql(tables, by_name, "src-federal-pay-2026-1"))
    assert "DELETE FROM pay_tables WHERE family = 'gs_locality' AND year = 2026" in sql
    assert "DELETE FROM pay_tables WHERE family = 'va_nurse' AND year = 2026" in sql
    assert "'atlanta-athens-clarke-county-sandy-springs-ga-al'" in sql
    assert "INSERT INTO pay_cells" in sql and sql.rstrip().endswith("DROP TABLE _imp_pay_cells")
