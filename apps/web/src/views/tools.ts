/** Trang /compare, /calculator và /report. */
import type { District, LargeDistrict, Schedule, SearchHit } from "@pay-schedules/db";
import { html, raw } from "hono/html";
import { type CompareEntry, compareCell, MAX_COMPARE } from "../compare";
import { formatCents, schoolYearLabel } from "../format";
import type { Selection } from "./district";
import type { Html } from "./layout";
import { benchmarkRow, districtPath, hitList, placeLine, searchForm } from "./parts";
import { calculator, scheduleTable } from "./schedule";

function keyOfDistrict(district: District): string {
  return `${district.state.slug}/${district.slug}`;
}

// ---------------------------------------------------------------- /compare

export interface ComparePageData {
  entries: CompareEntry[];
  /** Các cột bằng cấp chuẩn hóa chọn được; rỗng khi không bảng nào có cột bằng cấp. */
  lanes: string[];
  lane: string | null;
  /** Số bậc của bảng dài nhất. */
  steps: number;
  /** Bậc đang chọn, đếm từ 1. */
  step: number;
  query: string;
  hits: SearchHit[];
  /** Học khu lớn có số liệu, gợi ý sẵn khi chưa chọn học khu nào. */
  popular?: LargeDistrict[];
  /** Cặp so sánh nổi bật (trang /compare/<a>-vs-<b>), gợi ý khi chưa chọn học khu. */
  featured?: { href: string; label: string }[];
  /** Trang so sánh hai học khu: tiêu đề và phần đối đầu thay cho tiêu đề chung (D-118). */
  heading?: string;
  lede?: Html;
  before?: Html;
}

/** Danh sách học khu gợi ý sẵn (thẻ bấm được), mỗi thẻ dẫn tới `hrefOf(key)`. */
export function popularList(items: LargeDistrict[], hrefOf: (key: string) => string): Html {
  if (items.length === 0) {
    return html``;
  }
  const links = items.map((item) => {
    const key = `${item.stateSlug}/${item.slug}`;
    return html`<li><a href="${hrefOf(key)}">${item.name} <span class="muted">${item.stateCode}</span></a></li>`;
  });
  return html`<ul class="chip-list">${links}</ul>`;
}

export function comparePath(keys: string[], lane: string | null, step: number): string {
  if (keys.length === 0) {
    return "/compare";
  }
  const params = [`d=${keys.join(",")}`];
  if (lane) {
    params.push(`lane=${encodeURIComponent(lane)}`);
  }
  if (step > 1) {
    params.push(`step=${step}`);
  }
  return `/compare?${params.join("&")}`;
}

function option(value: string, label: string, selected: boolean): Html {
  const flag = selected ? raw(" selected") : "";
  return html`<option value="${value}"${flag}>${label}</option>`;
}

function compareControls(data: ComparePageData, keys: string[]): Html {
  const lanes: Html[] = [];
  for (const lane of data.lanes) {
    lanes.push(option(lane, lane, lane === data.lane));
  }
  let laneField = html``;
  if (lanes.length > 0) {
    laneField = html`<div class="field"><label for="lane">Education lane</label>
<select id="lane" name="lane">${lanes}</select></div>`;
  }
  const steps: Html[] = [];
  for (let position = 1; position <= data.steps; position += 1) {
    steps.push(option(String(position), `Step ${position}`, position === data.step));
  }
  return html`<form class="calc" method="get" action="/compare">
<input type="hidden" name="d" value="${keys.join(",")}">
${laneField}
<div class="field"><label for="step">Step (counted from the first row)</label>
<select id="step" name="step">${steps}</select></div>
<button type="submit">Compare</button>
</form>`;
}

export interface Extremes {
  maxCents: number;
  minCents: number;
}

/** Cao nhất và thấp nhất trong các ô có số; null khi chưa đủ hai số khác nhau để so. */
export function extremesOf(amounts: (number | null)[]): Extremes | null {
  const values = amounts.filter((a): a is number => a !== null);
  if (values.length < 2) {
    return null;
  }
  const maxCents = Math.max(...values);
  const minCents = Math.min(...values);
  return maxCents === minCents ? null : { maxCents, minCents };
}

