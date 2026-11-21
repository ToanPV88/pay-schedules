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
    return {"reader": "stipend-layout@2", "page": page, "school_year": year, "title": title,
            "columns": cols, "rows": rows, "problems": []}  # fmt: skip


def _doc(name: str, tables: list[dict], fetched: str = "2026-11-01T00:00:00Z") -> DocReading:
    return DocReading(
        nces_id="9900001", asset_name=name, url=f"https://x.invalid/{name}",
        sha256=(name.encode().hex() * 64)[:64],
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


def _raw(columns: list[str], rows: list[tuple[str, list[float | None]]]) -> dict:
    return {"page": 1, "school_year": "2026-27", "title": "", "columns": columns,
            "rows": [{"label": lab, "amounts": a} for lab, a in rows]}  # fmt: skip


def test_clean_collapses_scattered_single_amounts_and_drops_footer() -> None:
    from pay_pipeline.extra_pay.read import check, clean

    t = clean(
        _raw(
            ["Column 1", "Column 2"],
            [("Head Football Coach $", [None, 6500.0]), ("Head Track Coach", [3000.0, None]),
             ("Head Volleyball Coach", [None, 4200.0]), ("Band Director", [2000.0, None]),
             ("Head Soccer Coach", [None, 2500.0]), ("Board Approved: June 25,", [None, 2026.0])],
        )
    )  # fmt: skip
    assert t["columns"] == ["Amount"]
    assert t["rows"][0]["label"] == "Head Football Coach"
    assert len(t["rows"]) == 5 and check(t) == []


def test_check_rejects_unnamed_columns_and_percent_rows() -> None:
    from pay_pipeline.extra_pay.read import check, clean

    rows = [(f"Head {s} Coach", [1000.0, 2000.0]) for s in ["Football", "Track", "Golf", "Tennis"]]
    t = clean(
        _raw(["Column 1", "Column 2"], [*rows, ("Athletic Director 14.00%", [4858.0, 4958.0])])
    )
    problems = check(t)
    assert any("tiêu đề cột" in p for p in problems)
    assert any("phần trăm" in p for p in problems)


def test_old_school_year_is_not_published() -> None:
    result, outcomes = prepare([_doc("d", [_table("2023-24", 3)])], CATALOG, TODAY)
    assert result.prepared == [] and outcomes[0].status == "no_table"


def test_check_rejects_repeated_labels() -> None:
    from pay_pipeline.extra_pay.read import check

    t = _raw(["Amount"], [("HEAD COACH", [7500.0])] * 4 + [("Band Director", [2000.0])] * 2)
    assert any("trùng tên" in p for p in check(t))


def _line(label: str, amount: str | None = None) -> object:
    from pay_pipeline.pdf_pipeline.read import Line, Word

    words = [Word(t, 10.0 + 40 * i, 40.0 + 40 * i) for i, t in enumerate(label.split())]
    if amount:
        words.append(Word(amount, 400.0, 440.0))
    return Line(words)


def test_heading_names_role_only_rows() -> None:
    from pay_pipeline.extra_pay.read import find_tables

    lines = [_line("Football"), _line("Head", "$5,000"), _line("Asst.", "$3,000"),
             _line("Basketball"), _line("Head", "$4,500"), _line("Asst.", "$2,800"),
             _line("Head Golf Coach", "$2,000")]  # fmt: skip
    labels = [r.label for r in find_tables(lines, 1)[0].rows]  # type: ignore[arg-type]
    assert labels == ["Football Head", "Football Asst", "Basketball Head", "Basketball Asst",
                      "Head Golf Coach"]  # fmt: skip


def test_document_year_from_cover() -> None:
    from pay_pipeline.extra_pay.read import document_year

    pages = [[_line("Negotiated Agreement 2025-2026")], [_line("Stipends")]]
    assert document_year(pages) == "2025-26"  # type: ignore[arg-type]


def test_clean_drops_sentences_but_flags_many() -> None:
    from pay_pipeline.extra_pay.read import check, clean

    good = [(f"Head {s} Coach", [1000.0]) for s in ["Football", "Track", "Golf", "Tennis", "Swim"]]
    t = clean(_raw(["Amount"], [*good, ("Teachers are compensated", [187.0])]))
    assert len(t["rows"]) == 5 and check(t) == []
    t = clean(_raw(["Amount"], [*good, *[("monetary supplements", [500.0])] * 3]))
    assert any("câu văn" in p for p in check(t))


def test_future_year_is_not_published() -> None:
    result, _ = prepare([_doc("d", [_table("2027-28", 3)])], CATALOG, TODAY)
    assert result.prepared == []


def _db() -> object:
    import sqlite3
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    for path in sorted((repo / "packages" / "db" / "migrations").glob("*.sql")):
        db.executescript(path.read_text(encoding="utf-8"))
    db.execute("INSERT INTO states (code, name, slug) VALUES ('ZZ', 'Zed', 'zed')")
    db.execute(
        "INSERT INTO districts (nces_id, name, slug, state)"
        " VALUES ('9900001', 'Test ISD', 'test-isd', 'ZZ')"
    )
    return db


def _load(db: object, docs: list[DocReading]) -> None:
    from pay_pipeline.extra_pay.build import with_retire

    result, _ = prepare(docs, CATALOG, TODAY)
    sql = with_retire(schedules_sql(result, now=dt.datetime(2026, 11, 21, tzinfo=dt.UTC)))
    db.executescript(";\n".join(sql) + ";")  # type: ignore[attr-defined]


def test_reimport_retires_tables_no_longer_read() -> None:
    db = _db()
    _load(db, [_doc("d", [_table("2026-27", 3, "Athletics"), _table("2026-27", 4, "Clubs")])])
    q = "SELECT title, status FROM schedules WHERE schedule_type = 'extra_duty' ORDER BY id"
    assert db.execute(q).fetchall() == [("Athletics", "published"), ("Clubs", "published")]  # type: ignore[attr-defined]
    _load(db, [_doc("d", [_table("2026-27", 3, "Athletics")])])
    assert db.execute(q).fetchall() == [("Athletics", "published"), ("Clubs", "superseded")]  # type: ignore[attr-defined]
    cells = db.execute(  # type: ignore[attr-defined]
        "SELECT count(*) FROM cells c JOIN schedules s ON s.id = c.schedule_id"
        " WHERE s.status = 'published'"
    ).fetchone()[0]
    assert cells == 5
