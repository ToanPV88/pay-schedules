"""Import the salary schedules published by state education departments (PLAN Công đoạn 4).

Flow: read each state file (``ca_j90``, ``ky_kde``) -> map the state's district code to the NCES
LEAID through the CCD directory (column ST_LEAID) -> keep districts present and active in the
site catalogue (D1) -> validate -> SQL for D1 (``d1sql``) and a Markdown report.

A schedule that passes every check is published; otherwise it is stored as a draft with its
reasons in ``review_queue``. State files are authoritative history, so a school year older than
the one already published is accepted (D-018).
"""

from __future__ import annotations

import datetime as dt
import json
import random
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from pay_pipeline.catalog.ccd import StateLea, find_file, read_state_ids
from pay_pipeline.schedules import ca_j90, ct_cea, hi_doe, ky_kde, ok_sde, wv_wvde
from pay_pipeline.schedules.model import ScheduleDraft, school_year_from_start, school_year_start
from pay_pipeline.schedules.validate import (
    Issue,
    current_school_year_start,
    start_salary,
    summarize,
    validate,
)

KY_YEARS = 2
"""Kentucky: import the latest N fiscal years of the workbook (California: every J-90 file)."""
CROSS_CHECK_SAMPLE = 10

IMPORTERS = {
    "CA": "ca_j90@1",
    "CT": "ct_cea@1",
    "HI": "hi_doe@1",
    "KY": "ky_kde@1",
    "OK": "ok_sde@1",
    "WV": "wv_wvde@1",
}
# A state file is what each district reported to the state: odd figures (pay falling between two
# steps or lanes, a big change from last year) are published as reported, not held for a person
# (D-028). Holds from a manual cross-check and structural problems still wait for review.
AS_REPORTED = frozenset({"monotonic_step", "monotonic_lane", "start_change"})
STATE_AS_REPORTED = {
    # Connecticut contracts often start the grid above step 1 (frozen or retired lower steps,
    # Bridgeport starts at 6): the book prints every row it has (D-071).
    "CT": frozenset({"step_start"}),
}

STATE_KEY: dict[str, Callable[[str], str | None]] = {
    # 'CA-0161119' -> CDS '0161119'
    "CA": lambda st: st[3:] if re.fullmatch(r"CA-\d{7}", st) else None,
    # 'KY-002005000' -> district number '005' (county 002, district 005)
    "KY": lambda st: st[6:9] if re.fullmatch(r"KY-\d{9}", st) else None,
    # 'OK-72-I001' -> county-district code '72I001'
    "OK": lambda st: st[3:5] + st[6:] if re.fullmatch(r"OK-\d{2}-[A-Z]\d{3}", st) else None,
    # 'HI-001' -> '001' (Hawaii is one statewide district)
    "HI": lambda st: st[3:] if re.fullmatch(r"HI-\d{3}", st) else None,
}
NAME_KEY: dict[str, Callable[[str], str]] = {
    # Books that name districts but print no state code: matched by the CCD name (D-071).
    "CT": ct_cea.district_key,
    "WV": wv_wvde.district_key,
}


@dataclass(frozen=True)
class SourceDocument:
    asset_name: str
    url: str
    sha256: str
    fetched_at: str
    mime: str | None
    release_tag: str
    district_nces: str | None = None
    """Set when the document belongs to one district (PDF pipeline); None for a state file."""


@dataclass(frozen=True)
class RunRecord:
    """One extraction of a source document (``extraction_runs``)."""

    url: str
    sha256: str
    model: str
    prompt_version: str | None
    raw_output: str
    cost_usd_micros: int | None


@dataclass(frozen=True)
class CatalogDistrict:
    nces_id: str
    state: str
    name: str
    active: bool


@dataclass(frozen=True)
class PublishedSchedule:
    nces_id: str
    school_year: str
    schedule_type: str
    title: str
    start_cents: int | None


@dataclass
class Prepared:
    key: int
    draft: ScheduleDraft
    nces_id: str
    catalog_name: str
    source: SourceDocument
    importer: str
    issues: list[Issue]
    confidence: float | None = 1.0
    as_reported: frozenset[str] = frozenset()
    """Checks whose findings do not hold the schedule back: the figures are published as the
    source reported them, and the findings are kept as resolved review rows (D-028)."""

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.code not in self.as_reported]

    @property
    def status(self) -> str:
        return "draft" if self.blocking else "published"

    @property
    def reasons(self) -> list[str]:
        """Open review reasons: every finding, when something holds the schedule back."""
        return summarize(self.issues) if self.blocking else []

    @property
    def accepted_reasons(self) -> list[str]:
        """Findings of a schedule published as reported."""
        return [] if self.blocking else summarize(self.issues)


