"""Chọn bảng phụ cấp và dựng ScheduleDraft (PLAN 11), dữ liệu GIẢ LẬP."""

from __future__ import annotations

import datetime as dt

from pay_pipeline.extra_pay.build import DocReading, prepare, to_draft
from pay_pipeline.extra_pay.read import title_of
from pay_pipeline.schedules.d1sql import schedules_sql
from pay_pipeline.schedules.state_import import CatalogDistrict

TODAY = dt.date(2026, 11, 21)


def _table(year: str, page: int, title: str = "", columns: list[str] | None = None) -> dict:
    cols = columns or ["Amount"]
    rows = [
        {"label": "Head Football Coach", "amounts": [6500.0] * len(cols)},
        {"label": "Assistant Football Coach", "amounts": [3500.0] * len(cols)},
        {"label": "Head Volleyball Coach", "amounts": [4200.0] * len(cols)},
        {"label": "Band Director", "amounts": [None] * len(cols)},
        {"label": "Head Track Coach", "amounts": [3000.0] * len(cols)},
    ]
    return {"reader": "stipend-layout@1", "page": page, "school_year": year, "title": title,
            "columns": cols, "rows": rows, "problems": []}  # fmt: skip


def _doc(name: str, tables: list[dict], fetched: str = "2026-11-01T00:00:00Z") -> DocReading:
    return DocReading(
        nces_id="9900001", asset_name=name, url=f"https://x.invalid/{name}", sha256=name * 8,
        fetched_at=fetched, content_type="application/pdf", release_tag="docs-t",
        stipend_pages=[t["page"] for t in tables], tables=tables,
    )  # fmt: skip


CATALOG = {"9900001": CatalogDistrict("9900001", "ZZ", "Test ISD", True)}


def test_single_amount_column_has_no_lane_and_empty_cell_note() -> None:
    d = to_draft(_table("2026-27", 3), "ZZ", "9900001", "Test ISD")
    assert d.schedule_type == "extra_duty" and d.lanes == []
    assert d.cells[(0, None)].amount_cents == 650_000
    assert d.cells[(3, None)].amount_cents is None and d.cells[(3, None)].note


def test_columns_become_lanes() -> None:
    d = to_draft(_table("2026-27", 3, columns=["Yr 1-3", "Yr 4+"]), "ZZ", "9900001", "Test ISD")
    assert [lane.label_raw for lane in d.lanes] == ["Yr 1-3", "Yr 4+"]
    assert d.cells[(1, 1)].amount_cents == 350_000


def test_prepare_picks_year_in_force_and_skips_failing_tables() -> None:
    old = _doc("old", [_table("2025-26", 4)])
    bad = _table("2026-27", 5)
    bad["problems"] = ["ít hàng"]
    new = _doc("new", [_table("2026-27", 3), _table("2026-27", 3), bad])
    result, outcomes = prepare([old, new], CATALOG, TODAY)
    assert [o.status for o in outcomes] == ["published"]
    assert len(result.prepared) == 1  # the duplicate is dropped, the failing table left out
    assert result.prepared[0].draft.school_year == "2026-27"
    assert result.sources[0].asset_name == "new"
    sql = "\n".join(schedules_sql(result))
    assert "'extra_duty'" in sql and "'published'" in sql


def test_same_title_tables_get_page_suffix() -> None:
    doc = _doc(
        "d",
        [_table("2026-27", 3), {**_table("2026-27", 4), "rows": _table("x", 0)["rows"][:5][::-1]}],
    )
    result, _ = prepare([doc], CATALOG, TODAY)
    titles = [p.draft.title for p in result.prepared]
    assert titles == [
        "Coaching and extra-duty stipends",
        "Coaching and extra-duty stipends (page 4)",
    ]


def test_no_passing_table_is_reported_not_imported() -> None:
    t = _table("2026-27", 3)
    t["problems"] = ["số tiền ngoài khoảng"]
    result, outcomes = prepare([_doc("d", [t])], CATALOG, TODAY)
    assert result.prepared == [] and outcomes[0].status == "no_table"


def test_title_drops_running_header() -> None:
    ctx = (
        "Pearland Independent School District\nCampus Stipends\nDAWSON HIGH SCHOOL\nPosition Amount"
    )
    assert title_of(ctx) == "Campus Stipends — DAWSON HIGH SCHOOL"
