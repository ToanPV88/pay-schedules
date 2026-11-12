"""Validate checks (PLAN Công đoạn 5, bước Validate) on small hand-made schedules."""

from __future__ import annotations

import datetime as dt

import pytest

from pay_pipeline.schedules.model import (
    Cell,
    Lane,
    ScheduleDraft,
    Step,
    dollars_to_cents,
    normalize_lane,
    school_year_start,
)
from pay_pipeline.schedules.validate import (
    check_cell_count,
    check_monotonic,
    check_range,
    check_school_year,
    check_start_change,
    compare_extractions,
    start_salary,
    summarize,
    validate,
)

TODAY = dt.date(2026, 11, 12)


def grid(
    rows: list[list[float | None]], lanes: int | None = None, year: str = "2025-26"
) -> ScheduleDraft:
    """Rows are steps, columns are lanes; amounts in dollars, None = blank cell with a note."""
    width = len(rows[0]) if lanes is None else lanes
    cells: dict[tuple[int, int | None], Cell] = {}
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            cells[(i, j)] = (
                Cell(None, "blank in source") if value is None else Cell(round(value * 100))
            )
    return ScheduleDraft(
        state="CA",
        state_district_id="0000000",
        district_name="Test",
        school_year=year,
        lanes=[Lane(f"L{j}") for j in range(width)],
        steps=[Step(str(i + 1)) for i in range(len(rows))],
        cells=cells,
    )


GOOD: list[list[float | None]] = [[50000, 52000], [51000, 53000], [52000, None]]


class TestModel:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("BA", "BA"),
            ("B.A.", "BA"),
            ("ba + 30", "BA+30"),
            ("MA", "MA"),
            ("MA+15", "MA+15"),
            ("Ph.D.", "PhD"),
            ("Doctorate", "PhD"),
            ("BA+45 OR MA", None),
            ("BA+60+CRED", None),
            ("BA NON-CRED", None),
            ("Column 3", None),
        ],
    )
    def test_normalize_lane_is_conservative(self, label: str, expected: str | None) -> None:
        assert normalize_lane(label) == expected

    def test_money_and_school_year(self) -> None:
        assert dollars_to_cents("48,899.00") == 4889900
        assert dollars_to_cents(77693.005) == 7769301
        assert school_year_start("2024-25") == 2024
        assert school_year_start("1999-00") == 1999
        with pytest.raises(ValueError):
            school_year_start("2024-26")


class TestChecks:
    def test_good_schedule_passes(self) -> None:
        assert validate(grid(GOOD), today=TODAY) == []

    def test_pay_falling_with_step_or_lane(self) -> None:
        issues = check_monotonic(grid([[50000, 52000], [49000, 51000]]))
        assert [i.code for i in issues] == ["monotonic_step", "monotonic_step"]
        issues = check_monotonic(grid([[50000, 48000], [51000, 53000]]))
        assert [i.code for i in issues] == ["monotonic_lane"]
        assert "L0" in issues[0].message and "$48,000.00" in issues[0].message

    def test_noted_exception_and_blank_cells_do_not_break_order(self) -> None:
        s = grid([[50000, 52000], [None, 53000], [51000, 54000]])
        assert check_monotonic(s) == []
        s.cells[(2, 0)] = Cell(4900000, "Frozen step per contract")
        assert check_monotonic(s) == []

    def test_cell_count(self) -> None:
        s = grid(GOOD)
        del s.cells[(0, 1)]
        s.cells[(1, 1)] = Cell(None)
        codes = [i.message for i in check_cell_count(s)]
        assert any("Thiếu 1 ô" in m for m in codes)
        assert any("không có ghi chú" in m for m in codes)

    def test_range_catches_hourly_and_daily_figures(self) -> None:
        assert check_range(grid([[52.5, 55]]))[0].code == "range"
        assert check_range(grid([[350, 400]]))[0].code == "range"
        assert check_range(grid([[400000, 410000]]))[0].code == "range"
        assert check_range(grid([[48000, 52000]])) == []

    def test_school_year(self) -> None:
        assert check_school_year(grid(GOOD, year="2027-28"), TODAY) == []
        assert check_school_year(grid(GOOD, year="2028-29"), TODAY)[0].code == "school_year"
        assert check_school_year(grid(GOOD, year="2024-26"), TODAY)[0].code == "school_year"
        older = grid(GOOD, year="2023-24")
        assert check_school_year(older, TODAY, published_year="2024-25")[0].code == "school_year"
        assert check_school_year(older, TODAY, "2024-25", allow_history=True) == []

    def test_start_change(self) -> None:
        s = grid(GOOD)
        assert start_salary(s) == 5000000
        assert check_start_change(s, 4500000) == []
        assert check_start_change(s, 4000000)[0].code == "start_change"
        assert check_start_change(s, None) == []
        s.cells[(0, 0)] = Cell(None, "blank")
        assert start_salary(s) == 5200000

    def test_double_extraction(self) -> None:
        a, b = grid(GOOD), grid(GOOD)
        assert compare_extractions(a, b) == []
        b.cells[(1, 1)] = Cell(5300100)
        assert compare_extractions(a, b)[0].message.startswith("1 ô lệch")
        c = grid([[50000], [51000], [52000]])
        assert "lưới" in compare_extractions(a, c)[0].message
        assert validate(a, today=TODAY, second_extraction=b)[0].code == "double_extraction"

    def test_highest_lane_first_is_accepted_when_consistent(self) -> None:
        ranks = [[60000, 55000, 50000], [61000, 56000, 51000], [62000, 57000, 52000]]
        assert check_monotonic(grid(ranks)) == []
        ranks[2][2] = 57500  # one pair breaks the falling pattern
        assert [i.code for i in check_monotonic(grid(ranks))] == ["monotonic_lane"]
        # a single falling pair in a two-lane table is not a pattern: flagged
        assert [i.code for i in check_monotonic(grid([[70000, 65000]]))] == ["monotonic_lane"]

    def test_summarize_groups_by_check(self) -> None:
        issues = check_monotonic(grid([[5, 6, 4], [4, 5, 3], [3, 4, 2], [2, 3, 1], [1, 2, 0.5]]))
        reasons = summarize(issues)
        assert len(reasons) == 2
        assert reasons[0].startswith("[monotonic_step]") and "chỗ khác" in reasons[0]
