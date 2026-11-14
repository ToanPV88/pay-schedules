"""OCR reader for scanned salary schedules (D-036).

Free and deterministic (D-022): Poppler's ``pdftoppm`` renders each page, Tesseract reads it and
returns every word with its box. The words are grouped into lines by vertical position and fed to
the same table finder as the text readers (:func:`read.find_tables`), so lanes, steps and checks
work as for any PDF.

Two readings, as for text PDFs: the same page at two resolutions and two page-segmentation modes.
Their digit errors are largely independent, so the shared ``double_extraction`` check (cell by
cell) catches most misread amounts. Pages are first located with a fast low-resolution pass
scored by the classifier's page score, so a 60-page scanned contract costs three careful passes,
not sixty.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import tempfile
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

from pay_pipeline.documents.classify import score_page
from pay_pipeline.pdf_pipeline import read as rd

#: Pages scanned at low resolution to find the schedule pages. Contracts put the schedule in an
#: appendix near the end (Michigan: page 62 of 67), so a long scan keeps its first and last pages.
MAX_SCAN_PAGES = 160
SCAN_HEAD_PAGES = 40
#: Pages read carefully (both readings).
MAX_READ_PAGES = 2
SCAN_DPI = 200
TIMEOUT = 120

_DIGITISH = re.compile(r"^[\$S§]?[\dOolI|,.]+$")
_THOUSANDS_DOT = re.compile(r"^(\$?)(\d{1,3})\.(\d{3})$")


def _render(pdf: Path, page: int, dpi: int, out_dir: Path) -> Path:
    prefix = out_dir / f"p{page}-{dpi}"
    subprocess.run(  # noqa: S603
        ["pdftoppm", "-r", str(dpi), "-gray", "-png", "-singlefile",  # noqa: S607
         "-f", str(page), "-l", str(page), str(pdf), str(prefix)],
        check=True, capture_output=True, timeout=TIMEOUT,
    )  # fmt: skip
    return prefix.with_suffix(".png")


#: Grey level below which a pixel is ink (0 black, 255 white); shading lighter than this is dropped.
INK = 160
#: Runs this many pixels long (at 300 dpi; scaled by resolution) are table rules, not letters.
#: Vertical rules cross whole rows, so they must be longer than the tallest letters.
RULE_ACROSS_PX = 60
RULE_DOWN_PX = 150


def clean(image: Path, dpi: int) -> Path:
    """Black-and-white page without table rules or row shading, which Tesseract misreads.

    Pillow only (no extra dependency). Box-averaging along one axis finds long runs of ink:
    horizontal runs are row rules, vertical runs are column rules; both at once is a filled
    block (a dark header row with white text), which is inverted instead of erased.
    """
    from PIL import Image, ImageChops  # pdfplumber already depends on Pillow

    across_run = max(20, RULE_ACROSS_PX * dpi // 300)
    down_run = max(50, RULE_DOWN_PX * dpi // 300)
    page = Image.open(image).convert("L")
    ink = page.point(lambda v: 0 if v < INK else 255)
    w, h = ink.size

    def rules(size: tuple[int, int]) -> Image.Image:
        small = ink.resize(size, Image.Resampling.BOX)
        # 255 where at least ~75 % of the run is ink
        return small.point(lambda v: 255 if v < 64 else 0).resize((w, h), Image.Resampling.NEAREST)

    across = rules((max(1, w // across_run), h))
    down = rules((w, max(1, h // down_run)))
    block = ImageChops.multiply(across, down)  # 255 only where both: a filled area
    lines = ImageChops.subtract(ImageChops.lighter(across, down), block)
    out = ImageChops.lighter(ink, lines)  # erase rules
    # white text on a dark block -> black on white
    out = Image.composite(ImageChops.invert(out), out, block)
    target = image.with_name(image.stem + "-clean.png")
    out.save(target)
    return target


def _tesseract(image: Path, psm: int) -> list[dict[str, str]]:
    out = subprocess.run(  # noqa: S603
        ["tesseract", str(image), "stdout", "--psm", str(psm),  # noqa: S607
         "-c", "preserve_interword_spaces=1", "tsv"],
        check=True, capture_output=True, timeout=TIMEOUT,
    ).stdout.decode("utf-8", errors="replace")  # fmt: skip
    return list(csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE))


def fix_token(text: str) -> str:
    """Undo the usual OCR slips in amounts: S for $, O for 0, l or I for 1, a dot for a comma."""
    t = text.strip().strip("|[]“”‘’'\"`~«»")
    if re.search(r"\d[,.;:!]+$", t):
        t = t.rstrip(",.;:!")  # "$48,306," — punctuation or a speck after the amount
    if t.endswith(")") and "(" not in t:
        t = t[:-1]  # a table rule read as ")" after the amount
    if re.fullmatch(r"[LlI|]\d", t):
        return "1" + t[1:]  # "L3" is step 13
    if not _DIGITISH.match(t) or not any(c.isdigit() for c in t):
        return t
    if t[0] in "S§":
        t = "$" + t[1:]
    t = t.translate(str.maketrans("OolI|", "00111"))
    m = _THOUSANDS_DOT.match(t)
    if m:  # "45.123" is 45,123: cents have two digits
        t = f"{m.group(1)}{m.group(2)},{m.group(3)}"
    return t


def ocr_lines(rows: list[dict[str, str]]) -> list[rd.Line]:
    """Tesseract TSV words -> lines grouped by vertical position, x in pixels."""
    words = []
    for r in rows:
        text = (r.get("text") or "").strip()
        if r.get("level") != "5" or not text:
            continue
        try:
            conf = float(r.get("conf") or -1)
            left, top = float(r["left"]), float(r["top"])
            width, height = float(r["width"]), float(r["height"])
        except (KeyError, ValueError):
            continue
        if conf < 0:
            continue
        token = fix_token(text)
        if not any(c.isalnum() for c in token):
            continue  # table rules and specks read as "|", "~", "‘"
        words.append((top, height, rd.Word(token, left, left + width)))
    words.sort(key=lambda w: w[0])
    lines: list[rd.Line] = []
    line_top: float | None = None
    reach = 0.0
    for top, height, word in words:
        if line_top is None or top - line_top > reach:
            lines.append(rd.Line([]))
            line_top = top
            reach = max(4.0, 0.5 * height)
        lines[-1].words.append(word)
    for line in lines:
        line.words = sorted(line.words, key=lambda w: w.x0)
    return fill_step_labels(repair_step_labels(lift_step_labels(lines)))


_STEP = re.compile(r"^\d{1,2}$")
MIN_ROW_AMOUNTS = 3


def _row_kind(line: rd.Line) -> tuple[str, int | None]:
    words = line.words
    amounts = [w for w in words if rd.money(w.text) is not None]
    if len(amounts) < MIN_ROW_AMOUNTS or not words:
        return "other", None
    first = words[0]
    if _STEP.match(first.text) and rd.money(first.text) is None and first.x1 <= amounts[0].x0:
        return "label", int(first.text)
    if rd.money(first.text) is not None:
        return "bare", None
    return "other", None


_JUNK = re.compile(r"^[^\d]{1,3}$")
#: Lines looked back over for a step number printed above its row.
LIFT_REACH = 3


def lift_step_labels(lines: list[rd.Line]) -> list[rd.Line]:
    """Join a step number printed at the top of a tall cell to the amounts at its bottom.

    Waterford (MI) prints "1" on one text line and "$43,992 $45,221 …" on the next. A row of
    amounts with nothing before it takes the nearest step number above it, looking past specks
    ("oe", "~") but not past another row of amounts. Specks before the first amount ("iz") go.
    """
    out = [rd.Line(list(ln.words)) for ln in lines]
    used: set[int] = set()
    for i, line in enumerate(out):
        words = line.words
        amounts = [w for w in words if rd.money(w.text) is not None]
        if len(amounts) < MIN_ROW_AMOUNTS:
            continue
        lead = words[: words.index(amounts[0])]
        if not all(_JUNK.match(w.text) for w in lead):
            continue
        for k in range(i - 1, max(-1, i - 1 - LIFT_REACH), -1):
            if k in used:
                break
            above = out[k].words
            if sum(rd.money(w.text) is not None for w in above) >= MIN_ROW_AMOUNTS:
                break
            steps = [w for w in above if _STEP.match(w.text) and w.x1 <= amounts[0].x0]
            if steps:
                if len(steps) == len([w for w in above if not _JUNK.match(w.text)]):
                    line.words = [steps[-1], *words[len(lead) :]]
                    out[k] = rd.Line([])
                    used.add(k)
                break
    return [ln for ln in out if ln.words]


def repair_step_labels(lines: list[rd.Line]) -> list[rd.Line]:
    """Fix a step number OCR misread inside a run of rows that count up by one.

    "10, 1, 12" becomes "10, 11, 12" (a dropped digit), and a last row that goes backwards after
    two rows counting up ("13, 14, 7") becomes the next step. Any other break is left alone: steps
    can jump on purpose (longevity rows). Only rows of amounts led by a number are looked at.
    """
    out = [rd.Line(list(ln.words)) for ln in lines]
    kinds = [_row_kind(ln) for ln in out]

    def relabel(k: int, n: int) -> None:
        w = out[k].words[0]
        out[k].words[0] = rd.Word(str(n), w.x0, w.x1)

    # Rows of amounts in page order; specks between them ("oe") do not break the run.
    run = [k for k in range(len(out)) if kinds[k][0] == "label"]
    for a, b, c in zip(run, run[1:], run[2:], strict=False):
        la, lb, lc = kinds[a][1], kinds[b][1], kinds[c][1]
        if la is not None and lb is not None and lc is not None and lc == la + 2 and lb != la + 1:
            relabel(b, la + 1)
            kinds[b] = ("label", la + 1)
    if len(run) >= 3:
        a, b, c = run[-3:]
        la, lb, lc = kinds[a][1], kinds[b][1], kinds[c][1]
        if la is not None and lb is not None and lc is not None and lb == la + 1 and lc <= lb:
            relabel(c, lb + 1)
            kinds[c] = ("label", lb + 1)
    return out


def fill_step_labels(lines: list[rd.Line]) -> list[rd.Line]:
    """Put back step numbers OCR dropped (a lone "1" in a wide cell is often missed).

    Only inside a run of table rows, and only where the labels around a gap leave no doubt: the
    gap between step a and step b spans exactly b − a − 1 rows. Rows above the first label get
    numbers only when the first two labels count up by one per row.
    """
    kinds = [_row_kind(ln) for ln in lines]
    out = [rd.Line(list(ln.words)) for ln in lines]
    i = 0
    while i < len(lines):
        if kinds[i][0] == "other":
            i += 1
            continue
        j = i
        while j < len(lines) and kinds[j][0] != "other":
            j += 1
        labelled = [(k, kinds[k][1]) for k in range(i, j) if kinds[k][0] == "label"]
        xs = sorted(lines[k].words[0].x0 for k, _ in labelled)
        x = xs[len(xs) // 2] if xs else 0.0

        def put(k: int, n: int, x: float = x) -> None:
            if n >= 0:
                out[k].words.insert(0, rd.Word(str(n), x, x + 1.0))

        for (a_i, a), (b_i, b) in pairwise(labelled):
            if a is not None and b is not None and b - a == b_i - a_i:
                for k in range(a_i + 1, b_i):
                    put(k, a + (k - a_i))
        if len(labelled) >= 2:
            (f_i, f), (s_i, sv) = labelled[0], labelled[1]
            if f is not None and sv is not None and sv - f == s_i - f_i:
                for k in range(i, f_i):
                    if kinds[k][0] == "bare":
                        put(k, f - (f_i - k))
        i = j
    return out


def page_count(pdf: Path) -> int:
    out = subprocess.run(  # noqa: S603
        ["pdfinfo", str(pdf)],  # noqa: S607
        capture_output=True,
        timeout=TIMEOUT,
        check=True,
    ).stdout.decode("utf-8", errors="replace")
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    return int(m.group(1)) if m else 0


def scan_order(pages: int) -> list[int]:
    """Pages to scan: all of them, or the first SCAN_HEAD_PAGES and the last ones up to the cap."""
    if pages <= MAX_SCAN_PAGES:
        return list(range(1, pages + 1))
    tail = MAX_SCAN_PAGES - SCAN_HEAD_PAGES
    return list(range(1, SCAN_HEAD_PAGES + 1)) + list(range(pages - tail + 1, pages + 1))


def schedule_pages(pdf: Path, tmp: Path, pages: int) -> list[int]:
    """Pages most like a salary schedule, from a fast low-resolution pass."""
    scores = []
    for p in scan_order(pages):
        lines = ocr_lines(_tesseract(clean(_render(pdf, p, SCAN_DPI, tmp), SCAN_DPI), 6))
        s = score_page("\n".join(ln.text for ln in lines), p)
        if s.amounts >= 12:
            scores.append(s)
    # As the classifier: teacher schedule pages first, then other schedule-like pages.
    scores.sort(key=lambda s: (-(s.is_schedule and s.teacher and s.negative <= 2),
                               -s.is_schedule, -s.score))  # fmt: skip
    if scores and scores[0].is_schedule and scores[0].teacher and scores[0].negative <= 2:
        # A clear teacher schedule page: read it alone, so a fuller table on a page for other
        # staff (classified, administrators) cannot win the table choice.
        return [scores[0].page]
    return [s.page for s in scores[:MAX_READ_PAGES]]


#: OCR settings tried in turn: (reader, dpi, page segmentation mode, clean the image first).
CONFIGS = (
    ("tesseract-psm6-300dpi-clean@2", 300, 6, True),
    ("tesseract-psm4-300dpi-clean@2", 300, 4, True),
    ("tesseract-psm6-300dpi@2", 300, 6, False),
    ("tesseract-psm4-300dpi@2", 300, 4, False),
    ("tesseract-psm6-400dpi-clean@2", 400, 6, True),
    ("tesseract-psm4-400dpi-clean@2", 400, 4, True),
)
READERS = frozenset(c[0] for c in CONFIGS)


def _cells(answer: dict[str, Any]) -> int:
    if not answer.get("is_teacher_salary_schedule"):
        return 0
    return sum(v is not None for row in answer.get("cells") or [] for v in row)


def same_grid(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two readings agree on every amount (and on which cells are empty)."""
    if not (_cells(a) and _cells(b)):
        return False
    ca, cb = a["cells"], b["cells"]
    if len(ca) != len(cb) or any(len(x) != len(y) for x, y in zip(ca, cb, strict=True)):
        return False
    return all(
        (x is None) == (y is None) and (x is None or abs(x - y) < 0.005)
        for ra, rb in zip(ca, cb, strict=True)
        for x, y in zip(ra, rb, strict=True)
    )


