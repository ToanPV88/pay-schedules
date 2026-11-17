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
    check_labels,
    check_monotonic,
    check_range,
    check_school_year,
    check_start_change,
    compare_extractions,
    lane_rank,
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
        # D-070: a published 2027-28 table does not hold back the 2026-27 one (year in force).
        current = grid(GOOD, year="2026-27")
        assert check_school_year(current, TODAY, published_year="2027-28") == []
        assert check_school_year(older, TODAY, published_year="2027-28")[0].code == "school_year"

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
        rows: list[list[float]] = [[5, 6, 4], [4, 5, 3], [3, 4, 2], [2, 3, 1], [1, 2, 0.5]]
        scaled: list[list[float | None]] = [[x * 10_000 for x in row] for row in rows]
        issues = check_monotonic(grid(scaled))
        reasons = summarize(issues)
        assert len(reasons) == 2
        assert reasons[0].startswith("[monotonic_step]") and "chỗ khác" in reasons[0]


def labelled(labels: list[str], rows: list[list[float]]) -> ScheduleDraft:
    s = grid([list(r) for r in rows])
    s.lanes = [Lane(x) for x in labels]
    return s


class TestLaneRank:
    """D-024: compare lanes by the qualification their labels state, track by track."""

    @pytest.mark.parametrize(
        ("label", "degree", "units", "track"),
        [
            ("BA", 1.0, 0, ""),
            ("BA+30", 1.0, 30, ""),
            ("BA+45 OR MA", 1.0, 45, ""),
            ("BA+75+MA OR MA+30", 2.0, 75, ""),
            ("MA+60+17", 2.0, 77, ""),
            ("BA<45 EMERG", 1.0, None, "EMERG"),
            ("<BA", 0.0, 0, ""),
            ("BA+CRED", 1.0, 0, ""),
            ("BA CRED", 1.0, 0, ""),
            ("BA+98 NON-CRED", 1.0, 98, "NONCRED"),
            ("BA+60 INTERN/ EMERG", 1.0, 60, "INTERNEMERG"),
            ("BA+45 SPED 220 DAYS", 1.0, 45, "SPED220DAYS"),
            ("BA FULL STEP", 1.0, 0, ""),
            ("BA HALF STEP", 1.0, 0, "HALFSTEP"),
            ("BA+75+MA+PHD", 3.0, 75, ""),
            ("Rank II", None, 0, "RANKII"),
            ("NON-CRED", None, 0, "NONCRED"),
            ("Column 3", None, 0, "COLUMN3"),
        ],
    )
    def test_reads_degree_units_and_track(
        self, label: str, degree: float | None, units: int | None, track: str
    ) -> None:
        rank = lane_rank(label)
        assert (rank.degree, rank.units, rank.track) == (degree, units, track)

    def test_dominance(self) -> None:
        assert lane_rank("BA+45").dominates(lane_rank("BA+30"))
        assert lane_rank("PHD").dominates(lane_rank("MA"))
        assert not lane_rank("BA+45").dominates(lane_rank("BA+30+MA"))  # not comparable
        assert not lane_rank("BA+30").dominates(lane_rank("BA+30"))
        assert not lane_rank("BA+CRED").dominates(lane_rank("BA NON-CRED"))  # other track
        # Units counted from different degrees do not compare (Central Union High, J-90).
        assert not lane_rank("BA+75+MA OR MA+30").dominates(lane_rank("MA+60 OR PHD"))
        # "Fewer than 90 units" is not a number of units (Laytonville, J-90).
        assert not lane_rank("BA+60").dominates(lane_rank("BA<90"))
        assert lane_rank("BA").dominates(lane_rank("<BA"))

    def test_tracks_side_by_side_are_not_compared(self) -> None:
        # Los Angeles Unified, J-90 2024-25: the non-credentialed lanes come first and their top
        # lane pays more than the first credentialed lane.
        s = labelled(
            ["BA NON-CRED", "BA+98 NON-CRED", "BA+CRED", "BA+14+CRED"],
            [[60000, 70190, 69304, 70000], [61000, 71190, 70304, 71000]],
        )
        assert check_monotonic(s) == []

    def test_interleaved_ma_lanes_are_not_compared(self) -> None:
        s = labelled(["BA+30", "BA+30+MA", "BA+45", "BA+45+MA"], [[60000, 63188, 62031, 65000]])
        assert check_monotonic(s) == []

    def test_fall_to_a_higher_qualification_is_flagged(self) -> None:
        s = labelled(["BA", "BA+15", "BA+30 OR MA"], [[60000, 62928, 62490]])
        issues = check_monotonic(s)
        assert [i.code for i in issues] == ["monotonic_lane"]
        assert "'BA+15' $62,928.00 → 'BA+30 OR MA' $62,490.00" in issues[0].message
        # Order in the source does not matter once lanes are compared by rank.
        s = labelled(["BA+30 OR MA", "BA", "BA+15"], [[62490, 60000, 62928]])
        assert [i.code for i in check_monotonic(s)] == ["monotonic_lane"]

    def test_unreadable_labels_keep_source_order(self) -> None:
        # Kentucky ranks: no degree to read, so the old rule (source order) applies.
        s = labelled(["Rank V", "Rank IV", "Rank III"], [[31875, 30016, 40000]])
        assert [i.code for i in check_monotonic(s)] == ["monotonic_lane"]

    def test_bare_generic_label_is_flagged(self) -> None:
        # Mobile County: the heading "RANK DR" lost its "DR" when read.
        s = labelled(["RANK B", "RANK A", "RANK AA", "RANK"], [[48552, 52913, 57055, 61195]])
        assert [i.code for i in check_labels(s)] == ["lane_label"]
        s.lanes[3] = Lane("RANK DR")
        assert check_labels(s) == []

    def test_one_salary_column_is_a_name(self) -> None:
        # New York contracts: one salary column, no lanes (D-068).
        assert check_labels(labelled(["Salary"], [[48552]])) == []
        s = labelled(["BA", "Salary"], [[48552, 52913]])
        assert [i.code for i in check_labels(s)] == ["lane_label"]

    def test_rounding_in_the_source_is_not_a_fall(self) -> None:
        # Kentucky, Fayette County 2024-25: Rank II step 38 $91,493.01, step 39 $91,493.00.
        assert check_monotonic(grid([[91493.01], [91493.00]])) == []
        assert check_monotonic(grid([[42153, 42152]])) == []
        assert [i.code for i in check_monotonic(grid([[45963], [45846]]))] == ["monotonic_step"]