@dataclass(frozen=True)
class Skipped:
    state: str
    state_district_id: str
    name: str
    school_year: str
    reason: str


@dataclass
class ImportResult:
    sources: list[SourceDocument]
    prepared: list[Prepared]
    skipped: list[Skipped]
    catalog: dict[str, CatalogDistrict]
    states: list[str] = field(default_factory=list)
    runs: list[RunRecord] | None = None
    """Extraction runs to record; None = one summary run per state file."""


def load_manifest_sources(directory: Path, release_tag: str) -> dict[str, SourceDocument]:
    record = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return {
        f["name"]: SourceDocument(
            asset_name=f["name"],
            url=f["url"],
            sha256=f["sha256"],
            fetched_at=f["fetched_at"],
            mime=f.get("content_type"),
            release_tag=release_tag,
        )
        for f in record["files"]
    }


def _wrangler_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Không thấy tệp {path}")
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    rows: list[dict[str, object]] = []
    for item in data if isinstance(data, list) else [data]:
        if isinstance(item, dict) and "results" in item:
            rows.extend(item["results"])
        elif isinstance(item, dict):
            rows.append(item)
    return rows


def load_catalog(path: Path) -> dict[str, CatalogDistrict]:
    """``SELECT nces_id, state, name, active FROM districts`` via ``wrangler d1 execute --json``."""
    out = {}
    for r in _wrangler_rows(path):
        if r.get("nces_id"):
            nces = str(r["nces_id"])
            out[nces] = CatalogDistrict(nces, str(r["state"]), str(r["name"]), bool(r["active"]))
    return out


def load_published(path: Path | None) -> list[PublishedSchedule]:
    if path is None:
        return []
    out = []
    for r in _wrangler_rows(path):
        start = r.get("start_cents")
        out.append(
            PublishedSchedule(
                nces_id=str(r["nces_id"]),
                school_year=str(r["school_year"]),
                schedule_type=str(r["schedule_type"]),
                title=str(r.get("title") or ""),
                start_cents=int(str(start)) if start is not None else None,
            )
        )
    return out


@dataclass(frozen=True)
class Hold:
    """A schedule held for review by a person (e.g. a cross-check found a wrong cell)."""

    state: str
    state_district_id: str
    school_year: str
    reason: str


def load_holds(path: Path | None) -> dict[tuple[str, str, str], str]:
    """``{"holds": [{"state", "state_district_id", "school_year", "reason"}]}`` -> lookup."""
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for h in data.get("holds", []):
        hold = Hold(
            str(h["state"]), str(h["state_district_id"]), str(h["school_year"]), str(h["reason"])
        )
        if not hold.reason.strip():
            raise ValueError(f"Hold thiếu lý do: {h}")
        out[(hold.state, hold.state_district_id, hold.school_year)] = hold.reason
    return out


def read_drafts(
    sources: Path,
    docs: dict[str, SourceDocument],
    work: Path,
    ky_years: int = KY_YEARS,
    runner: ca_j90.Runner = ca_j90.mdb_runner,
) -> list[tuple[ScheduleDraft, SourceDocument]]:
    out: list[tuple[ScheduleDraft, SourceDocument]] = []
    for exe in sorted(sources.glob("j90[0-9][0-9][0-9][0-9].exe")):
        accdb = ca_j90.extract_accdb(exe, work / exe.stem)
        for draft in ca_j90.j90_schedules(ca_j90.read_j90(accdb, runner)):
            out.append((draft, docs[exe.name]))
    for xlsx in sorted(sources.glob("ky_certified_salary_schedule*.xlsx")):
        for sheet in ky_kde.list_sheets(xlsx)[-ky_years:]:
            for draft in ky_kde.read_sheet(xlsx, sheet):
                out.append((draft, docs[xlsx.name]))
    for pdf in sorted(sources.glob("ok_local_salary_schedules_*.pdf")):
        for draft in ok_sde.read_book(pdf):
            out.append((draft, docs[pdf.name]))
    for pdf in sorted(sources.glob("hi_teacher_10_month_*.pdf")):
        for draft in hi_doe.read_pdf(pdf):
            out.append((draft, docs[pdf.name]))
    # Books that print the coming years of multi-year contracts: up to the school year in
    # force (D-070, D-071).
    current = current_school_year_start(dt.datetime.now(dt.UTC).date())
    for pdf in sorted(sources.glob("ct_cea_teacher_salary_schedules_*.pdf")):
        for draft in ct_cea.read_pdf(pdf):
            if school_year_start(draft.school_year) <= current:
                out.append((draft, docs[pdf.name]))
    for pdf in sorted(sources.glob("wv_professional_salary_schedules_*.pdf")):
        for draft in wv_wvde.read_pdf(pdf):
            out.append((draft, docs[pdf.name]))
    return out


