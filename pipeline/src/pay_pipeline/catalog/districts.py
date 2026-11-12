"""Build the district catalogue from one year of NCES CCD files (PLAN Công đoạn 3).

Pure transformation: files in, :class:`Catalog` out. Writing to D1 is in ``d1sql.py``.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pay_pipeline.catalog.ccd import (
    NYC_LEAID,
    NYC_STATE,
    NYC_UNION,
    REGULAR_TYPES,
    STATES,
    DirectoryRow,
    EdgeRow,
    SummaryRow,
    find_file,
    iter_operating,
    read_directory,
    read_edge,
    read_membership,
    read_summary,
)
from pay_pipeline.catalog.neighbors import Neighbor, Point, compute_neighbors
from pay_pipeline.catalog.slugs import SlugInput, assign_slugs, slugify

LEA_TYPE_LABELS = {
    "1": "Regular, not in a supervisory union",
    "2": "Regular, component of a supervisory union",
    "3": "Supervisory union",
    "4": "Service agency",
    "5": "State operated agency",
    "6": "Federal operated agency",
    "7": "Independent charter district",
    "8": "Other local education agency",
    "9": "Specialized public school district",
}
SAMPLE_SIZE = 20


@dataclass(frozen=True)
class District:
    nces_id: str
    name: str
    slug: str
    state: str
    city: str | None
    county: str | None
    county_code: str | None
    website: str | None
    enrollment: int | None
    lat: float | None
    lng: float | None
    lea_type: str


@dataclass
class StateCount:
    in_file: int = 0
    operating: int = 0
    kept: int = 0
    excluded: Counter[str] = field(default_factory=Counter)


@dataclass
class Catalog:
    school_year: str
    states: dict[str, str]
    districts: list[District]
    neighbors: list[Neighbor]
    by_state: dict[str, StateCount]
    out_of_scope: Counter[str]
    disambiguated: list[tuple[str, str, str]]
    summary_title: str
    summary: dict[str, SummaryRow]
    nyc_components: int


def normalize_website(raw: str) -> str | None:
    url = raw.strip()
    if not url or " " in url or "." not in url:
        return None
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    return url


def _exclusion(row: DirectoryRow) -> str | None:
    if row.state == NYC_STATE and row.union == NYC_UNION and row.leaid != NYC_LEAID:
        return "nyc_component"
    if row.leaid == NYC_LEAID:
        return None
    if row.lea_type not in REGULAR_TYPES:
        return f"type_{row.lea_type}"
    return None


def build_catalog(
    sources: Path,
    existing_slugs: Mapping[str, tuple[str, str]],
    summary_file: str = "ccd_*_summary_2.html",
) -> Catalog:
    directory = read_directory(find_file(sources, "ccd_lea_029_*.zip"))
    years = {r.school_year for r in directory}
    if len(years) != 1:
        raise ValueError(f"Tệp danh mục có nhiều năm học: {sorted(years)}")
    school_year = years.pop()

    by_state: dict[str, StateCount] = defaultdict(StateCount)
    out_of_scope: Counter[str] = Counter()
    for r in directory:
        if r.state in STATES:
            by_state[r.state].in_file += 1

    kept: list[DirectoryRow] = []
    nyc_component_ids: set[str] = set()
    for r in iter_operating(directory):
        if r.state not in STATES:
            out_of_scope[r.state] += 1
            continue
        count = by_state[r.state]
        count.operating += 1
        reason = _exclusion(r)
        if reason == "nyc_component":
            nyc_component_ids.add(r.leaid)
        if reason:
            count.excluded[reason] += 1
            continue
        count.kept += 1
        kept.append(r)

    kept_ids = {r.leaid for r in kept}
    membership = read_membership(
        find_file(sources, "ccd_lea_052_*.zip"), kept_ids | nyc_component_ids
    )
    if NYC_LEAID in kept_ids and membership.get(NYC_LEAID) is None and nyc_component_ids:
        parts = [membership.get(i) for i in nyc_component_ids]
        known = [p for p in parts if p is not None]
        membership[NYC_LEAID] = sum(known) if known and len(known) == len(parts) else None

    edge: dict[str, EdgeRow] = read_edge(find_file(sources, "EDGE_GEOCODE_PUBLICLEA_*.zip"))

    slug_result = assign_slugs(
        (
            SlugInput(r.leaid, r.state, r.name, e.county_name if (e := edge.get(r.leaid)) else None)
            for r in kept
        ),
        existing_slugs,
    )

    districts = []
    for r in sorted(kept, key=lambda x: x.leaid):
        e = edge.get(r.leaid)
        districts.append(
            District(
                nces_id=r.leaid,
                name=r.name,
                slug=slug_result.slugs[r.leaid],
                state=r.state,
                city=r.city or None,
                county=e.county_name if e and e.county_name else None,
                county_code=e.county_code if e and e.county_code else None,
                website=normalize_website(r.website),
                enrollment=membership.get(r.leaid),
                lat=e.lat if e else None,
                lng=e.lng if e else None,
                lea_type=r.lea_type,
            )
        )

    neighbors = compute_neighbors(Point(d.nces_id, d.county_code, d.lat, d.lng) for d in districts)

    summary_path = find_file(sources, summary_file.replace("*", school_year_code(school_year)))
    title, summary = read_summary(summary_path)

    return Catalog(
        school_year=school_year,
        states=dict(STATES),
        districts=districts,
        neighbors=neighbors,
        by_state=dict(by_state),
        out_of_scope=out_of_scope,
        disambiguated=slug_result.disambiguated,
        summary_title=title,
        summary=summary,
        nyc_components=len(nyc_component_ids),
    )


def school_year_code(school_year: str) -> str:
    """'2024-2025' -> '202425' (the code in CCD table file names)."""
    start, end = school_year.split("-")
    return f"{start}{end[-2:]}"


def state_slug(name: str) -> str:
    return slugify(name)


def reconcile(catalog: Catalog) -> list[tuple[str, int, int | None, str]]:
    """Per state: (code, operating LEAs in file, NCES table count, explanation of any gap)."""
    out = []
    for code, name in sorted(catalog.states.items()):
        count = catalog.by_state.get(code, StateCount())
        table = catalog.summary.get(name.upper())
        expected = table.operating_districts if table else None
        note = ""
        if expected is None:
            note = "Bảng NCES không có dòng cho bang này"
        elif expected != count.operating:
            gap = count.operating - expected
            nyc = catalog.nyc_components if code == NYC_STATE else 0
            if code == NYC_STATE and gap == nyc:
                note = (
                    f"NCES gộp {nyc} LEA thành viên của NYC thành một LEA "
                    "(chú thích của bảng); khớp sau khi gộp"
                )
            else:
                note = f"Lệch {gap:+d}, chưa giải thích được"
        out.append((code, count.operating, expected, note))
    return out


def sample(catalog: Catalog, size: int = SAMPLE_SIZE) -> list[District]:
    rnd = random.Random(f"sample:{catalog.school_year}")  # noqa: S311 - reproducible sample
    return sorted(
        rnd.sample(catalog.districts, min(size, len(catalog.districts))), key=lambda d: d.nces_id
    )


def render_report(catalog: Catalog, provenance: list[dict[str, str]] | None = None) -> str:
    lines = [
        f"# Danh mục học khu NCES CCD {catalog.school_year}",
        "",
        f"- Học khu giữ lại: **{len(catalog.districts):,}** "
        f'(50 bang + DC, loại 1–2 "regular", đang hoạt động đầu năm học).',
        f"- Cặp học khu lân cận: {len(catalog.neighbors):,}.",
        f"- Bảng đối chiếu: {catalog.summary_title}",
        "",
    ]
    if provenance:
        lines += [
            "## Tệp nguồn",
            "",
            "| Tệp | SHA-256 | Tải lúc | URL |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| {p['name']} | `{p['sha256'][:16]}…` | {p['fetched_at']} | {p['url']} |"
            for p in provenance
        ]
        lines.append("")

    rec = reconcile(catalog)
    unexplained = [r for r in rec if r[3].startswith("Lệch") or r[2] is None]
    lines += [
        "## Đối chiếu số học khu đang hoạt động theo bang",
        "",
        f"Khớp: {sum(1 for r in rec if not r[3])}/{len(rec)} bang; "
        f"lệch có giải thích: {sum(1 for r in rec if r[3] and r not in unexplained)}; "
        f"lệch chưa giải thích: {len(unexplained)}.",
        "",
        "| Bang | Trong tệp (mọi loại) | Bảng NCES | Giữ lại | Loại bỏ | Ghi chú |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for code, operating, expected, note in rec:
        count = catalog.by_state.get(code, StateCount())
        excluded = ", ".join(f"{k} {v}" for k, v in sorted(count.excluded.items()))
        exp = "—" if expected is None else f"{expected:,}"
        lines.append(f"| {code} | {operating:,} | {exp} | {count.kept:,} | {excluded} | {note} |")
    lines += [
        "",
        "Mã loại bỏ: "
        + "; ".join(f"type_{k} = {v}" for k, v in LEA_TYPE_LABELS.items() if k not in REGULAR_TYPES)
        + "; nyc_component = học khu con của NYC, gộp vào NYC Chancellor's Office.",
        "",
    ]
    if catalog.out_of_scope:
        oos = ", ".join(f"{k} {v}" for k, v in sorted(catalog.out_of_scope.items()))
        lines += [f"Ngoài phạm vi (lãnh thổ, BIE), không nhập: {oos}.", ""]

    d = catalog.districts
    neigh_count = Counter(n.district for n in catalog.neighbors)
    lines += [
        "## Độ đầy đủ",
        "",
        f"- Thiếu website: {sum(1 for x in d if not x.website):,}",
        f"- Thiếu sĩ số: {sum(1 for x in d if x.enrollment is None):,}",
        f"- Thiếu tọa độ: {sum(1 for x in d if x.lat is None):,}",
        f"- Thiếu quận: {sum(1 for x in d if not x.county):,}",
        f"- Không có học khu lân cận: {sum(1 for x in d if neigh_count[x.nces_id] == 0):,}",
        f"- Slug trùng: {len(d) - len({(x.state, x.slug) for x in d})}",
        f"- Slug phải thêm hậu tố (quận hoặc mã NCES): {len(catalog.disambiguated):,}",
        "",
        "## 20 học khu ngẫu nhiên để kiểm tra tay",
        "",
        "| NCES ID | Bang | Tên | Thành phố | Website |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {x.nces_id} | {x.state} | {x.name} | {x.city or ''} | {x.website or ''} |"
        for x in sample(catalog)
    ]
    return "\n".join(lines) + "\n"
