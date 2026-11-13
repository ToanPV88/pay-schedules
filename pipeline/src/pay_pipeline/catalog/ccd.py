"""Read the NCES Common Core of Data files of one school year (PLAN Công đoạn 3).

Inputs (archived in a GitHub Release by ``fetch-sources``, see pipeline/sources/):

* LEA directory (``ccd_lea_029_*.zip``): one row per local education agency;
* LEA membership (``ccd_lea_052_*.zip``): long format, one row per count;
* EDGE geocode (``EDGE_GEOCODE_PUBLICLEA_*.zip``): office location, county, coordinates;
* CCD summary table 2 (HTML): operating districts per state, used only to reconcile counts.

Column names below were checked on the 2024-25 files (Final Version 1a). A file without one
of the required columns is rejected with the list of columns it does have.
"""

from __future__ import annotations

import csv
import html
import io
import re
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

# The 50 states and DC: PLAN covers public school districts in the United States. Territories
# and the Bureau of Indian Education are outside the scope (DECISIONS.md D-015).
STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}  # fmt: skip

# CCD SY_STATUS: operating at the start of the school year (the definition NCES uses for
# "operating districts" in summary table 2). 2 closed, 6 inactive, 7 future are not operating.
OPERATING_STATUS = frozenset({"1", "3", "4", "5", "8"})

# CCD LEA_TYPE 1 and 2: regular public school districts (2 = component of a supervisory union).
REGULAR_TYPES = frozenset({"1", "2"})

# New York City: NCES reports the member LEAs of the NYC supervisory union (UNION 300) as one LEA
# in its summary tables. Teachers there work under one contract, so the site has one district:
# the NYC Chancellor's Office, and the community districts are folded into it (D-015).
NYC_STATE = "NY"
NYC_UNION = "300"
NYC_LEAID = "3620580"

DIRECTORY_COLUMNS = (
    "SCHOOL_YEAR", "ST", "LEA_NAME", "LEAID", "UNION", "LCITY", "WEBSITE",
    "SY_STATUS", "LEA_TYPE",
)  # fmt: skip
MEMBERSHIP_COLUMNS = ("LEAID", "STUDENT_COUNT", "TOTAL_INDICATOR")
MEMBERSHIP_TOTAL = "Derived - Education Unit Total minus Adult Education Count"
EDGE_COLUMNS = (
    "LEAID", "NAME", "OPSTFIPS", "STREET", "CITY", "STATE", "ZIP", "STFIP", "CNTY", "NMCNTY",
    "LAT", "LON",
)  # fmt: skip


@dataclass(frozen=True)
class DirectoryRow:
    school_year: str
    state: str
    name: str
    leaid: str
    union: str
    city: str
    website: str
    sy_status: str
    lea_type: str


@dataclass(frozen=True)
class EdgeRow:
    leaid: str
    county_code: str
    county_name: str
    lat: float | None
    lng: float | None


@dataclass(frozen=True)
class SummaryRow:
    state_name: str
    operating_districts: int
    membership: int | None


def _member(zf: zipfile.ZipFile, suffix: str) -> str:
    names = [n for n in zf.namelist() if n.lower().endswith(suffix.lower())]
    if len(names) != 1:
        raise ValueError(f"Cần đúng một tệp *{suffix} trong {zf.filename}, thấy: {names}")
    return names[0]


def _require(columns: list[str] | None, required: tuple[str, ...], source: str) -> None:
    missing = [c for c in required if c not in (columns or [])]
    if missing:
        raise ValueError(f"{source} thiếu cột {missing}; có các cột {columns}")


def read_directory(path: Path) -> list[DirectoryRow]:
    with zipfile.ZipFile(path) as zf, zf.open(_member(zf, ".csv")) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        _require(list(reader.fieldnames or []), DIRECTORY_COLUMNS, path.name)
        return [
            DirectoryRow(
                school_year=r["SCHOOL_YEAR"].strip(),
                state=r["ST"].strip(),
                name=r["LEA_NAME"].strip(),
                leaid=r["LEAID"].strip(),
                union=r["UNION"].strip(),
                city=r["LCITY"].strip(),
                website=r["WEBSITE"].strip(),
                sy_status=r["SY_STATUS"].strip(),
                lea_type=r["LEA_TYPE"].strip(),
            )
            for r in reader
        ]


@dataclass(frozen=True)
class SchoolSites:
    """Website hosts of the schools of one LEA (school directory, ``ccd_sch_029_*.zip``)."""

    schools: int
    hosts: Counter[str]


def _host(raw: str) -> str | None:
    url = raw.strip()
    if not url or " " in url or "." not in url:
        return None
    if "://" not in url:
        url = "http://" + url
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.") or None


def read_school_sites(path: Path) -> dict[str, SchoolSites]:
    """LEAID -> number of schools and the website hosts they report (D-035)."""
    counts: dict[str, int] = Counter()
    hosts: dict[str, Counter[str]] = {}
    with zipfile.ZipFile(path) as zf, zf.open(_member(zf, ".csv")) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        _require(list(reader.fieldnames or []), ("LEAID", "WEBSITE"), path.name)
        for r in reader:
            leaid = r["LEAID"].strip()
            counts[leaid] += 1
            host = _host(r["WEBSITE"])
            if host:
                hosts.setdefault(leaid, Counter())[host] += 1
    return {k: SchoolSites(n, hosts.get(k, Counter())) for k, n in counts.items()}