def _skip_reason(lea: StateLea | None, catalog: dict[str, CatalogDistrict]) -> str | None:
    if lea is None:
        return "Mã học khu của bang không có trong NCES CCD (ST_LEAID)"
    district = catalog.get(lea.leaid)
    if district is None:
        kind = f"LEA_TYPE {lea.lea_type}" + (f" {lea.lea_type_text}" if lea.lea_type_text else "")
        return f"NCES {lea.leaid} ({kind}) nằm ngoài danh mục học khu của site (D-015)"
    if not district.active:
        return f"NCES {lea.leaid} không còn hoạt động trong danh mục (SY_STATUS {lea.sy_status})"
    return None


def build_import(
    sources: Path,
    ccd_dir: Path,
    catalog: dict[str, CatalogDistrict],
    published: list[PublishedSchedule],
    release_tag: str,
    today: dt.date,
    ky_years: int = KY_YEARS,
    runner: ca_j90.Runner = ca_j90.mdb_runner,
    holds: dict[tuple[str, str, str], str] | None = None,
) -> ImportResult:
    docs = load_manifest_sources(sources, release_tag)
    with tempfile.TemporaryDirectory(prefix="state-import-") as tmp:
        drafts = read_drafts(sources, docs, Path(tmp), ky_years, runner)
    states = sorted({d.state for d, _ in drafts})
    leas = read_state_ids(find_file(ccd_dir, "ccd_lea_029_*.zip"), set(states))
    by_state_key: dict[tuple[str, str], StateLea] = {}
    for state, rows in leas.items():
        for row in rows:
            if state in NAME_KEY:
                key: str | None = NAME_KEY[state](row.name)
                held = by_state_key.get((state, key or ""))
                if held is not None and held.lea_type == "1" and row.lea_type != "1":
                    continue  # a name shared with a charter or agency: the regular district wins
            else:
                key = STATE_KEY[state](row.st_leaid)
            if key is not None:
                by_state_key[(state, key)] = row

    previous: dict[tuple[str, str, str, str], int | None] = {}
    latest_published: dict[tuple[str, str, str], str] = {}
    for p in published:
        previous[(p.nces_id, p.schedule_type, p.title, p.school_year)] = p.start_cents
        k3 = (p.nces_id, p.schedule_type, p.title)
        if k3 not in latest_published or p.school_year > latest_published[k3]:
            latest_published[k3] = p.school_year

    def skip(draft: ScheduleDraft, reason: str) -> None:
        skipped.append(
            Skipped(
                draft.state, draft.state_district_id, draft.district_name, draft.school_year, reason
            )
        )

    def in_catalog(lea: StateLea) -> bool:
        district = catalog.get(lea.leaid)
        return district is not None and district.active

    # Pass 1: the district named by the state code, or, for a supervisory union outside the
    # catalogue (California "common administration" districts, LEA_TYPE 3), its member
    # districts (LEA_TYPE 2, same UNION code): they share one bargaining unit (D-017).
    candidates: list[tuple[ScheduleDraft, SourceDocument, list[StateLea], StateLea | None]] = []
    direct: set[tuple[str, str]] = set()
    skipped: list[Skipped] = []
    for draft, doc in drafts:
        lea = by_state_key.get((draft.state, draft.state_district_id))
        if lea is not None and in_catalog(lea):
            candidates.append((draft, doc, [lea], None))
            direct.add((lea.leaid, draft.school_year))
            continue
        if lea is not None and lea.lea_type == "3" and lea.union:
            members = [
                m
                for m in leas[draft.state]
                if m.union == lea.union and m.lea_type == "2" and in_catalog(m)
            ]
            if members:
                candidates.append((draft, doc, members, lea))
                continue
        skip(draft, _skip_reason(lea, catalog) or "Không có học khu thành viên trong danh mục")

    mapped: list[tuple[ScheduleDraft, SourceDocument, StateLea]] = []
    for draft, doc, targets, union in candidates:
        if union is None:
            mapped.append((draft, doc, targets[0]))
            continue
        own = [m for m in targets if (m.leaid, draft.school_year) not in direct]
        if not own:
            skip(draft, f"Mọi học khu thành viên của NCES {union.leaid} đã có J-90 riêng")
            continue
        note = f"Shared schedule of {union.name} (NCES supervisory union {union.leaid})"
        for member in own:
            notes = f"{draft.notes}; {note}" if draft.notes else note
            mapped.append((replace(draft, notes=notes), doc, member))

    # Two state codes on one NCES district in the same year would publish twice: keep neither.
    counts = Counter((lea.leaid, d.school_year, d.schedule_type, d.title) for d, _, lea in mapped)
    for draft, _doc, lea in mapped:
        if counts[(lea.leaid, draft.school_year, draft.schedule_type, draft.title)] > 1:
            continue
        previous[(lea.leaid, draft.schedule_type, draft.title, draft.school_year)] = start_salary(
            draft
        )

    prepared: list[Prepared] = []
    for draft, doc, lea in mapped:
        k4 = (lea.leaid, draft.school_year, draft.schedule_type, draft.title)
        if counts[k4] > 1:
            skip(draft, f"Nhiều mã của bang cùng trỏ tới NCES {lea.leaid}")
            continue
        prior_year = school_year_from_start(school_year_start(draft.school_year) - 1)
        issues = validate(
            draft,
            today=today,
            previous_start_cents=previous.get(
                (lea.leaid, draft.schedule_type, draft.title, prior_year)
            ),
            published_year=latest_published.get((lea.leaid, draft.schedule_type, draft.title)),
            allow_history=True,
        )
        hold = (holds or {}).get((draft.state, draft.state_district_id, draft.school_year))
        if hold:
            issues.append(Issue("cross_check", hold))
        prepared.append(
            Prepared(
                key=len(prepared) + 1,
                draft=draft,
                nces_id=lea.leaid,
                catalog_name=catalog[lea.leaid].name,
                source=doc,
                importer=IMPORTERS[draft.state],
                issues=issues,
                as_reported=AS_REPORTED | STATE_AS_REPORTED.get(draft.state, frozenset()),
            )
        )
    used = {p.source.asset_name for p in prepared}
    return ImportResult(
        sources=[d for name, d in sorted(docs.items()) if name in used],
        prepared=prepared,
        skipped=skipped,
        catalog=catalog,
        states=states,
    )


