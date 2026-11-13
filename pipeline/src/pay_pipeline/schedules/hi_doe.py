"""Hawaii Department of Education: the statewide teacher salary schedule (D-031).

Hawaii is one school district (NCES 1500030, ST_LEAID ``HI-001``), so the state schedule is the
district's own schedule, not a minimum topped up locally. Source: "Teacher's Annual Rate Salary
Schedule (10-Month)", Exhibit E of the HSTA contract, published by HIDOE as a one-page PDF.

The page prints steps from the top (14B) down to the entry step (4), and every amount carries a
pay code such as ``T03-14A`` (class III, step 14A). The reader trusts the codes, not the column
positions: the step numbers in the left margin carry a footnote mark (``95`` = step 9, note 5).
"""

from __future__ import annotations

import re
from pathlib import Path

from pay_pipeline.schedules import ok_sde
from pay_pipeline.schedules.model import Cell, Lane, ScheduleDraft, Step, dollars_to_cents

STATE = "HI"
DISTRICT_ID = "001"
DISTRICT_NAME = "Hawaii Department of Education"

CLASSES = {
    2: ("Class II (BA)", "BA"),
    3: ("Class III (BA+30 or MA)", None),
    4: ("Class IV (Class III + 15 credits)", None),
    5: ("Class V (Class IV + 15 credits)", None),
    6: ("Class VI (Class V + 15 credits)", None),
    7: ("Class VII (Doctorate or Class VI + 15 credits)", None),
    8: ("Class VIII (Class VII + 15 credits)", None),
}
NOTES = (
    "Statewide schedule: Hawaii has one public school district. Step 4 is the entry level for"
    " teachers who have not completed a State Approved Teacher Education Program (SATEP); steps"
    " 5-14B require a SATEP and eligibility for a license."
)

_CODE = re.compile(r"\bT0([2-8])-(\d{2}[AB]?)\s+(\d{1,3}(?:,\d{3})+)\b")
_YEAR = re.compile(r"(\d{4})-(\d{4})\s+School\s+Year", re.IGNORECASE)
_TITLE = re.compile(r"TEACHER'?S\s+ANNUAL\s+RATE\s+SALARY\s+SCHEDULE\s*\(10-MONTH\)", re.IGNORECASE)


def _step_key(step: str) -> tuple[int, str]:
    return int(step[:2]), step[2:]


def read_text(text: str) -> ScheduleDraft | None:
    if not _TITLE.search(text):
        return None
    year = _YEAR.search(text)
    if not year or int(year.group(2)) != int(year.group(1)) + 1:
        return None
    amounts: dict[tuple[str, int], int] = {}
    for cls, step, amount in _CODE.findall(text):
        key = (step, int(cls))
        if key in amounts:
            return None  # one code printed twice: the layout is not the one this reader knows
        amounts[key] = dollars_to_cents(amount)
    steps = sorted({step for step, _ in amounts}, key=_step_key)
    classes = sorted({cls for _, cls in amounts})
    if len(steps) < 5 or classes != sorted(CLASSES):
        return None
    if len(amounts) != len(steps) * len(classes):
        return None  # a missing cell means a misread line; do not guess
    entry_lines = [
        _CODE.search(line) for line in text.splitlines() if "ENTRY LEVEL" in line.upper()
    ]
    entry_step = entry_lines[0].group(2) if entry_lines and entry_lines[0] else None
    labels = [f"Step {int(st[:2])}{st[2:]}" for st in steps]
    if entry_step == steps[0]:
        labels[0] += " (entry level)"
    cells = {
        (i, k): Cell(amounts[(step, cls)])
        for i, step in enumerate(steps)
        for k, cls in enumerate(classes)
    }
    return ScheduleDraft(
        state=STATE,
        state_district_id=DISTRICT_ID,
        district_name=DISTRICT_NAME,
        school_year=f"{year.group(1)}-{year.group(2)[2:]}",
        lanes=[Lane(*CLASSES[cls]) for cls in classes],
        steps=[Step(label) for label in labels],
        cells=cells,
        notes=NOTES,
        source_page=1,
    )


def read_pdf(path: Path) -> list[ScheduleDraft]:
    draft = read_text("\n".join(ok_sde.pages(path)))
    return [draft] if draft else []