/**
 * Ô lương của một dòng so sánh: số tiền, nhãn "Highest"/"Lowest" (chữ, không chỉ màu), thanh dài
 * theo tỉ lệ với mức cao nhất và khoảng cách tới mức cao nhất.
 */
function amountCell(amount: number, extremes: Extremes | null): Html {
  if (!extremes) {
    return html`<td class="amount-cell">${formatCents(amount)}</td>`;
  }
  const width = Math.round((amount / extremes.maxCents) * 100);
  let badge = html``;
  let gap = html``;
  if (amount === extremes.maxCents) {
    badge = html` <span class="badge badge-top">Highest</span>`;
  } else {
    if (amount === extremes.minCents) {
      badge = html` <span class="badge">Lowest</span>`;
    }
    gap = html`<span class="gap">${formatCents(extremes.maxCents - amount)} below the highest</span>`;
  }
  return html`<td class="amount-cell"><span class="amount">${formatCents(amount)}</span>${badge}<span class="bar" style="width: ${width}%"></span>${gap}</td>`;
}

function compareRows(data: ComparePageData, keys: string[]): Html[] {
  const rows: Html[] = [];
  const cells = data.entries.map((entry) => compareCell(entry.schedule, data.lane, data.step));
  const extremes = extremesOf(cells.map((cell) => cell.amountCents));
  for (const [i, entry] of data.entries.entries()) {
    const { district, schedule } = entry;
    const key = keyOfDistrict(district);
    const href = districtPath(district.state.slug, district.slug);
    const others = keys.filter((k) => k !== key);
    const remove = comparePath(others, data.lane, data.step);
    const cell = cells[i] ?? compareCell(schedule, data.lane, data.step);
    const year = schedule ? schoolYearLabel(schedule.schoolYear) : "";
    let lane = cell.laneLabel ?? "";
    if (schedule && schedule.lanes.length === 0) {
      lane = "Single column";
    }
    const amount =
      cell.amountCents === null
        ? html`<td class="empty">${cell.reason ?? "—"}</td>`
        : amountCell(cell.amountCents, extremes);
    const place = placeLine(district.city, null, district.state.code);
    const top = extremes !== null && cell.amountCents === extremes.maxCents;
    const row = html`<tr${top ? raw(' class="top-row"') : ""}>
<th scope="row"><a href="${href}">${district.name}</a><br><span class="muted">${place}</span></th>
<td>${year}</td><td>${lane}</td><td>${cell.stepLabel ?? ""}</td>${amount}
<td><a href="${remove}" rel="nofollow">Remove<span class="visually-hidden"> ${district.name}</span></a></td>
</tr>
`;
    rows.push(row);
  }
  return rows;
}