# ---------------------------------------------------------------- report


def _pct(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "–"


def cross_check_sample(
    result: ImportResult, state: str, size: int = CROSS_CHECK_SAMPLE
) -> list[Prepared]:
    """Published schedules of the latest year, seeded so the list is stable between runs."""
    latest = max(
        (p.draft.school_year for p in result.prepared if p.draft.state == state), default=""
    )
    pool = sorted(
        (p for p in result.prepared if p.draft.state == state and p.draft.school_year == latest
         and p.status == "published"),
        key=lambda p: p.nces_id,
    )  # fmt: skip
    rng = random.Random(f"cross-check-{state}-{latest}")  # noqa: S311 (repeatable sample)
    return rng.sample(pool, min(size, len(pool)))


def render_report(result: ImportResult) -> str:
    lines = ["# Nhập bảng lương do bang công bố (Công đoạn 4)", ""]
    lines += [
        "## Tệp nguồn",
        "",
        "| Tệp | URL | SHA-256 | Tải lúc | Release |",
        "|---|---|---|---|---|",
    ]
    for s in result.sources:
        lines.append(
            f"| {s.asset_name} | {s.url} | `{s.sha256[:12]}…` | {s.fetched_at} | {s.release_tag} |"
        )
    lines += ["", "## Kết quả theo bang và năm học", ""]
    lines.append(
        "| Bang | Năm học | Học khu trong tệp | Nhập được | Tỉ lệ | Bỏ qua | Bảng ghi vào D1"
        " | Published | Chờ xem tay |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    groups: dict[tuple[str, str], list[Prepared]] = defaultdict(list)
    skipped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for p in result.prepared:
        groups[(p.draft.state, p.draft.school_year)].append(p)
    for k in result.skipped:
        skipped[(k.state, k.school_year)].add(k.state_district_id)
    for key in sorted(set(groups) | set(skipped)):
        ps = groups.get(key, [])
        imported = {p.draft.state_district_id for p in ps}
        dropped = skipped.get(key, set()) - imported
        total = len(imported) + len(dropped)
        pub = sum(p.status == "published" for p in ps)
        lines.append(
            f"| {key[0]} | {key[1]} | {total} | {len(imported)} | {_pct(len(imported), total)}"
            f" | {len(dropped)} | {len(ps)} | {pub} | {len(ps) - pub} |"
        )
    lines += [
        "",
        "Học khu trong tệp và Nhập được đếm theo mã học khu của bang. Một bảng của học khu"
        " hành chính chung (supervisory union) được ghi cho từng học khu thành viên, nên số bảng"
        " ghi vào D1 có thể lớn hơn. Bảng ghi vào D1 gồm bản published và bản draft chờ xem tay.",
        "",
        "## Học khu bỏ qua và lý do",
        "",
    ]
    if result.skipped:
        lines += [
            "| Bang | Năm học | Mã của bang | Tên trong tệp | Lý do |",
            "|---|---|---|---|---|",
        ]
        for k in sorted(
            result.skipped, key=lambda x: (x.state, x.school_year, x.state_district_id)
        ):
            lines.append(
                f"| {k.state} | {k.school_year} | {k.state_district_id} | {k.name} | {k.reason} |"
            )
    else:
        lines.append("Không có.")

    lines += ["", "## Kiểm tra báo lỗi", ""]
    lines.append(
        "Chờ xem tay: bảng bị giữ lại. Published như nguồn: kiểm tra chỉ thấy số lạ của chính"
        " nguồn, bảng vẫn publish và trang web ghi rõ (D-028)."
    )
    lines.append("")
    lines += ["| Bang | Năm học | Kiểm tra | Chờ xem tay | Published như nguồn |"]
    lines += ["|---|---|---|---:|---:|"]
    codes: Counter[tuple[str, str, str, str]] = Counter()
    for p in result.prepared:
        for code in sorted({i.code for i in p.issues}):
            codes[(p.draft.state, p.draft.school_year, code, p.status)] += 1
    keys = sorted({(st, year, code) for st, year, code, _ in codes})
    for st, year, code in keys:
        held, shown = codes[(st, year, code, "draft")], codes[(st, year, code, "published")]
        lines.append(f"| {st} | {year} | {code} | {held} | {shown} |")
    if not keys:
        lines.append("| – | – | – | 0 | 0 |")

    lines += ["", "## Học khu còn thiếu bảng lương ở mỗi bang", ""]
    lines.append(
        "Học khu đang hoạt động trong danh mục của site nhưng không có bảng lương năm mới nhất"
        " từ tệp của bang. Các học khu này chuyển sang pipeline PDF (Công đoạn 5)."
    )
    lines.append("")
    for state in result.states:
        latest = max(
            (p.draft.school_year for p in result.prepared if p.draft.state == state), default=""
        )
        have = {
            p.nces_id
            for p in result.prepared
            if p.draft.state == state and p.draft.school_year == latest
        }
        active = sorted(
            (d for d in result.catalog.values() if d.state == state and d.active),
            key=lambda d: d.name,
        )
        missing = [d for d in active if d.nces_id not in have]
        lines.append(
            f"- **{state}** ({latest}): {len(missing)} / {len(active)} học khu còn thiếu"
            f" ({_pct(len(active) - len(missing), len(active))} đã có)."
        )
        if missing:
            lines += ["", "  <details><summary>Danh sách</summary>", ""]
            lines += [f"  - {d.name} (NCES {d.nces_id})" for d in missing]
            lines += ["", "  </details>", ""]

    lines += ["", "## Mẫu ngẫu nhiên để kiểm tra chéo", ""]
    lines.append(
        "10 học khu mỗi bang (năm mới nhất, bảng published, chọn ngẫu nhiên có seed). Phần lớn"
        " học khu nhỏ không đăng bảng lương công khai, nên kiểm tra chéo dùng thêm học khu có"
        " tài liệu; kết quả ở docs/reports/state-schedules-crosscheck.md."
    )
    lines += [
        "",
        "| Bang | Học khu | NCES | Năm học | Ô đầu tiên | Ô lớn nhất |",
        "|---|---|---|---|---:|---:|",
    ]
    for state in result.states:
        for p in cross_check_sample(result, state):
            amounts = [c.amount_cents for c in p.draft.cells.values() if c.amount_cents is not None]
            start = start_salary(p.draft)
            lines.append(
                f"| {state} | {p.catalog_name} | {p.nces_id} | {p.draft.school_year}"
                f" | {'' if start is None else f'${start / 100:,.0f}'}"
                f" | {f'${max(amounts) / 100:,.0f}' if amounts else ''} |"
            )
    return "\n".join(lines) + "\n"
