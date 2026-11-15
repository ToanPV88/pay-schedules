/** Các khối hiển thị một bảng lương: bảng, máy tính, phụ cấp và ghi chú, nguồn. */
import type { Cell, Schedule } from "@pay-schedules/db";
import { html, raw } from "hono/html";
import { type Calculation, calculate } from "../calc";
import {
  formatCents,
  formatDate,
  hostOf,
  payBasisNoun,
  safeHttpUrl,
  sourceLanding,
  stepLabel,
} from "../format";
import type { Html } from "./layout";

// ---------------------------------------------------------------- bảng

/** Ghi chú chung của pipeline cho ô trống (pipeline/.../extract.py: BLANK_NOTE): không thêm thông tin. */
const GENERIC_BLANK = /^(blank in the source( document)?|not in the source)\.?$/i;

/**
 * Ô trống chỉ hiện dấu gạch. Ghi chú riêng của tài liệu (vd. "No initial placement in this lane")
 * nằm ở title (rê chuột) và trong chữ cho trình đọc màn hình; ghi chú chung "Blank in the source
 * document" không hiện. CSV và Excel vẫn ghi đủ ghi chú.
 */
function cellHtml(cell: Cell | null): Html {
  if (cell?.amountCents !== null && cell?.amountCents !== undefined) {
    return html`<td data-cents="${cell.amountCents}">${formatCents(cell.amountCents)}</td>`;
  }
  const note = cell?.note?.trim() ?? "";
  if (note !== "" && !GENERIC_BLANK.test(note)) {
    return html`<td class="empty" title="${note}">—<span class="visually-hidden"> ${note}</span></td>`;
  }
  return html`<td class="empty">—<span class="visually-hidden"> No amount in the source</span></td>`;
}

/**
 * Nút đổi cỡ chữ của bảng lương. Ẩn sẵn; site.js hiện ra và nhớ lựa chọn trong trình duyệt.
 * Không có JavaScript thì người xem dùng phím phóng to của trình duyệt.
 */
const TEXT_SIZE_TOOL = raw(
  '<div class="table-tools" data-text-size hidden><span>Text size</span><button type="button" data-size="-1" aria-label="Smaller table text">A−</button><button type="button" data-size="1" aria-label="Larger table text">A+</button></div>',
);

/** Bảng có nhiều bậc hơn số này được giữ trong khung cuộn có hàng tiêu đề dính. */
export const LONG_SCHEDULE_ROWS = 12;

/**
 * Bảng lương đầy đủ bằng thẻ table thật: đọc được khi tắt JavaScript. Ô có số mang `data-cents`
 * để `site.js` tính tại chỗ; ô trống là dấu gạch, chú thích bảng giải thích một lần.
 */
export function scheduleTable(schedule: Schedule, caption: string): Html {
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
      cells.push(cellHtml(cell));
    }
    rows.push(html`<tr><th scope="row">${step.labelRaw}</th>${cells}</tr>\n`);
  }
  const hasEmpty = schedule.cells.some((row) => row.some((cell) => cell?.amountCents == null));
  const dashNote = hasEmpty ? ". A dash means the document shows no amount for that cell." : "";
  const days = schedule.contractDays ?? "";
  // Bảng dài: khung cuộn có chiều cao giới hạn để hàng tiêu đề (tên lane) luôn nhìn thấy.
  const scrollClass =
    schedule.steps.length > LONG_SCHEDULE_ROWS ? "table-scroll tall" : "table-scroll";
  return html`${TEXT_SIZE_TOOL}
<div class="${scrollClass}" role="region" aria-label="${caption}" tabindex="0">
<table class="schedule" id="schedule-${schedule.id}" data-days="${days}" data-basis="${schedule.payBasis}">
<caption>${caption}${dashNote}</caption>
<thead>
<tr><th scope="col">Step</th>${head}</tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
}

// ---------------------------------------------------------------- máy tính

export interface CalculationText {
  amount: string;
  perMonth: string;
  perDay: string;
  raise: string;
  top: string;
}

/** "$97,726 at Step 16 (15 more steps)" hoặc "This is the top of the lane". */
function topText(schedule: Schedule, result: Calculation | null): string {
  if (!result || result.topStepIndex === null || result.topCents === null) {
    return "—";
  }
  const more = result.topStepIndex - result.stepIndex;
  if (more <= 0) {
    return "This is the top of the lane";
  }
  const step = schedule.steps[result.topStepIndex];
  const label = step ? stepLabel(step) : `Step ${result.topStepIndex + 1}`;
  return `${formatCents(result.topCents)} at ${label} (${more} more ${more === 1 ? "step" : "steps"})`;
}

/** Các dòng kết quả. Câu chữ phải khớp với `public/site.js`. */
export function calculationText(schedule: Schedule, result: Calculation | null): CalculationText {
  const top = topText(schedule, result);
  if (!result || result.amountCents === null) {
    const raise = result?.isTopStep ? "Top step of this schedule" : "—";
    return {
      amount: "No amount listed for this step and lane",
      perMonth: "—",
      perDay: "—",
      raise,
      top,
    };
  }
  const amount = `${formatCents(result.amountCents)} ${payBasisNoun(schedule.payBasis)}`;
  const perMonth =
    result.perMonthCents === null ? "—" : `${formatCents(result.perMonthCents)} (12 equal checks)`;
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
  return { amount, perMonth, perDay, raise, top };
}

export interface CalculatorOptions {
  /** Đường dẫn nhận form GET, ví dụ trang học khu hoặc /calculator. */
  action: string;
  /** Trường ẩn gửi kèm, ví dụ `d` của trang /calculator. */
  hidden: Record<string, string>;
  laneIndex: number;
  stepIndex: number;
}

function yearsText(years: number): string {
  return years === 1 ? "1 year" : `${years} years`;
}

/** Mọi bậc đều ghi số năm kinh nghiệm: ô chọn hỏi theo số năm thay vì theo bậc. */
export function stepsHaveYears(schedule: Schedule): boolean {
  return schedule.steps.length > 0 && schedule.steps.every((step) => step.yearsExperience !== null);
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
  const byYears = stepsHaveYears(schedule);
  const steps: Html[] = [];
  for (const [i, step] of schedule.steps.entries()) {
    let label = `${stepLabel(step)}${experienceSuffix(step.yearsExperience)}`;
    if (byYears && step.yearsExperience !== null) {
      // Nhãn gốc khác số năm (vd. bậc "1" = 0 năm, "40+"): ghi kèm để đối chiếu với bảng.
      const same = step.labelRaw === String(step.yearsExperience);
      label = same
        ? yearsText(step.yearsExperience)
        : `${yearsText(step.yearsExperience)} (${stepLabel(step)})`;
    }
    steps.push(option(i + 1, label, i === options.stepIndex));
  }
  const stepFieldLabel = byYears ? "Years of experience" : "Step";
  const result = calculate(schedule, options.laneIndex, options.stepIndex);
  const text = calculationText(schedule, result);
  const form = html`<form class="calc" method="get" action="${options.action}#calc-${id}" data-calc-table="schedule-${id}" data-calc-result="calc-${id}">
