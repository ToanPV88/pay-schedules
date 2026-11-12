"""Extract (PLAN Công đoạn 5, bước 4): read a salary schedule from the chosen pages with Claude.

* Only the pages picked by the classifier are sent (cut with pypdf); a scanned PDF sends its
  first pages, which the model reads as images. DOCX/XLSX send their text.
* The model must answer through one tool whose input schema is fixed (``TOOL``), so the output is
  JSON with school_year, contract_days, lanes, steps, cells, stipends, notes.
* Two independent extractions with different models (``PRIMARY``, ``SECONDARY``); validation
  compares them cell by cell (``validate.compare_extractions``).
* The prompt has a version (``PROMPT_VERSION``); the raw answer is kept verbatim for
  ``extraction_runs``.

The API key comes from the ``ANTHROPIC_API_KEY`` environment variable and is never logged.
"""

from __future__ import annotations

import base64
import io
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pypdf

from pay_pipeline.schedules.model import (
    Cell,
    Lane,
    ScheduleDraft,
    Step,
    Stipend,
    dollars_to_cents,
    normalize_lane,
)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
PRIMARY = "claude-sonnet-5-5"
SECONDARY = "claude-haiku-5-5"
PROMPT_VERSION = "p1"
MAX_PAGES = 6
SCANNED_PAGES = 8
MAX_TOKENS = 12000
BLANK_NOTE = "Blank in the source document"

# USD per million tokens (input, output), standard API, from
# https://platform.claude.com/docs/en/about-claude/pricing on 2026-11-12. Used only to report cost.
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5-5": (4.0, 20.0),
}

TOOL: dict[str, Any] = {
    "name": "record_salary_schedule",
    "description": "Record the teacher salary schedule found in the document, exactly as printed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_teacher_salary_schedule": {
                "type": "boolean",
                "description": "True only if the pages contain the base salary schedule (step and"
                " column/lane amounts) for classroom teachers (certificated/certified staff).",
            },
            "reason": {"type": "string", "description": "One sentence: why or why not."},
            "school_year": {
                "type": ["string", "null"],
                "description": "School year the schedule applies to, as YYYY-YY (e.g. 2025-26)."
                " Null if the document does not say.",
            },
            "title": {"type": "string", "description": "Title of the schedule as printed."},
            "contract_days": {"type": ["integer", "null"]},
            "pay_basis": {"type": "string", "enum": ["annual", "monthly", "daily", "hourly"]},
            "lanes": {
                "type": "array",
                "description": "Column headings (education lanes) left to right, verbatim. Empty"
                " if the schedule has steps only.",
                "items": {"type": "string"},
            },
            "steps": {
                "type": "array",
                "description": "Row labels top to bottom, verbatim.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "years_experience": {
                            "type": ["integer", "null"],
                            "description": "Years of experience for this row only if the"
                            " document states it.",
                        },
                    },
                    "required": ["label", "years_experience"],
                },
            },
            "cells": {
                "type": "array",
                "description": "One array per step, one number per lane (or one number when"
                " there are no lanes). Dollars as printed, no rounding. null where the"
                " document has no amount.",
                "items": {"type": "array", "items": {"type": ["number", "null"]}},
            },
            "stipends": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "amount": {"type": ["number", "null"]},
                        "amount_text": {"type": ["string", "null"]},
                        "condition": {"type": ["string", "null"]},
                    },
                    "required": ["name", "amount", "amount_text", "condition"],
                },
            },
            "notes": {"type": ["string", "null"], "description": "Footnotes, verbatim."},
            "source_pages": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Original page numbers holding the schedule.",
            },
            "other_schedules": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Titles of other teacher schedules in the document not recorded.",
            },
        },
        "required": [
            "is_teacher_salary_schedule", "reason", "school_year", "title", "contract_days",
            "pay_basis", "lanes", "steps", "cells", "stipends", "notes", "source_pages",
            "other_schedules",
        ],
    },
}  # fmt: skip