export function comparePage(data: ComparePageData): Html {
  const keys = data.entries.map((entry) => keyOfDistrict(entry.district));
  let adder = html``;
  if (keys.length < MAX_COMPARE) {
    const hidden: Record<string, string> = {};
    if (keys.length > 0) {
      hidden.d = keys.join(",");
    }
    if (data.lane) {
      hidden.lane = data.lane;
    }
    if (data.step > 1) {
      hidden.step = String(data.step);
    }
    const form = searchForm({
      action: "/compare",
      query: data.query,
      label: keys.length === 0 ? "Find the first district" : "Add another district",
      hidden,
      button: "Find",
      suggestHref: comparePath([...keys, "{key}"], data.lane, data.step),
    });
    const candidates = data.hits.filter((hit) => !keys.includes(`${hit.state.slug}/${hit.slug}`));
    let results = html``;
    if (candidates.length > 0) {
      const hrefOf = (hit: SearchHit) =>
        comparePath([...keys, `${hit.state.slug}/${hit.slug}`], data.lane, data.step);
      results = hitList(candidates, hrefOf);
    } else if (data.query !== "") {
      results = html`<p>No other districts match “${data.query}”.</p>`;
    }
    adder = html`<section aria-labelledby="add-heading">
<h2 id="add-heading">Add a district</h2>
${form}
${results}
</section>`;
  }
  if (data.entries.length === 0) {
    const popular = data.popular ?? [];
    let start = html``;
    if (popular.length > 0) {
      const sample = popular.slice(0, 3).map((p) => `${p.stateSlug}/${p.slug}`);
      const quick =
        sample.length >= 2
          ? html`<p><a class="button" data-nearby-button href="${comparePath(sample, null, 1)}">Compare the ${sample.length} largest districts</a></p>`
          : html``;
      // site.js thay bằng học khu gần người xem khi biết vị trí gần đúng (data-nearby).
      start = html`<section aria-labelledby="popular-heading" data-nearby="/compare?d={key}" data-nearby-compare="/compare?d={keys}">
<h2 id="popular-heading">Or start from a large district</h2>
${quick}
${popularList(popular, (key) => comparePath([key], null, 1))}
</section>`;
    }
    const featured = data.featured ?? [];
    const pairs =
      featured.length > 0
        ? html`<section aria-labelledby="pairs-heading">
<h2 id="pairs-heading">Popular comparisons</h2>
<ul class="chip-list">${featured.map((p) => html`<li><a href="${p.href}">${p.label}</a></li>`)}</ul>
</section>`
        : html``;
    return html`<h1>Compare salary schedules</h1>
<p class="lede">Put up to ${MAX_COMPARE} districts side by side at the same step and education lane. Each row reads one cell from that district’s latest published schedule.</p>
${adder}
${start}
${pairs}`;
  }
  const benchmarks: Html[] = [];
  for (const entry of data.entries) {
    if (entry.summary) {
      benchmarks.push(benchmarkRow(html`${entry.district.name}`, entry.summary, false));
    }
  }
  let benchmarkTable = html``;
  if (benchmarks.length > 0) {
    benchmarkTable = html`<section aria-labelledby="benchmarks-heading">
<h2 id="benchmarks-heading">Benchmarks</h2>
<div class="table-scroll" role="region" aria-label="Benchmarks" tabindex="0">
<table>
<thead>
<tr><th scope="col">District</th><th scope="col">School year</th><th scope="col">BA, step 1</th><th scope="col">MA, step 10</th><th scope="col">Maximum</th></tr>
</thead>
<tbody>
${benchmarks}</tbody>
</table>
</div>
</section>`;
  }
  const lede =
    data.lede ??
    html`Each row reads one cell from that district’s latest published schedule. Lanes are matched by education level; steps are matched by row position, so check each district’s own step label.`;
  return html`<h1>${data.heading ?? "Compare salary schedules"}</h1>
<p class="lede">${lede}</p>
${data.before ?? html``}
${data.heading ? html`<h2 id="same-cell-heading">Same step and lane</h2>` : html``}
${compareControls(data, keys)}
<div class="table-scroll" role="region" aria-label="Comparison" tabindex="0">
<table class="compare">
<thead>
<tr><th scope="col">District</th><th scope="col">School year</th><th scope="col">Lane on schedule</th><th scope="col">Step on schedule</th><th scope="col">Salary</th><th scope="col"><span class="visually-hidden">Remove</span></th></tr>
</thead>
<tbody>
${compareRows(data, keys)}</tbody>
</table>
</div>
${benchmarkTable}
${adder}`;
}

// ---------------------------------------------------------------- /calculator

export interface CalculatorPageData {
  query: string;
  hits: SearchHit[];
  /** Học khu đã chọn qua tham số `d`; null khi chưa chọn. */
  district: District | null;
  schedules: Schedule[];
  selection: Selection | null;
  /** Học khu lớn có số liệu, gợi ý sẵn khi chưa chọn học khu. */
  popular?: LargeDistrict[];
}