${hidden}<input type="hidden" name="s" value="${id}">
${laneField}
<div class="field"><label for="step-${id}">${stepFieldLabel}</label>
<select id="step-${id}" name="step">${steps}</select></div>
<button type="submit">Calculate</button>
</form>`;
  // Bảng không tính theo năm (theo giờ, ngày, tháng): bỏ hai ô quy đổi từ lương năm.
  const annual = schedule.payBasis === "annual";
  const perMonth = annual
    ? html`<div><dt>Per month</dt><dd data-out="per-month">${text.perMonth}</dd></div>`
    : html``;
  const perDay = annual
    ? html`<div><dt>Per contract day</dt><dd data-out="per-day">${text.perDay}</dd></div>`
    : html``;
  return html`${form}
<dl class="facts calc-result" id="calc-${id}" aria-live="polite">
<div><dt>Salary on schedule</dt><dd data-out="amount">${text.amount}</dd></div>
${perMonth}${perDay}<div><dt>Raise at next step</dt><dd data-out="raise">${text.raise}</dd></div>
<div><dt>Top of this lane</dt><dd data-out="top">${text.top}</dd></div>
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
/** Lời giải thích (tiếng Anh) cho mã kiểm tra đã báo ở bảng publish "như nguồn" (D-028). */
const AS_REPORTED_TEXT: Record<string, string> = {
  monotonic_step: "pay goes down from one step to the next",
  monotonic_lane: "a lane with more education pays less than a lower one",
  start_change: "starting pay changed by more than 20% from the previous year",
  step_start: "the table starts above step 1",
  school_year: "this is the most recent schedule we found; a newer one may exist",
};

function checkStatus(asReported: string[]): Html {
  if (asReported.length === 0) {
    return html`Passed automated checks; not reviewed by a person. <a href="/methodology#checks">How we check</a>`;
  }
  const found = asReported.map((code) => AS_REPORTED_TEXT[code] ?? code).join("; ");
  return html`Shown as the source published it. Our automated checks flagged values that look unusual (${found}); they have not been changed. <a href="/methodology#checks">How we check</a>`;
}

export function sourceBlock(
  schedule: Schedule,
  reportHref: string | null,
  asReported: string[] = [],
): Html {
  const { source } = schedule;
  const landing = sourceLanding(source.url);
  const url = safeHttpUrl(source.url);
  let link: Html;
  if (landing) {
    link = html`<a href="${landing.href}" rel="nofollow noopener">${landing.label}</a>`;
  } else if (url && /\.exe$/i.test(new URL(url).pathname)) {
    link = html`${hostOf(url)} (data file, not linked)`;
  } else if (url) {
    link = html`<a href="${url}" rel="nofollow noopener">${hostOf(url)}</a> (original document)`;
  } else {
    link = html`${source.url}`;
  }
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
<div><dt>Check status</dt><dd>${checkStatus(asReported)}</dd></div>
<div><dt>File fingerprint</dt><dd><abbr title="SHA-256 ${source.sha256}">${fingerprint}…</abbr></dd></div>
</dl>
${report}`;
}