#: OCR readings that must read exactly the same grid before the table can be published (D-036).
#: Two readings of one engine share some mistakes (a dropped row, a misread digit), so two
#: matching readings only send the table to review.
AGREE_TO_PUBLISH = 3
#: Longest lane label accepted from a scan without review.
MAX_LANE_LABEL = 30


def vote(answers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One grid from several OCR readings, cell by cell (D-057).

    Readings of the same page with the most common lane count are lined up by step label. A step
    is kept when AGREE_TO_PUBLISH readings have it; each cell takes the amount most readings
    agree on, which must have AGREE_TO_PUBLISH votes and more votes than any other amount. The
    reading with the most rows gives the labels and their order, and each of its rows must be
    kept. Returns None when any of that fails; the answer's
    ``ocr_agree`` is the smallest winning vote, so a weak cell still holds the table for review.
    """
    full = [a for a in answers if _cells(a)]
    if len(full) < AGREE_TO_PUBLISH:
        return None
    # Readings of one page with one lane count: a reading of another page is another table.
    shape = Counter(
        (tuple(a.get("source_pages") or ()), len(a["lanes"])) for a in full
    ).most_common(1)[0][0]
    full = [a for a in full if (tuple(a.get("source_pages") or ()), len(a["lanes"])) == shape]
    lanes = shape[1]
    if len(full) < AGREE_TO_PUBLISH:
        return None
    rows = [
        {st["label"]: row for st, row in zip(a["steps"], a["cells"], strict=False)} for a in full
    ]
    seen = Counter(label for r in rows for label in r)
    keep = {label for label, n in seen.items() if n >= AGREE_TO_PUBLISH}
    base_i = max(range(len(full)), key=lambda i: len(rows[i]))
    base = full[base_i]
    order = [st["label"] for st in base["steps"]]
    # Every row of the fullest reading must be confirmed: a row only some readings saw (often
    # the last) is never dropped to make the vote pass.
    if not order or set(order) != keep or len(order) != len(set(order)):
        return None
    cells: list[list[float | None]] = []
    weakest = len(full)
    for label in order:
        row: list[float | None] = []
        for j in range(lanes):
            votes = Counter(
                None if r[label][j] is None else round(float(r[label][j]), 2)
                for r in rows
                if label in r and j < len(r[label])
            ).most_common(2)
            top, n = votes[0]
            if n < AGREE_TO_PUBLISH or (len(votes) > 1 and votes[1][1] >= n):
                return None
            weakest = min(weakest, n)
            row.append(top)
        cells.append(row)
    years = Counter(a.get("school_year") for a in full if a.get("school_year")).most_common(1)
    steps = {st["label"]: st for st in base["steps"]}
    out = dict(base)
    out.update(
        cells=cells,
        steps=[steps[label] for label in order],
        school_year=years[0][0] if years else base.get("school_year"),
        ocr_agree=weakest,
        ocr_vote=len(full),
    )
    return out


def read_scanned(pdf: Path) -> list[dict[str, Any]]:
    """Two OCR readings of a scanned PDF, in the shared answer shape (D-036).

    OCR settings are tried in turn until AGREE_TO_PUBLISH of them read exactly the same grid; two
    of that group are returned, so the shared ``double_extraction`` check passes. ``ocr_agree`` on
    the first answer says how many readings matched; :func:`run.pdf_checks` holds the table for
    review below AGREE_TO_PUBLISH. With no matching pair, the two fullest readings are returned and
    the double-extraction check sends the table to review.
    """
    answers: list[dict[str, Any]] = []
    groups: list[list[dict[str, Any]]] = []
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            pages = schedule_pages(pdf, tmp, page_count(pdf))
            if not pages:
                reason = "PDF dạng ảnh quét: OCR không thấy trang bảng lương"
                return [rd.to_answer(None, "", CONFIGS[0][0], reason)]
            for reader, dpi, psm, cleaned in CONFIGS:
                read = []
                for p in pages:
                    image = _render(pdf, p, dpi, tmp)
                    read.append(ocr_lines(_tesseract(clean(image, dpi) if cleaned else image, psm)))
                # read_pages numbers pages from 1 in the order given.
                answer = rd.read_pages(read, list(range(1, len(read) + 1)), reader)
                if answer.get("source_pages"):
                    answer["source_pages"] = [pages[int(i) - 1] for i in answer["source_pages"]]
                answers.append(answer)
                if not _cells(answer):
                    continue
                group = next((g for g in groups if same_grid(g[0], answer)), None)
                if group is None:
                    groups.append([answer])
                    continue
                group.append(answer)
                if len(group) >= AGREE_TO_PUBLISH:
                    break
    except (subprocess.SubprocessError, OSError) as exc:
        reason = f"OCR lỗi: {type(exc).__name__}"[:200]
        return [rd.to_answer(None, "", CONFIGS[0][0], reason)]
    best = max(groups, key=len, default=[])
    if len(best) < AGREE_TO_PUBLISH:
        voted = vote(answers)
        if voted is not None:
            return [voted, dict(voted)]
    if len(best) >= 2:
        best[0]["ocr_agree"] = len(best)
        return best[:2]
    answers.sort(key=lambda a: -_cells(a))
    for a in answers:
        a["ocr_agree"] = 1
    return answers[:2]
