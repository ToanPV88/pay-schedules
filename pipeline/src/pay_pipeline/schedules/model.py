"""A salary schedule as read from a source, before it reaches D1.

The shape mirrors the D1 tables (packages/db/migrations/0002_schema.sql): lanes are columns
(education level), steps are rows (experience), cells hold annual amounts in cents. Indexes in
``cells`` are 0-based positions in ``steps`` and ``lanes``; a schedule without lanes uses
``None`` as the lane index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCHOOL_YEAR_RE = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True)
class Lane:
    label_raw: str
    lane_normalized: str | None = None


@dataclass(frozen=True)
class Step:
    label_raw: str
    years_experience: int | None = None


@dataclass(frozen=True)
class Cell:
    amount_cents: int | None
    note: str | None = None
    """Required when ``amount_cents`` is None; on a filled cell it marks a known exception."""


@dataclass(frozen=True)
class Stipend:
    name: str
    amount_cents: int | None
    amount_raw: str | None = None
    condition: str | None = None


@dataclass
class ScheduleDraft:
    state: str
    state_district_id: str
    """The state's own district code (California CDS, Kentucky district number)."""
    district_name: str
    """District name as written in the source."""
    school_year: str
    lanes: list[Lane]
    steps: list[Step]
    cells: dict[tuple[int, int | None], Cell]
    schedule_type: str = "teacher"
    title: str = ""
    contract_days: int | None = None
    pay_basis: str = "annual"
    notes: str | None = None
    source_sheet: str | None = None
    source_page: int | None = None
    stipends: list[Stipend] = field(default_factory=list)

    def lane_indexes(self) -> list[int | None]:
        return list(range(len(self.lanes))) if self.lanes else [None]

    def amount(self, step: int, lane: int | None) -> int | None:
        cell = self.cells.get((step, lane))
        return cell.amount_cents if cell else None


def school_year_from_start(start: int) -> str:
    return f"{start}-{(start + 1) % 100:02d}"


def school_year_start(school_year: str) -> int:
    match = SCHOOL_YEAR_RE.match(school_year)
    if not match or int(match.group(2)) != (int(match.group(1)) + 1) % 100:
        raise ValueError(f"Năm học không hợp lệ: {school_year!r}")
    return int(match.group(1))


def dollars_to_cents(text: str | float | int) -> int:
    """'48,899.00' / 48899.0 -> 4889900. Rounds half up to the cent."""
    value = float(str(text).replace(",", "").replace("$", "").strip())
    return int(value * 100 + 0.5)


_LANE_SPACE = re.compile(r"\s+")
_LANE_PATTERNS = (
    (re.compile(r"^BA$"), "BA"),
    (re.compile(r"^BA\+(\d{1,3})$"), "BA+{}"),
    (re.compile(r"^MA$"), "MA"),
    (re.compile(r"^MA\+(\d{1,3})$"), "MA+{}"),
    (re.compile(r"^(?:PHD|EDD|DOCTORATE)$"), "PhD"),
)


def normalize_lane(label: str) -> str | None:
    """Map an unambiguous lane label to BA, BA+N, MA, MA+N or PhD; anything else is None.

    Labels such as "BA+45 OR MA" or "BA+60+CRED" stay None: guessing would mislead comparisons.
    """
    text = _LANE_SPACE.sub(" ", label.upper()).strip()
    text = text.replace(".", "")
    text = re.sub(r"\s*\+\s*", "+", text)
    for pattern, template in _LANE_PATTERNS:
        match = pattern.match(text)
        if match:
            return template.format(*match.groups())
    return None
