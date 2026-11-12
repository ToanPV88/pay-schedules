/** Các khối hiển thị một bảng lương: bảng, máy tính, phụ cấp và ghi chú, nguồn. */
import type { Cell, Schedule } from "@pay-schedules/db";
import { html, raw } from "hono/html";
import { type Calculation, calculate } from "../calc";
import { formatCents, formatDate, hostOf, payBasisNoun, safeHttpUrl, stepLabel } from "../format";
import type { Html } from "./layout";

// ---------------------------------------------------------------- bảng

function cellHtml(scheduleId: number, cell: Cell | null, footnotes: string[]): Html {
  if (!cell) {
    return html`<td class="empty"><span class="visually-hidden">Not in the source</span></td>`;
  }
  if (cell.amountCents === null) {
    footnotes.push(cell.note ?? "");
    const n = footnotes.length;
    const href = `#s${scheduleId}-note-${n}`;
    return html`<td class="empty">—<sup><a href="${href}" aria-label="Note ${n}">${n}</a></sup></td>`;
  }
  return html`<td data-cents="${cell.amountCents}">${formatCents(cell.amountCents)}</td>`;
}

/**
 * Bảng lương đầy đủ bằng thẻ table thật: đọc được khi tắt JavaScript. Ô có số mang `data-cents`
 * để `site.js` tính tại chỗ; ô trống kèm chú thích đánh số bên dưới bảng.
 */
export function scheduleTable(schedule: Schedule, caption: string): Html {
  const footnotes: string[] = [];
  const head: Html[] = [];
  if (schedule.lanes.length === 0) {
    head.push(html`<th scope="col">Salary</th>`);
  }
  for (const lane of schedule.lanes) {
    head.push(html`<th scope="col">${lane.labelRaw}</th>`);
  }
  const rows: Html[] = [];
  for (const [i, step] of schedule.steps.entries()) {
    const cells: Html[] = [];
    for (const cell of schedule.cells[i] ?? []) {
      cells.push(cellHtml(schedule.id, cell, footnotes));
    }
    rows.push(html`<tr><th scope="row">${step.labelRaw}</th>${cells}</tr>\n`);
  }
  const notes: Html[] = [];
  for (const [k, note] of footnotes.entries()) {
    notes.push(html`<li id="s${schedule.id}-note-${k + 1}">${note}</li>`);
  }
  const noteList = notes.length > 0 ? html`<ol class="notes">${notes}</ol>` : html``;
  const days = schedule.contractDays ?? "";
  return html`<div class="table-scroll" role="region" aria-label="${caption}" tabindex="0">
<table class="schedule" id="schedule-${schedule.id}" data-days="${days}" data-basis="${schedule.payBasis}">
<caption>${caption}</caption>
<thead>
<tr><th scope="col">Step</th>${head}</tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>
${noteList}`;
}

// ---------------------------------------------------------------- máy tính

export interface CalculationText {
  amount: string;
  perDay: string;
  raise: string;
}

/** Ba dòng kết quả. Câu chữ phải khớp với `public/site.js`. */
export function calculationText(schedule: Schedule, result: Calculation | null): CalculationText {
  if (!result || result.amountCents === null) {
    const raise = result?.isTopStep ? "Top step of this schedule" : "—";
    return { amount: "No amount listed for this step and lane", perDay: "—", raise };
  }
  const amount = `${formatCents(result.amountCents)} ${payBasisNoun(schedule.payBasis)}`;
  let perDay = "—";
  if (result.perDayCents !== null) {
    perDay = `${formatCents(result.perDayCents)} (${schedule.contractDays} contract days)`;
  } else if (schedule.payBasis === "annual") {
    perDay = "Not available: the source does not state contract days";
  }
  let raise = "—";
  if (result.isTopStep) {
    raise = "Top step of this schedule";
  } else if (result.nextStepRaiseCents !== null) {
    const sign = result.nextStepRaiseCents >= 0 ? "+" : "";
    raise = `${sign}${formatCents(result.nextStepRaiseCents)} at the next step`;
  }
  return { amount, perDay, raise };
}

export interface CalculatorOptions {
  /** Đường dẫn nhận form GET, ví dụ trang học khu hoặc /calculator. */
  action: string;
  /** Trường ẩn gửi kèm, ví dụ `d` của trang /calculator. */
  hidden: Record<string, string>;
  laneIndex: number;
  stepIndex: number;
}

function experienceSuffix(years: number | null): string {
  if (years === null) {
    return "";
  }
  return years === 1 ? " (1 year of experience)" : ` (${years} years of experience)`;
}

function option(value: number, label: string, selected: boolean): Html {
  const flag = selected ? raw(" selected") : "";
  return html`<option value="${value}"${flag}>${label}</option>`;
}