def read_membership(path: Path, leaids: set[str] | None = None) -> dict[str, int | None]:
    """Total students per LEA, excluding adult education (as in CCD summary table 2).

    ``None`` means the state did not report a total for that LEA.
    """
    totals: dict[str, int | None] = {}
    with zipfile.ZipFile(path) as zf, zf.open(_member(zf, ".csv")) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        _require(list(reader.fieldnames or []), MEMBERSHIP_COLUMNS, path.name)
        for r in reader:
            if r["TOTAL_INDICATOR"] != MEMBERSHIP_TOTAL:
                continue
            leaid = r["LEAID"].strip()
            if leaids is not None and leaid not in leaids:
                continue
            count = r["STUDENT_COUNT"].strip()
            totals[leaid] = int(count) if count.isdigit() else None
    return totals


def _float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def read_edge(path: Path) -> dict[str, EdgeRow]:
    """EDGE geocode LEA file: the .TXT inside is pipe-delimited without a header row."""
    with zipfile.ZipFile(path) as zf, zf.open(_member(zf, ".txt")) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        out: dict[str, EdgeRow] = {}
        for fields in csv.reader(text, delimiter="|"):
            if len(fields) < len(EDGE_COLUMNS):
                raise ValueError(
                    f"{path.name}: dòng có {len(fields)} cột, cần ≥ {len(EDGE_COLUMNS)}"
                )
            r = dict(zip(EDGE_COLUMNS, fields, strict=False))
            if r["LEAID"] == "LEAID":  # tolerate a header row in other years
                continue
            lat, lng = _float(r["LAT"]), _float(r["LON"])
            out[r["LEAID"].strip()] = EdgeRow(
                leaid=r["LEAID"].strip(),
                county_code=r["CNTY"].strip(),
                county_name=r["NMCNTY"].strip(),
                lat=lat if lat is not None and -90 <= lat <= 90 else None,
                lng=lng if lng is not None and -180 <= lng <= 180 else None,
            )
        return out


def _cells(row_html: str) -> list[str]:
    cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.S)
    return [html.unescape(re.sub(r"<sup>.*?</sup>|<[^>]+>", "", c)).strip() for c in cells]


def _int(text: str) -> int | None:
    digits = text.replace(",", "")
    return int(digits) if digits.isdigit() else None


def read_summary(path: Path) -> tuple[str, dict[str, SummaryRow]]:
    """CCD data table 2: returns (title, upper-case state name -> row)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r'<p class="title"[^>]*>(.*?)</p>', text, re.S)
    title = html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else ""
    title = " ".join(title.split())
    start, end = text.find("<tbody>"), text.find("</tbody>")
    if start < 0 or end < 0:
        raise ValueError(f"{path.name}: không thấy bảng số liệu")
    rows: dict[str, SummaryRow] = {}
    for row_html in re.findall(r"<tr>(.*?)</tr>", text[start:end], re.S):
        cells = _cells(row_html)
        if len(cells) < 5 or not cells[0]:
            continue
        districts = _int(cells[2])
        if districts is None:
            continue
        rows[cells[0].upper()] = SummaryRow(cells[0], districts, _int(cells[4]))
    if not rows:
        raise ValueError(f"{path.name}: bảng không có dòng nào")
    return title, rows


def find_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"Cần đúng một tệp {pattern} trong {directory}, thấy {matches}")
    return matches[0]


def iter_operating(rows: list[DirectoryRow]) -> Iterator[DirectoryRow]:
    return (r for r in rows if r.sy_status in OPERATING_STATUS)


@dataclass(frozen=True)
class StateLea:
    """A CCD LEA seen from a state's own district code (ST_LEAID, e.g. 'CA-0161119')."""

    leaid: str
    st_leaid: str
    name: str
    lea_type: str
    lea_type_text: str
    sy_status: str
    union: str = ""
    """Supervisory union code shared by a union (LEA_TYPE 3) and its members (LEA_TYPE 2)."""


STATE_ID_COLUMNS = ("ST", "ST_LEAID", "LEAID", "LEA_NAME", "LEA_TYPE", "SY_STATUS", "UNION")


def read_state_ids(path: Path, states: set[str]) -> dict[str, list[StateLea]]:
    """LEAs of ``states`` from the CCD directory, grouped by state code."""
    out: dict[str, list[StateLea]] = {s: [] for s in states}
    with zipfile.ZipFile(path) as zf, zf.open(_member(zf, ".csv")) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        _require(list(reader.fieldnames or []), STATE_ID_COLUMNS, path.name)
        for r in reader:
            st = r["ST"].strip()
            if st in out:
                out[st].append(
                    StateLea(
                        leaid=r["LEAID"].strip(),
                        st_leaid=r["ST_LEAID"].strip(),
                        name=r["LEA_NAME"].strip(),
                        lea_type=r["LEA_TYPE"].strip(),
                        lea_type_text=(r.get("LEA_TYPE_TEXT") or "").strip(),
                        sy_status=r["SY_STATUS"].strip(),
                        union=r["UNION"].strip(),
                    )
                )
    return out
