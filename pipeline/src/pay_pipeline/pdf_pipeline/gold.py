"""Gold set (PLAN Công đoạn 5, nghiệm thu): salary schedules entered and checked by hand.

Each ``pipeline/gold/*.json`` names a document (Release asset + URL + sha256), the school year and
the grid (lanes, steps, cells) as printed. ``evaluate`` runs the same classify → read →
validate path as the pipeline on each document and compares the first reading with the gold
grid, cell by cell:

* lanes are matched by label (normalised text, one containing the other), falling back to position
  when both have the same number of lanes; steps likewise;
* only cells with an amount in the gold set count; a cell is right when the extracted amount is
  equal to the cent.

Acceptance (PLAN): over schedules that would be published, ≥ 99 % of gold cells right; no
schedule with a wrong cell is published (it must be stopped by Validate).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pay_pipeline.documents.classify import classify
from pay_pipeline.pdf_pipeline import extract as ex
from pay_pipeline.schedules.model import ScheduleDraft, dollars_to_cents
from pay_pipeline.schedules.validate import Issue, validate


@dataclass(frozen=True)
class Gold:
    id: str
    nces_id: str
    state: str
    district: str
    asset: str
    url: str
    sha256: str
    school_year: str
    lanes: list[str]
    steps: list[str]
    cells: list[list[float | None]]


@dataclass
class GoldResult:
    id: str
    status: str  # published | review | no_schedule | error
    school_year_ok: bool = False
    gold_cells: int = 0
    right_cells: int = 0
    issues: list[str] = field(default_factory=list)
    wrong: list[str] = field(default_factory=list)
    cost_usd_micros: int = 0

    @property
    def accuracy(self) -> float:
        return self.right_cells / self.gold_cells if self.gold_cells else 0.0


def load_gold(directory: Path) -> list[Gold]:
    out = []
    for path in sorted(directory.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        doc = d["document"]
        gold = Gold(
            d["id"], d["nces_id"], d["state"], d["district"], doc["asset"], doc["url"],
            doc["sha256"], d["school_year"], d["lanes"], d["steps"], d["cells"],
        )  # fmt: skip
        widths = {len(r) for r in gold.cells}
        if len(gold.cells) != len(gold.steps) or widths - {len(gold.lanes)}:
            raise ValueError(f"{path.name}: lưới không khớp số bậc/lane")
        out.append(gold)
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+]", "", text.lower())


def _match(gold: list[str], got: list[str]) -> dict[int, int]:
    """gold index -> extracted index: exact label first, then one label containing the other."""
    g, e = [_norm(x) for x in gold], [_norm(x) for x in got]
    out: dict[int, int] = {}
    used: set[int] = set()
    for exact in (True, False):
        for i, a in enumerate(g):
            if i in out or not a:
                continue
            for j, b in enumerate(e):
                if j in used or not b:
                    continue
                if a == b if exact else (a in b or b in a):
                    out[i] = j
                    used.add(j)
                    break
    if len(out) < len(gold) and len(gold) == len(got):
        return {i: i for i in range(len(gold))}
    return out


def compare(gold: Gold, draft: ScheduleDraft) -> tuple[int, int, list[str]]:
    lanes = _match(gold.lanes, [ln.label_raw for ln in draft.lanes])
    steps = _match(gold.steps, [s.label_raw for s in draft.steps])
    total = right = 0
    wrong: list[str] = []
    for i, row in enumerate(gold.cells):
        for j, value in enumerate(row):
            if value is None:
                continue
            total += 1
            si, lj = steps.get(i), lanes.get(j)
            got = None
            if si is not None and (lj is not None or not draft.lanes):
                got = draft.amount(si, lj if draft.lanes else None)
            if got == dollars_to_cents(value):
                right += 1
            elif len(wrong) < 10:
                shown = "–" if got is None else f"{got / 100:,.2f}"
                wrong.append(
                    f"bậc {gold.steps[i]}, {gold.lanes[j]}: chuẩn {value:,.2f}, trích {shown}"
                )
    return total, right, wrong


def evaluate(golds: list[Gold], docs_dir: Path, *, today: dt.date) -> list[GoldResult]:
    from pay_pipeline.pdf_pipeline.run import pdf_checks, read_document

    results = []
    for gold in golds:
        path = docs_dir / gold.asset
        c = classify(path)
        if not c.is_candidate:
            results.append(GoldResult(gold.id, "no_schedule", issues=[c.reason]))
            continue
        data = read_document(path, c.kind, asdict(c))
        if not data[0].get("is_teacher_salary_schedule"):
            results.append(GoldResult(gold.id, "no_schedule", issues=[str(data[0].get("reason"))]))
            continue
        try:
            draft = ex.to_draft(data[0], gold.state, gold.nces_id, gold.district)
            second = None
            if len(data) > 1 and data[1].get("is_teacher_salary_schedule"):
                second = ex.to_draft(data[1], gold.state, gold.nces_id, gold.district)
        except ex.ExtractionError as exc:
            results.append(GoldResult(gold.id, "error", issues=[str(exc)]))
            continue
        if not draft.school_year and c.best_year:
            draft.school_year = c.best_year
        issues: list[Issue] = validate(draft, today=today, second_extraction=second)
        issues += pdf_checks(data[0], draft, today)
        if len(data) > 1 and second is None:
            issues.append(Issue("double_extraction", "Lần đọc thứ hai không thấy bảng"))
        total, right, wrong = compare(gold, draft)
        results.append(
            GoldResult(
                gold.id, "review" if issues else "published",
                school_year_ok=draft.school_year == gold.school_year,
                gold_cells=total, right_cells=right,
                issues=sorted({i.code for i in issues}), wrong=wrong,
            )
        )  # fmt: skip
    return results


def render(results: list[GoldResult]) -> str:
    published = [r for r in results if r.status == "published"]
    gold = sum(r.gold_cells for r in published)
    right = sum(r.right_cells for r in published)
    leaked = [r for r in published if r.right_cells < r.gold_cells or not r.school_year_ok]
    lines = [
        "# Bộ chuẩn: kết quả pipeline PDF",
        "",
        f"- Tài liệu: {len(results)}; sẽ publish: {len(published)}; chờ xem tay:"
        f" {sum(r.status == 'review' for r in results)}; khác: "
        f"{sum(r.status not in ('published', 'review') for r in results)}",
        f"- Ô đúng trên các bảng sẽ publish: {right}/{gold}"
        + (f" ({right / gold:.2%}); ngưỡng PLAN ≥ 99%" if gold else ""),
        f"- Bảng sai mà vẫn qua Validate: {len(leaked)} (ngưỡng PLAN: 0)",
        "",
        "| Bộ chuẩn | Kết quả | Năm học đúng | Ô đúng | Kiểm tra trượt | Ô sai (tối đa 10) |",
        "|---|---|---|---:|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.status} | {'có' if r.school_year_ok else 'không'} |"
            f" {r.right_cells}/{r.gold_cells} | {', '.join(r.issues)} | {'; '.join(r.wrong)} |"
        )
    return "\n".join(lines) + "\n"