/**
 * Máy tính lương của một bảng. Không có JavaScript: form GET nạp lại trang với kết quả do server
 * tính. Có JavaScript: `site.js` đọc `data-cents` trong bảng và cập nhật ngay khi đổi lựa chọn.
 */
export function calculator(schedule: Schedule, options: CalculatorOptions): Html {
  const id = schedule.id;
  const hidden: Html[] = [];
  for (const [name, value] of Object.entries(options.hidden)) {
    hidden.push(html`<input type="hidden" name="${name}" value="${value}">`);
  }
  const lanes: Html[] = [];
  for (const [j, lane] of schedule.lanes.entries()) {
    lanes.push(option(j + 1, lane.labelRaw, j === options.laneIndex));
  }
  let laneField = html``;
  if (lanes.length > 0) {
    laneField = html`<div class="field"><label for="lane-${id}">Education lane</label>
<select id="lane-${id}" name="lane">${lanes}</select></div>`;
  }
  const steps: Html[] = [];
  for (const [i, step] of schedule.steps.entries()) {
    const label = `${stepLabel(step)}${experienceSuffix(step.yearsExperience)}`;
    steps.push(option(i + 1, label, i === options.stepIndex));
  }
  const result = calculate(schedule, options.laneIndex, options.stepIndex);
  const text = calculationText(schedule, result);
  return html`<form class="calc" method="get" action="${options.action}#calc-${id}" data-calc-table="schedule-${id}" data-calc-result="calc-${id}">
${hidden}<input type="hidden" name="s" value="${id}">
${laneField}
<div class="field"><label for="step-${id}">Step</label>
<select id="step-${id}" name="step">${steps}</select></div>
<button type="submit">Calculate</button>
</form>
<dl class="facts calc-result" id="calc-${id}" aria-live="polite">
<div><dt>Salary on schedule</dt><dd data-out="amount">${text.amount}</dd></div>
<div><dt>Per contract day</dt><dd data-out="per-day">${text.perDay}</dd></div>
<div><dt>Raise at next step</dt><dd data-out="raise">${text.raise}</dd></div>
</dl>`;
}

// ---------------------------------------------------------------- phụ cấp và ghi chú

export function hasStipendsOrNotes(schedule: Schedule): boolean {
  return schedule.stipends.length > 0 || Boolean(schedule.notes);
}

/** Phụ cấp và ghi chú của tài liệu, giữ nguyên văn. */
export function stipendsAndNotes(schedule: Schedule): Html {
  const rows: Html[] = [];
  for (const stipend of schedule.stipends) {
    let amount = stipend.amountRaw ?? "";
    if (stipend.amountCents !== null) {
      amount = formatCents(stipend.amountCents);
    }
    const condition = stipend.condition ?? "";
    const row = html`<tr><th scope="row">${stipend.name}</th><td>${amount}</td><td>${condition}</td></tr>\n`;
    rows.push(row);
  }
  let table = html``;
  if (rows.length > 0) {
    table = html`<div class="table-scroll" role="region" aria-label="Stipends" tabindex="0">
<table>
<thead><tr><th scope="col">Stipend</th><th scope="col">Amount</th><th scope="col">Condition</th></tr></thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
  }
  const notes = schedule.notes ? html`<p class="verbatim">${schedule.notes}</p>` : html``;
  return html`${table}
${notes}`;
}

// ---------------------------------------------------------------- nguồn

/** Nguồn của bảng: link tài liệu gốc, vị trí trong tài liệu, ngày tải, trạng thái kiểm tra. */
export function sourceBlock(schedule: Schedule, reportHref: string | null): Html {
  const { source } = schedule;
  const url = safeHttpUrl(source.url);
  const link = url
    ? html`<a href="${url}" rel="nofollow noopener">${hostOf(url)}</a> (original document)`
    : html`${source.url}`;
  let location = "Not recorded";
  if (source.page !== null) {
    location = `Page ${source.page}`;
  } else if (source.sheet) {
    location = `Sheet “${source.sheet}”`;
  }
  const report = reportHref
    ? html`<p><a class="button" href="${reportHref}" rel="nofollow">Report an error</a></p>`
    : html``;
  const fingerprint = source.sha256.slice(0, 12);
  return html`<dl class="facts source">
<div><dt>Source document</dt><dd>${link}</dd></div>
<div><dt>Location in document</dt><dd>${location}</dd></div>
<div><dt>Retrieved</dt><dd>${formatDate(source.fetchedAt)}</dd></div>
<div><dt>Check status</dt><dd>Passed automated checks; not reviewed by a person. <a href="/methodology#checks">How we check</a></dd></div>
<div><dt>File fingerprint</dt><dd><abbr title="SHA-256 ${source.sha256}">${fingerprint}…</abbr></dd></div>
</dl>
${report}`;
}
