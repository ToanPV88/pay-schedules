"""Turn an extraction answer (the JSON shape shared by every reader) into a ScheduleDraft.

The answer shape: ``is_teacher_salary_schedule``, ``reason``, ``school_year``, ``title``,
``contract_days``, ``pay_basis``, ``lanes`` (labels), ``steps`` (``label``, ``years_experience``),
``cells`` (one row per step, one amount or null per lane), ``stipends``, ``notes``,
``source_pages``. Readers: ``read.py`` (deterministic, D-022).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pay_pipeline.schedules.model import (
    Cell,
    Lane,
    ScheduleDraft,
    Step,
    Stipend,
    dollars_to_cents,
    normalize_lane,
)

BLANK_NOTE = "Blank in the source document"


@dataclass
class ExtractionRun:
    """One reading of a document, kept verbatim in ``extraction_runs``."""

    model: str
    prompt_version: str | None
    raw_output: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_micros: int = 0
    error: str | None = None

    def data(self) -> dict[str, Any] | None:
        if self.error:
            return None
        try:
            value = json.loads(self.raw_output)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


class ExtractionError(ValueError):
    pass


def to_draft(data: dict[str, Any], state: str, nces_id: str, district: str) -> ScheduleDraft:
    """Turn the tool input into a :class:`ScheduleDraft` (amounts to cents, blanks noted)."""
    lanes_raw = [str(x).strip() for x in data.get("lanes") or []]
    steps_raw = data.get("steps") or []
    cells_raw = data.get("cells") or []
    if len(cells_raw) != len(steps_raw):
        raise ExtractionError(f"{len(cells_raw)} hàng ô nhưng {len(steps_raw)} bậc")
    width = len(lanes_raw) or 1
    cells: dict[tuple[int, int | None], Cell] = {}
    for i, row in enumerate(cells_raw):
        if not isinstance(row, list) or len(row) != width:
            raise ExtractionError(f"Hàng {i + 1} có {len(row) if isinstance(row, list) else '?'}"
                                  f" ô, cần {width}")  # fmt: skip
        for j, value in enumerate(row):
            key = (i, j if lanes_raw else None)
            cells[key] = Cell(None, BLANK_NOTE) if value is None else Cell(dollars_to_cents(value))
    stipends = []
    for s in data.get("stipends") or []:
        amount = s.get("amount")
        text = s.get("amount_text")
        if amount is None and not text:
            continue
        stipends.append(
            Stipend(
                name=str(s.get("name") or "Stipend")[:200],
                amount_cents=None if amount is None else dollars_to_cents(amount),
                amount_raw=None if text is None else str(text)[:200],
                condition=None if s.get("condition") is None else str(s["condition"])[:500],
            )
        )
    pages = [int(p) for p in data.get("source_pages") or [] if isinstance(p, int) and p > 0]
    days = data.get("contract_days")
    return ScheduleDraft(
        state=state,
        state_district_id=nces_id,
        district_name=district,
        school_year=str(data.get("school_year") or ""),
        lanes=[Lane(x, normalize_lane(x)) for x in lanes_raw],
        steps=[
            Step(
                str(s.get("label", "")).strip() or str(i + 1),
                s.get("years_experience") if isinstance(s.get("years_experience"), int) else None,
            )
            for i, s in enumerate(steps_raw)
        ],
        cells=cells,
        title=str(data.get("title") or "")[:300],
        contract_days=days if isinstance(days, int) and 1 <= days <= 366 else None,
        pay_basis=str(data.get("pay_basis") or "annual"),
        notes=None if not data.get("notes") else str(data["notes"])[:4000],
        source_page=min(pages) if pages else None,
        stipends=stipends,
    )