PROMPT = """You are reading pages {pages} of a document published by {district} ({state}), a US \
public school district. Find the base salary schedule for classroom teachers \
(certificated / certified / licensed staff) and record it with the record_salary_schedule tool.

Rules:
- Copy every amount exactly as printed, as a plain number of dollars. Do not round, do not compute.
- Lanes are the columns (education levels such as BA, BA+15, MA, Rank I...), left to right, with \
the heading text as printed. Steps are the rows, top to bottom, with the label as printed.
- cells[i][j] is the amount for step i and lane j. Use null where the table is blank; never copy \
a neighbouring value into a blank.
- If the document holds several teacher schedules (e.g. by number of work days or by \
credential), record the one for regular classroom teachers with the standard work year and \
list the others in other_schedules.
- Ignore schedules for administrators, classified staff, substitutes, coaches or extra duty.
- If there is no teacher salary schedule on these pages, set is_teacher_salary_schedule to false \
and leave lanes, steps and cells empty.
- school_year must be YYYY-YY and only if the document states it (title, header or effective date).
"""


@dataclass
class ExtractionRun:
    model: str
    prompt_version: str
    raw_output: str
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int
    error: str | None = None

    def data(self) -> dict[str, Any] | None:
        if self.error:
            return None
        try:
            value = json.loads(self.raw_output)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def cost_micros(model: str, input_tokens: int, output_tokens: int) -> int:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return round(input_tokens * price_in + output_tokens * price_out)  # $/MTok == µ$/token


def pdf_excerpt(data: bytes, pages: list[int]) -> bytes:
    """A new PDF with only ``pages`` (1-based), in that order."""
    reader = pypdf.PdfReader(io.BytesIO(data))
    writer = pypdf.PdfWriter()
    for p in pages:
        if 1 <= p <= len(reader.pages):
            writer.add_page(reader.pages[p - 1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def pages_to_send(classification: dict[str, Any]) -> list[int]:
    total = int(classification.get("pages_total") or 0)
    if classification.get("scanned"):
        return list(range(1, min(total, SCANNED_PAGES) + 1))
    pages = sorted(int(p) for p in classification.get("schedule_pages") or [])[:MAX_PAGES]
    return pages or list(range(1, min(total, 2) + 1))


def build_content(
    path: Path, kind: str, classification: dict[str, Any], district: str, state: str
) -> tuple[list[dict[str, Any]], list[int]]:
    data = path.read_bytes()
    if kind == "pdf":
        pages = pages_to_send(classification)
        excerpt = pdf_excerpt(data, pages)
        doc = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(excerpt).decode("ascii"),
            },
        }
        label = ", ".join(str(p) for p in pages)
    else:
        from pay_pipeline.documents.classify import document_pages

        text = "\n\f\n".join(document_pages(path, kind))[:150_000]
        doc = {"type": "text", "text": f"<document>\n{text}\n</document>"}
        pages, label = [1], "1 (text of a Word or Excel file)"
    prompt = PROMPT.format(pages=label, district=district, state=state)
    return [doc, {"type": "text", "text": prompt}], pages


def call_claude(
    client: httpx.Client,
    api_key: str,
    model: str,
    content: list[dict[str, Any]],
    *,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> ExtractionRun:
    body = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": TOOL["name"]},
        "messages": [{"role": "user", "content": content}],
    }
    headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}
    last_error = ""
    for attempt in range(retries + 1):
        try:
            response = client.post(API_URL, json=body, headers=headers, timeout=300)
        except httpx.TransportError as exc:
            last_error = f"network: {type(exc).__name__}"
            sleep(10 * (attempt + 1))
            continue
        if response.status_code in (429, 500, 502, 503, 504, 529) and attempt < retries:
            last_error = f"HTTP {response.status_code}"
            retry_after = response.headers.get("retry-after", "")
            sleep(float(retry_after) if retry_after.isdigit() else 15 * (attempt + 1))
            continue
        if response.status_code != 200:
            text = response.text[:300]
            return ExtractionRun(
                model, PROMPT_VERSION, "", 0, 0, 0, f"HTTP {response.status_code}: {text}"
            )
        payload = response.json()
        usage = payload.get("usage", {})
        tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        tool_input = next(
            (b.get("input") for b in payload.get("content", []) if b.get("type") == "tool_use"),
            None,
        )
        if tool_input is None:
            raw = json.dumps(payload)[:20000]
            cost = cost_micros(model, tin, tout)
            return ExtractionRun(
                model, PROMPT_VERSION, raw, tin, tout, cost, "Không có tool_use trong kết quả"
            )
        return ExtractionRun(
            model, PROMPT_VERSION, json.dumps(tool_input, ensure_ascii=False), tin, tout,
            cost_micros(model, tin, tout),
        )  # fmt: skip
    return ExtractionRun(model, PROMPT_VERSION, "", 0, 0, 0, f"Hết số lần thử: {last_error}")


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