export function calculatorPage(data: CalculatorPageData): Html {
  const form = searchForm({
    action: "/calculator",
    query: data.query,
    label: "Find a school district",
    button: "Find",
    suggestHref: "/calculator?d={key}",
  });
  const { district } = data;
  if (!district) {
    let results = html``;
    if (data.hits.length > 0) {
      results = hitList(data.hits, (hit) => `/calculator?d=${hit.state.slug}/${hit.slug}`);
    } else if (data.query !== "") {
      results = html`<p>No districts match “${data.query}”.</p>`;
    }
    const popular = data.popular ?? [];
    let start = html``;
    if (popular.length > 0) {
      // site.js thay bằng học khu gần người xem khi biết vị trí gần đúng (data-nearby).
      start = html`<section aria-labelledby="popular-heading" data-nearby="/calculator?d={key}">
<h2 id="popular-heading">Popular districts</h2>
${popularList(popular, (key) => `/calculator?d=${key}`)}
</section>`;
    }
    return html`<h1>Teacher salary calculator</h1>
<p class="lede">Choose a district, then your education lane and years of experience, to read the salary from that district’s published schedule. You can also tap any cell in the table.</p>
${form}
${results}
${start}`;
  }
  const key = keyOfDistrict(district);
  const page = districtPath(district.state.slug, district.slug);
  const sections: Html[] = [];
  for (const schedule of data.schedules) {
    const chosen = data.selection?.scheduleId === schedule.id ? data.selection : null;
    const heading = schedule.title || "Salary schedule";
    const caption = `${district.name}, ${schoolYearLabel(schedule.schoolYear)}: ${heading}`;
    const calc = calculator(schedule, {
      action: "/calculator",
      hidden: { d: key },
      laneIndex: chosen?.laneIndex ?? 0,
      stepIndex: chosen?.stepIndex ?? 0,
    });
    const section = html`<section aria-labelledby="schedule-${schedule.id}-heading">
<h2 id="schedule-${schedule.id}-heading">${heading} (${schoolYearLabel(schedule.schoolYear)})</h2>
${calc}
<h3>Full schedule</h3>
${scheduleTable(schedule, caption)}
</section>
`;
    sections.push(section);
  }
  let body = html`<p class="notice"><strong>Schedule not found.</strong> We have not published a salary schedule for this district yet.</p>`;
  if (sections.length > 0) {
    body = html`${sections}`;
  }
  return html`<h1>Salary calculator: ${district.name}</h1>
<p class="lede"><a href="${page}">See the full district page</a> for nearby districts, stipends and the source document.</p>
${body}
<section aria-labelledby="other-heading">
<h2 id="other-heading">Choose another district</h2>
${form}
</section>`;
}

// ---------------------------------------------------------------- /report

export const REPORT_ERRORS = {
  length: "Please describe the problem in 10 to 2,000 characters.",
  challenge: "The spam check did not pass. Please try again.",
  schedule: "That schedule could not be found. Please go back to the district page and try again.",
} as const;

export type ReportError = keyof typeof REPORT_ERRORS;

export interface ReportPageData {
  district: District;
  scheduleId: number | null;
  siteKey: string;
  message: string;
  error: ReportError | null;
  sent: boolean;
}

export function reportPage(data: ReportPageData): Html {
  const { district } = data;
  const page = districtPath(district.state.slug, district.slug);
  if (data.sent) {
    return html`<h1>Report received</h1>
<p>Thank you. We will compare the table with its source document.</p>
<p><a href="${page}">Back to ${district.name}</a></p>`;
  }
  const error = data.error
    ? html`<p class="notice" role="alert">${REPORT_ERRORS[data.error]}</p>`
    : html``;
  const schedule =
    data.scheduleId === null
      ? html``
      : html`<input type="hidden" name="s" value="${data.scheduleId}">`;
  return html`<h1>Report an error</h1>
<p class="lede">About <a href="${page}">${district.name}</a>.</p>
${error}
<form class="report-form" method="post" action="/report">
<input type="hidden" name="d" value="${keyOfDistrict(district)}">
${schedule}
<label for="message">What looks wrong? Say which step and lane, and what the source document shows.</label>
<textarea id="message" name="message" rows="6" minlength="10" maxlength="2000" required>${data.message}</textarea>
<p class="muted">Please do not include personal information. We store only this message and the page it refers to.</p>
<div class="hp" aria-hidden="true"><label for="website">Leave this field empty</label><input id="website" name="website" type="text" tabindex="-1" autocomplete="off"></div>
<div class="cf-turnstile" data-sitekey="${data.siteKey}"></div>
<button type="submit">Send report</button>
</form>`;
}
