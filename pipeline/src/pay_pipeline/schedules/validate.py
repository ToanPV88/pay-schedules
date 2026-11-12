"""Automatic checks run before a schedule may be published (PLAN Công đoạn 5, bước Validate).

Every check returns a list of :class:`Issue`; an empty list from :func:`validate` means the
schedule may be published. Any issue sends it to ``review_queue`` with the issue messages as
reasons. The checks:

1. ``monotonic_step``: within a lane, pay never falls as the step rises;
   ``monotonic_lane``: at a step, pay never falls from one lane to the next (lanes are in
   source order, lowest qualification first). A cell carrying a note is an accepted exception.
2. ``cell_count``: every step × lane has a cell; a blank cell must carry a note.
3. ``range``: every amount is plausible for the pay basis (annual pay is not hourly or daily).
4. ``school_year``: readable, not after next school year, and (unless the source is an
   authoritative history, D-018) not older than the schedule already published.
5. ``double_extraction``: two independent extractions agree cell by cell
   (:func:`compare_extractions`; not applicable to deterministic state files).
6. ``start_change``: starting pay moved more than 20 % against the previous school year.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from pay_pipeline.schedules.model import ScheduleDraft, school_year_start

# Plausible amounts per pay basis, in cents. Annual: below any state minimum for a full-time
# teacher is not an annual figure (an hourly or daily rate slipped in); above any known
# district maximum needs a human look.
RANGES: dict[str, tuple[int, int]] = {
    "annual": (15_000_00, 300_000_00),
    "monthly": (1_250_00, 30_000_00),
    "daily": (75_00, 1_500_00),
    "hourly": (10_00, 250_00),
}
START_CHANGE_LIMIT = 0.20


@dataclass(frozen=True)
class Issue:
    code: str
    message: str


def _fmt(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def check_monotonic(s: ScheduleDraft) -> list[Issue]:
    issues: list[Issue] = []
    lanes = s.lane_indexes()
    for lane in lanes:
        prev: tuple[int, int] | None = None
        for step in range(len(s.steps)):
            cell = s.cells.get((step, lane))
            if cell is None or cell.amount_cents is None:
                continue
            if prev is not None and cell.amount_cents < prev[1] and not cell.note:
                where = s.lanes[lane].label_raw if lane is not None else "(no lane)"
                issues.append(
                    Issue(
                        "monotonic_step",
                        f"Lương giảm khi tăng bậc: lane {where!r}, bậc"
                        f" {s.steps[prev[0]].label_raw} {_fmt(prev[1])}"
                        f" → bậc {s.steps[step].label_raw} {_fmt(cell.amount_cents)}",
                    )
                )
            prev = (step, cell.amount_cents)
    if s.lanes:
        for step in range(len(s.steps)):
            prev = None
            for lane in range(len(s.lanes)):
                cell = s.cells.get((step, lane))
                if cell is None or cell.amount_cents is None:
                    continue
                if prev is not None and cell.amount_cents < prev[1] and not cell.note:
                    issues.append(
                        Issue(
                            "monotonic_lane",
                            f"Lương giảm khi sang lane cao hơn: bậc {s.steps[step].label_raw},"
                            f" {s.lanes[prev[0]].label_raw!r} {_fmt(prev[1])}"
                            f" → {s.lanes[lane].label_raw!r} {_fmt(cell.amount_cents)}",
                        )
                    )
                prev = (lane, cell.amount_cents)
    return issues


def check_cell_count(s: ScheduleDraft) -> list[Issue]:
    issues: list[Issue] = []
    if not s.steps:
        return [Issue("cell_count", "Bảng không có bậc nào")]
    expected = {(st, ln) for st in range(len(s.steps)) for ln in s.lane_indexes()}
    missing = expected - set(s.cells)
    extra = set(s.cells) - expected
    unmarked = [k for k, c in s.cells.items() if c.amount_cents is None and not c.note]
    if missing:
        issues.append(
            Issue("cell_count", f"Thiếu {len(missing)} ô trên {len(expected)} (bậc × lane)")
        )
    if extra:
        issues.append(Issue("cell_count", f"{len(extra)} ô nằm ngoài lưới bậc × lane"))
    if unmarked:
        issues.append(Issue("cell_count", f"{len(unmarked)} ô trống không có ghi chú"))
    if all(c.amount_cents is None for c in s.cells.values()):
        issues.append(Issue("cell_count", "Bảng không có ô nào có số tiền"))
    return issues


def check_range(s: ScheduleDraft) -> list[Issue]:
    low, high = RANGES[s.pay_basis]
    amounts = [c.amount_cents for c in s.cells.values() if c.amount_cents is not None]
    out = [a for a in amounts if not low <= a <= high]
    if not out:
        return []
    return [
        Issue(
            "range",
            f"{len(out)} ô ngoài khoảng hợp lý cho lương {s.pay_basis}"
            f" ({_fmt(low)}–{_fmt(high)}), vd. {_fmt(min(out))} / {_fmt(max(out))}",
        )
    ]


def current_school_year_start(today: dt.date) -> int:
    """School years start on 1 July (the fiscal year used by state finance offices)."""
    return today.year if today.month >= 7 else today.year - 1


def check_school_year(
    s: ScheduleDraft,
    today: dt.date,
    published_year: str | None = None,
    allow_history: bool = False,
) -> list[Issue]:
    try:
        start = school_year_start(s.school_year)
    except ValueError as exc:
        return [Issue("school_year", str(exc))]
    issues = []
    if start > current_school_year_start(today) + 1:
        issues.append(Issue("school_year", f"Năm học {s.school_year} ở quá xa trong tương lai"))
    if published_year and not allow_history and start < school_year_start(published_year):
        issues.append(
            Issue(
                "school_year",
                f"Năm học {s.school_year} cũ hơn bảng đang published ({published_year})",
            )
        )
    return issues


def start_salary(s: ScheduleDraft) -> int | None:
    """Pay at the first step, in the lowest lane that has an amount there."""
    if not s.steps:
        return None
    for lane in s.lane_indexes():
        amount = s.amount(0, lane)
        if amount is not None:
            return amount
    return None


def check_start_change(s: ScheduleDraft, previous_start_cents: int | None) -> list[Issue]:
    current = start_salary(s)
    if current is None or not previous_start_cents:
        return []
    change = (current - previous_start_cents) / previous_start_cents
    if abs(change) <= START_CHANGE_LIMIT:
        return []
    return [
        Issue(
            "start_change",
            f"Lương khởi điểm đổi {change:+.1%} so với năm trước"
            f" ({_fmt(previous_start_cents)} → {_fmt(current)})",
        )
    ]


def compare_extractions(a: ScheduleDraft, b: ScheduleDraft) -> list[Issue]:
    """Cell-by-cell agreement of two independent extractions of the same document."""
    issues: list[Issue] = []
    if a.school_year != b.school_year:
        issues.append(
            Issue("double_extraction", f"Năm học lệch: {a.school_year} / {b.school_year}")
        )
    if [x.label_raw for x in a.lanes] != [x.label_raw for x in b.lanes] or len(a.steps) != len(
        b.steps
    ):
        issues.append(Issue("double_extraction", "Hai lần trích ra lưới bậc × lane khác nhau"))
        return issues
    differ = [k for k in set(a.cells) | set(b.cells) if a.cells.get(k) != b.cells.get(k)]
    if differ:
        issues.append(Issue("double_extraction", f"{len(differ)} ô lệch giữa hai lần trích"))
    return issues


def validate(
    s: ScheduleDraft,
    *,
    today: dt.date,
    previous_start_cents: int | None = None,
    published_year: str | None = None,
    allow_history: bool = False,
    second_extraction: ScheduleDraft | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    issues += check_cell_count(s)
    issues += check_monotonic(s)
    issues += check_range(s)
    issues += check_school_year(s, today, published_year, allow_history)
    issues += check_start_change(s, previous_start_cents)
    if second_extraction is not None:
        issues += compare_extractions(s, second_extraction)
    return issues


def summarize(issues: Iterable[Issue], limit: int = 3) -> list[str]:
    """One review reason per check: the first ``limit`` messages and how many more there are."""
    by_code: dict[str, list[str]] = {}
    for issue in issues:
        by_code.setdefault(issue.code, []).append(issue.message)
    reasons = []
    for code, messages in by_code.items():
        text = "; ".join(messages[:limit])
        if len(messages) > limit:
            text += f" (và {len(messages) - limit} chỗ khác)"
        reasons.append(f"[{code}] {text}")
    return reasons
