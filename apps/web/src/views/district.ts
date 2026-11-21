/** Trang học khu (PLAN Công đoạn 6: tám phần theo thứ tự) và trang "schedule not found". */
import type {
  District,
  Neighbor,
  PayBasis,
  PayOverview,
  Schedule,
  Summary,
  YearHistory,
} from "@pay-schedules/db";
import { html, raw } from "hono/html";
import { scheduleGrowth } from "../analysis";
import { scheduleRange } from "../calc";
import { csvPath } from "../csv";
import { formatCents, payBasisNoun, safeHttpUrl, schoolYearLabel, sourceLanding } from "../format";
import { ordinal, type Rank, topPercent } from "../ranks";
import { XLSX_TYPE, xlsxPath } from "../xlsx";
import { payChart } from "./chart";
import { morePayBlock } from "./extra";
import { faqSection } from "./faq";
import { adSlot, breadcrumbs, type Html, type Site } from "./layout";
import { benchmarkRow, districtPath, placeLine } from "./parts";
import {
  calculator,
  hasStipendsOrNotes,
  scheduleTable,
  sourceBlock,
  stepsHaveYears,
  stipendsAndNotes,
} from "./schedule";

export interface Selection {
  scheduleId: number;
  laneIndex: number;
  stepIndex: number;
}

export interface DistrictRanks {
  start: { state: Rank | null; nation: Rank | null };
  max: { state: Rank | null; nation: Rank | null };
}

export interface DistrictPageData {
  district: District;
  /** Năm học đang hiện. */
  year: string;
  /** Năm học mới nhất có bảng published. */
  latestYear: string;
  /** Các bảng lương giáo viên published của `year`; luôn có ít nhất một. */
  schedules: Schedule[];
  history: YearHistory[];
  summary: Summary | null;
  neighbors: Neighbor[];
  /** Lựa chọn của máy tính lấy từ query; null thì dùng bậc đầu, cột đầu. */
  selection: Selection | null;
  reportsEnabled: boolean;
  /** Mã kiểm tra đã báo ở bảng publish "như nguồn", theo id bảng (D-028). */
  asReported: Map<number, string[]>;
  /** Đường dẫn nhận form máy tính (chính trang này). */
  path: string;
  /** Trang mẫu với dữ liệu giả lập (chỉ ở bản xem trước). */
  demo: boolean;
  /** Trung vị của bang để so sánh trong câu mô tả; null khi không có. */
  statePay?: PayOverview | null;
  /** Hạng ở mốc khởi điểm và tối đa, trong bang và toàn quốc; chỉ có khi đang xem năm mới nhất. */
  ranks?: DistrictRanks | null;
  /** Cặp so sánh nổi bật có học khu này (trang /compare/<a>-vs-<b>, D-118). */
  pairs?: { href: string; label: string }[];
  /** Có học khu khác cùng tên trong bang: tiêu đề thêm thành phố. */
  sameNameInState?: boolean;
  /** Trang lương khác của học khu (phụ cấp HLV...), PLAN Công đoạn 11. */
  morePay?: { href: string; label: string }[];
}

/** Số học khu tối thiểu để trung vị của bang đủ nghĩa khi so sánh. */
export const MIN_STATE_DISTRICTS = 5;

/** Câu hướng dẫn của máy tính: hỏi số năm khi bảng ghi số năm cho mọi bậc. */
function calcHint(schedule: Schedule): string {
  if (stepsHaveYears(schedule)) {
    return "Pick a lane and your years of experience, or tap a cell in the table above.";
  }
  return "Pick a lane and a step, or tap a cell in the table above.";
}

export function districtTitle(district: District, year: string): string {
  return `${district.name} Teacher Salary Schedule ${schoolYearLabel(year)}`;
}

/**
 * Thẻ <title>: thêm mã bang (nhiều bang có học khu trùng tên) và thành phố khi trong bang có học
 * khu khác cùng tên, để không có hai trang trùng title (PLAN Công đoạn 7, nghiệm thu).
 */
export function districtDocumentTitle(
  district: District,
  year: string,
  sameNameInState: boolean,
): string {
  const where = sameNameInState && district.city ? ` (${district.city})` : "";
  return `${district.name}${where}, ${district.state.code} Teacher Salary Schedule ${schoolYearLabel(year)}`;
}

function gap(own: number, median: number): string {
  const diff = own - median;
  if (Math.abs(diff) < 100) {
    return "about the same as";
  }
  return `${formatCents(Math.abs(diff))} ${diff > 0 ? "above" : "below"}`;
}

/**
 * Câu so sánh với trung vị của bang, sinh từ số liệu (PLAN Công đoạn 7: không dùng đoạn văn
 * chung lặp lại giữa các trang). Null khi thiếu số hoặc bang có quá ít học khu để so.
 */
export function stateComparison(data: DistrictPageData): string | null {
  const pay = data.statePay;
  const summary = data.summary;
  if (!pay || !summary || summary.schoolYear !== data.year) {
    return null;
  }
  if (!data.schedules.every((s) => s.payBasis === "annual")) {
    return null;
  }
  const state = data.district.state.name;
  const parts: string[] = [];
  const start = summary.startBaCents;
  if (start !== null && pay.start.cents !== null && pay.start.districts >= MIN_STATE_DISTRICTS) {
    parts.push(
      `Starting pay for a teacher with a bachelor’s degree is ${formatCents(start)}, ${gap(start, pay.start.cents)} the ${state} median of ${formatCents(pay.start.cents)}`,
    );
  }
  const max = summary.maxSalaryCents;
  if (max !== null && pay.max.cents !== null && pay.max.districts >= MIN_STATE_DISTRICTS) {
    const lead = parts.length > 0 ? "the top of the scale is" : "The top of the scale is";
    parts.push(
      `${lead} ${formatCents(max)}, ${gap(max, pay.max.cents)} the state median of ${formatCents(pay.max.cents)}`,
    );
  }
  if (parts.length === 0) {
    return null;
  }
  const n = Math.max(pay.start.districts, pay.max.districts);
  return `${parts.join("; ")} (medians of ${n.toLocaleString("en-US")} ${state} districts on this site).`;
}

interface YearFacts {
  minCents: number | null;
  maxCents: number | null;
  /** Null khi các bảng trong năm tính theo đơn vị khác nhau. */
  basis: PayBasis | null;
  /** Số ngày hợp đồng; "varies" khi các bảng ghi khác nhau; null khi tài liệu không ghi. */
  contractDays: number | "varies" | null;
}

export function yearFacts(schedules: Schedule[]): YearFacts {
  const first = schedules[0];
  if (!first) {
    return { minCents: null, maxCents: null, basis: null, contractDays: null };
  }
  const sameBasis = schedules.every((s) => s.payBasis === first.payBasis);
  const sameDays = schedules.every((s) => s.contractDays === first.contractDays);
  let min: number | null = null;
  let max: number | null = null;
  if (sameBasis) {
    for (const schedule of schedules) {
      const range = scheduleRange(schedule);
      if (range) {
        min = min === null ? range.minCents : Math.min(min, range.minCents);
        max = max === null ? range.maxCents : Math.max(max, range.maxCents);
      }
    }
  }
  return {
    minCents: min,
    maxCents: max,
    basis: sameBasis ? first.payBasis : null,
    contractDays: sameDays ? first.contractDays : "varies",
  };
}

export function districtDescription(data: DistrictPageData): string {
  const { district } = data;
  const place = placeLine(district.city, null, district.state.name);
  const year = schoolYearLabel(data.year);
  const facts = yearFacts(data.schedules);
  let range = "";
  if (facts.minCents !== null && facts.maxCents !== null && facts.basis === "annual") {
    range = `, from ${formatCents(facts.minCents)} to ${formatCents(facts.maxCents)}`;
  }
  const comparison = stateComparison(data);
  if (comparison) {
    return `${district.name} (${place}) teacher salary schedule for ${year}${range}. ${comparison}`;
  }
  return `${district.name} (${place}) teacher salary schedule for ${year}${range}. Full step and lane table, salary calculator and a link to the source document.`;
}

function summaryFacts(schedules: Schedule[]): Html {
  const facts = yearFacts(schedules);
  const noun = facts.basis ? ` ${payBasisNoun(facts.basis)}` : "";
  let lowest = "Varies by schedule";
  let highest = "Varies by schedule";
  if (facts.basis) {
    lowest = facts.minCents === null ? "Not listed" : `${formatCents(facts.minCents)}${noun}`;
    highest = facts.maxCents === null ? "Not listed" : `${formatCents(facts.maxCents)}${noun}`;
  }
  let days = "Not stated in the source";
  if (facts.contractDays === "varies") {
    days = "Varies by schedule";
  } else if (facts.contractDays !== null) {
    days = String(facts.contractDays);
  }
  return html`<dl class="facts summary">
<div><dt>Lowest salary on schedule</dt><dd>${lowest}</dd></div>
<div><dt>Highest salary on schedule</dt><dd>${highest}</dd></div>
<div><dt>Contract days</dt><dd>${days}</dd></div>
</dl>`;
}

function scheduleHeading(schedule: Schedule, many: boolean): string {
  if (schedule.title) {
    return schedule.title;
  }
  return many ? `Salary schedule ${schedule.id}` : "Salary schedule";
}

/** "16 steps × 9 lanes" của một bảng. */
function shapeText(schedule: Schedule): string {
  const steps = `${schedule.steps.length} ${schedule.steps.length === 1 ? "step" : "steps"}`;
  const lanes = schedule.lanes.length;
  if (lanes === 0) {
    return steps;
  }
  return `${steps} × ${lanes} ${lanes === 1 ? "lane" : "lanes"}`;
}

/**
 * Học khu có nhiều bảng lương trong năm: danh sách đầu trang để nhảy thẳng tới bảng cần xem,
 * mỗi thẻ ghi khoảng lương và kích thước bảng. Một bảng thì không cần.
 */
export function schedulePicker(schedules: Schedule[], year: string): Html {
  if (schedules.length < 2) {
    return html``;
  }
  const items: Html[] = [];
  for (const schedule of schedules) {
    const range = scheduleRange(schedule);
    let money = "";
    if (range) {
      const noun = payBasisNoun(schedule.payBasis);
      money =
        range.minCents === range.maxCents
          ? `${formatCents(range.minCents)} ${noun}`
          : `${formatCents(range.minCents)}–${formatCents(range.maxCents)} ${noun}`;
    }
    const meta = [money, shapeText(schedule)].filter(Boolean).join(" · ");
    items.push(
      html`<li><a href="#schedule-${schedule.id}-heading"><span class="picker-title">${scheduleHeading(schedule, true)}</span><span class="muted">${meta}</span></a></li>
`,
    );
  }
  const label = schoolYearLabel(year);
  return html`<nav class="schedule-picker" aria-labelledby="picker-heading">
<h2 id="picker-heading">Salary schedules for ${label}</h2>
<p>This district publishes ${schedules.length} salary schedules for ${label}. Pick one to jump to it.</p>
<ul>
${items}</ul>
</nav>`;
}

function laneName(schedule: Schedule, laneIndex: number): string {
  return schedule.lanes[laneIndex]?.labelRaw ?? "Salary";
}

function stepName(schedule: Schedule, stepIndex: number): string {
  return schedule.steps[stepIndex]?.labelRaw ?? String(stepIndex + 1);
}

/**
 * "How pay moves up": mỗi cột từ bậc đầu tới đỉnh, số bậc, phần trăm tăng; câu tóm tắt cho cột
 * đầu (thường là BA) kèm bước tăng lớn nhất. Không hiện khi bảng chỉ có một bậc.
 */
export function growthBlock(schedule: Schedule): Html {
  const lanes = scheduleGrowth(schedule);
  const first = lanes[0];
  if (!first) {
    return html``;
  }
  const lane = laneName(schedule, first.laneIndex);
  const moves = `${first.stepMoves} ${first.stepMoves === 1 ? "step" : "steps"}`;
  const years = first.years === null ? "" : ` (${first.years} years of experience)`;
  let raise = "";
  if (first.largestRaise) {
    const r = first.largestRaise;
    raise = ` The largest single raise is ${formatCents(r.cents)}, from step ${stepName(schedule, r.fromStepIndex)} to step ${stepName(schedule, r.toStepIndex)}.`;
  }
  const where = schedule.lanes.length > 0 ? `In the ${lane} column, pay` : "Pay";
  const lead =
    first.stepMoves === 0
      ? `${where} is ${formatCents(first.startCents)} at every listed step.`
      : `${where} rises from ${formatCents(first.startCents)} at step ${stepName(schedule, first.startStepIndex)} to ${formatCents(first.topCents)} at step ${stepName(schedule, first.topStepIndex)}: ${moves}${years}, an increase of ${first.growthPct.toLocaleString("en-US")}%.${raise}`;
  if (lanes.length < 2) {
    return html`<h3>How pay moves up this schedule</h3>
<p class="growth">${lead}</p>`;
  }
  const rows = lanes.map(
    (
      g,
    ) => html`<tr><th scope="row">${laneName(schedule, g.laneIndex)}</th><td>${formatCents(g.startCents)}</td><td>${formatCents(g.topCents)}</td><td>${g.stepMoves}</td><td>${g.growthPct.toLocaleString("en-US")}%</td></tr>
`,
  );
  return html`<h3>How pay moves up this schedule</h3>
<p class="growth">${lead}</p>
<div class="table-scroll" role="region" aria-label="Pay growth by column" tabindex="0">
<table class="growth-table">
<caption>Each column from its first listed step to its top step.</caption>
<thead><tr><th scope="col">Column</th><th scope="col">First step</th><th scope="col">Top step</th><th scope="col">Steps to top</th><th scope="col">Growth</th></tr></thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
}

function rankPhrase(rank: Rank | null, where: string): string | null {
  if (!rank || rank.total < 2) {
    return null;
  }
  const pct = topPercent(rank);
  return `${ordinal(rank.rank)} of ${rank.total.toLocaleString("en-US")} ${where}${pct ? ` (${pct})` : ""}`;
}

/** Câu xếp hạng: lương khởi điểm và mức tối đa đứng thứ mấy trong bang và toàn quốc. */
export function rankText(data: DistrictPageData): string | null {
  const ranks = data.ranks;
  if (!ranks) {
    return null;
  }
  const state = data.district.state.name;
  const parts: string[] = [];
  const describe = (label: string, r: DistrictRanks["start"]) => {
    const places = [
      rankPhrase(r.state, `${state} districts`),
      rankPhrase(r.nation, "districts nationally"),
    ].filter((p): p is string => p !== null);
    if (places.length > 0) {
      parts.push(`${label} ranks ${places.join(" and ")}`);
    }
  };
  describe("Starting pay", ranks.start);
  describe(parts.length > 0 ? "the top of the scale" : "The top of the scale", ranks.max);
  return parts.length > 0 ? `${parts.join("; ")}, among districts on this site.` : null;
}

function chartBlock(schedule: Schedule): Html {
  const chart = payChart(schedule);
  return chart
    ? html`<h3>How pay grows with each step</h3>
${chart}`
    : html``;
}

function scheduleSections(data: DistrictPageData): Html {
  const many = data.schedules.length > 1;
  const sections: Html[] = [];
  for (const schedule of data.schedules) {
    const heading = scheduleHeading(schedule, many);
    const caption = `${data.district.name}, ${schoolYearLabel(data.year)}: ${heading}`;
    const chosen = data.selection?.scheduleId === schedule.id ? data.selection : null;
    const calc = calculator(schedule, {
      action: data.path,
      hidden: {},
      laneIndex: chosen?.laneIndex ?? 0,
      stepIndex: chosen?.stepIndex ?? 0,
    });
    const download = data.demo
      ? html``
      : html`<p class="download"><span>Download this table:</span> <a href="${xlsxPath(schedule.id)}" download rel="nofollow">Excel (.xlsx)</a> <a href="${csvPath(schedule.id)}" download rel="nofollow">CSV</a></p>`;
    const section = html`<section aria-labelledby="schedule-${schedule.id}-heading">
<h2 id="schedule-${schedule.id}-heading">${heading}</h2>
${scheduleTable(schedule, caption)}
${download}
${chartBlock(schedule)}
${growthBlock(schedule)}
<h3 id="calc-heading-${schedule.id}">Salary calculator</h3>
<p>${calcHint(schedule)}</p>
${calc}
${many ? html`<p class="back-link"><a href="#picker-heading">↑ All salary schedules</a></p>` : html``}
</section>
`;
    sections.push(section);
  }
  return html`${sections}`;
}

/** Khoảng cách hiển thị theo dặm (người đọc ở Mỹ); null khi không có số. */
export function distanceMiles(km: number | null): string | null {
  if (km === null || !Number.isFinite(km)) {
    return null;
  }
  const miles = km * 0.621371;
  return miles < 1 ? "under 1 mi" : `${Math.round(miles).toLocaleString("en-US")} mi`;
}

function neighborSection(data: DistrictPageData): Html {
  const { district, summary, neighbors } = data;
  if (!summary && neighbors.length === 0) {
    return html`<section aria-labelledby="nearby-heading">
<h2 id="nearby-heading">Nearby districts</h2>
<p>No nearby districts have comparable figures yet.</p>
</section>`;
  }
  const rows: Html[] = [];
  if (summary) {
    const name = html`${district.name} <span class="muted">(this district)</span>`;
    rows.push(benchmarkRow(name, summary, true));
  }
  const keys = [`${district.state.slug}/${district.slug}`];
  for (const neighbor of neighbors) {
    const href = districtPath(neighbor.stateSlug, neighbor.slug);
    const miles = distanceMiles(neighbor.distanceKm);
    const name = miles
      ? html`<a href="${href}">${neighbor.name}</a> <span class="muted distance">${miles}</span>`
      : html`<a href="${href}">${neighbor.name}</a>`;
    rows.push(benchmarkRow(name, neighbor.summary, false));
    if (keys.length < 4) {
      keys.push(`${neighbor.stateSlug}/${neighbor.slug}`);
    }
  }
  let compare = html``;
  if (keys.length > 1) {
    compare = html`<p><a href="/compare?d=${keys.join(",")}">Compare these districts at the same step and lane</a></p>`;
  }
  return html`<section aria-labelledby="nearby-heading">
<h2 id="nearby-heading">Nearby districts</h2>
<div class="table-scroll" role="region" aria-label="Nearby districts" tabindex="0">
<table>
<caption>Three benchmarks from each district’s latest published schedule, nearest districts first, with straight-line distance. A dash means the schedule has no such cell.</caption>
<thead>
<tr><th scope="col">District</th><th scope="col">School year</th><th scope="col">BA, step 1</th><th scope="col">MA, step 10</th><th scope="col">Maximum</th></tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>
${compare}
${pairList(data)}
</section>`;
}

function pairList(data: DistrictPageData): Html {
  const pairs = data.pairs ?? [];
  if (pairs.length === 0) {
    return html``;
  }
  return html`<p class="pairs"><span>Head-to-head:</span> ${pairs.map((p, i) => html`${i > 0 ? ", " : ""}<a href="${p.href}">${data.district.name} ${p.label}</a>`)}</p>`;
}

function detailSections(data: DistrictPageData): Html {
  const many = data.schedules.length > 1;
  const notes: Html[] = [];
  const sources: Html[] = [];
  const key = `${data.district.state.slug}/${data.district.slug}`;
  for (const schedule of data.schedules) {
    const label = many ? html`<h3>${scheduleHeading(schedule, many)}</h3>` : html``;
    if (hasStipendsOrNotes(schedule)) {
      notes.push(html`${label}${stipendsAndNotes(schedule)}`);
    }
    const report = data.reportsEnabled ? `/report?d=${key}&s=${schedule.id}` : null;
    const flagged = data.asReported.get(schedule.id) ?? [];
    sources.push(html`${label}${sourceBlock(schedule, report, flagged)}`);
  }
  let noteSection = html``;
  if (notes.length > 0) {
    noteSection = html`<section aria-labelledby="notes-heading">
<h2 id="notes-heading">Stipends and notes</h2>
<p>Quoted from the source document.</p>
${notes}
</section>`;
  }
  return html`${noteSection}
<section aria-labelledby="source-heading">
<h2 id="source-heading">Source</h2>
${sources}
</section>`;
}

/** "+$1,860 (+2.1%)" khi cả hai năm có mức tối đa; "—" khi thiếu. */
export function changeText(previous: number | null, current: number | null): string {
  if (previous === null || current === null || previous === 0) {
    return "—";
  }
  const diff = current - previous;
  const percent = (diff / previous) * 100;
  const sign = diff >= 0 ? "+" : "−";
  const pct = `${sign}${Math.abs(percent).toFixed(1)}%`;
  return `${sign}${formatCents(Math.abs(diff))} (${pct})`;
}

/**
 * Các năm học của học khu. Từ hai năm trở lên: bảng lương thấp nhất, cao nhất của từng năm và mức
 * tối đa tăng bao nhiêu so với năm trước, để thấy lương tăng thế nào qua các năm.
 */
export function historySection(data: DistrictPageData): Html {
  const base = districtPath(data.district.state.slug, data.district.slug);
  const years = [...data.history].sort((a, b) => a.schoolYear.localeCompare(b.schoolYear));
  if (years.length < 2) {
    return html`<section aria-labelledby="years-heading">
<h2 id="years-heading">Other school years</h2>
<p>No other school years have been published for this district yet.</p>
</section>`;
  }
  const rows: Html[] = [];
  let previous: number | null = null;
  for (const entry of years) {
    const href = entry.schoolYear === data.latestYear ? base : `${base}/${entry.schoolYear}`;
    const label = schoolYearLabel(entry.schoolYear);
    const name =
      entry.schoolYear === data.year
        ? html`${label} <span class="muted">(this page)</span>`
        : html`<a href="${href}">${label}</a>`;
    const low = entry.minCents === null ? "—" : formatCents(entry.minCents);
    const high = entry.maxCents === null ? "—" : formatCents(entry.maxCents);
    const change = rows.length === 0 ? "—" : changeText(previous, entry.maxCents);
    const own = entry.schoolYear === data.year ? raw(' class="self-row"') : "";
    rows.push(
      html`<tr${own}><th scope="row">${name}</th><td>${low}</td><td>${high}</td><td>${change}</td></tr>\n`,
    );
    previous = entry.maxCents;
  }
  return html`<section aria-labelledby="years-heading">
<h2 id="years-heading">Pay over the years</h2>
<div class="table-scroll" role="region" aria-label="Pay over the years" tabindex="0">
<table class="history">
<caption>Lowest and highest amounts on each year’s published teacher schedules, and how the top of the scale changed from the year before. A dash means the figure is not available or the schedule is not annual.</caption>
<thead>
<tr><th scope="col">School year</th><th scope="col">Lowest</th><th scope="col">Highest</th><th scope="col">Top of scale vs. year before</th></tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>
</section>`;
}

/** "2025-26" → "2025-07-01/2026-06-30": năm học Mỹ thường từ tháng 7 tới tháng 6. */
export function schoolYearInterval(year: string): string {
  const start = Number(year.slice(0, 4));
  return `${start}-07-01/${start + 1}-06-30`;
}

/**
 * Nút JSON-LD `Dataset` (PLAN Công đoạn 7): bảng lương là một tập dữ liệu nhỏ, có bản CSV tải
 * được và dựa trên tài liệu gốc của học khu.
 */
export function datasetNode(origin: string, data: DistrictPageData): object {
  const { district } = data;
  const path =
    data.year === data.latestYear
      ? districtPath(district.state.slug, district.slug)
      : `${districtPath(district.state.slug, district.slug)}/${data.year}`;
  const sources = data.schedules
    .map((s) => sourceLanding(s.source.url)?.href ?? safeHttpUrl(s.source.url))
    .filter((u): u is string => u !== null);
  return {
    "@type": "Dataset",
    name: districtTitle(district, data.year),
    description: districtDescription(data),
    url: `${origin}${path}`,
    temporalCoverage: schoolYearInterval(data.year),
    spatialCoverage: {
      "@type": "Place",
      name: placeLine(district.city, district.county, district.state.name),
    },
    creator: { "@type": "Organization", name: district.name },
    isBasedOn: [...new Set(sources)],
    variableMeasured: "Teacher salary by step and lane",
    keywords: [
      "teacher salary schedule",
      `${district.state.name} teacher pay`,
      `${district.name} salary`,
    ],
    isAccessibleForFree: true,
    // Điều khoản dùng lại (D-112, D-122): Google khuyên Dataset có `license`.
    license: `${origin}/terms`,
    distribution: data.schedules.flatMap((s) => [
      {
        "@type": "DataDownload",
        encodingFormat: "text/csv",
        contentUrl: `${origin}${csvPath(s.id)}`,
      },
      {
        "@type": "DataDownload",
        encodingFormat: XLSX_TYPE,
        contentUrl: `${origin}${xlsxPath(s.id)}`,
      },
    ]),
  };
}

function comparisonLine(data: DistrictPageData): Html {
  const text = stateComparison(data);
  const ranks = rankText(data);
  if (!text && !ranks) {
    return html``;
  }
  const state = data.district.state;
  const rankLine = ranks
    ? html`<p class="comparison">${ranks} <a href="/rankings">See the rankings</a>.</p>`
    : html``;
  const medianLine = text
    ? html`<p class="comparison">${text} <a href="/${state.slug}">Compare ${state.name} districts</a>.</p>`
    : html``;
  return html`${medianLine}${rankLine}`;
}

/**
 * Mục lục "On this page" dưới phần tóm tắt: trang học khu dài (bảng, máy tính, lân cận, nguồn,
 * các năm, câu hỏi), mục lục giúp nhảy thẳng tới phần cần xem.
 */
export function onThisPage(data: DistrictPageData): Html {
  const first = data.schedules[0];
  const many = data.schedules.length > 1;
  const links: Html[] = [];
  if (first) {
    const tableTarget = many ? "picker-heading" : `schedule-${first.id}-heading`;
    links.push(
      html`<a href="#${tableTarget}">${many ? "Salary schedules" : "Salary schedule"}</a>`,
    );
    links.push(html`<a href="#calc-heading-${first.id}">Calculator</a>`);
  }
  links.push(html`<a href="#nearby-heading">Nearby districts</a>`);
  if (data.schedules.some(hasStipendsOrNotes)) {
    links.push(html`<a href="#notes-heading">Stipends</a>`);
  }
  links.push(html`<a href="#source-heading">Source</a>`);
  links.push(
    html`<a href="#years-heading">${data.history.length > 1 ? "Past years" : "Other years"}</a>`,
  );
  links.push(html`<a href="#faq-heading">Questions</a>`);
  return html`<nav class="on-page" aria-label="On this page"><span>On this page</span>${links}</nav>`;
}

export function districtPage(site: Site, data: DistrictPageData): Html {
  const { district } = data;
  const crumbs = breadcrumbs([
    { label: "Home", href: "/" },
    { label: district.state.name, href: `/${district.state.slug}` },
    { label: district.name },
  ]);
  const place = placeLine(district.city, district.county, district.state.name);
  let notice = html``;
  if (data.demo) {
    notice = html`<p class="notice">Demo page with made-up data, shown only on preview deployments.</p>`;
  } else if (data.year !== data.latestYear) {
    const latest = districtPath(district.state.slug, district.slug);
    notice = html`<p class="notice">This is an earlier school year. <a href="${latest}">See the latest schedule (${schoolYearLabel(data.latestYear)})</a>.</p>`;
  }
  return html`${crumbs}
<h1>${districtTitle(district, data.year)}</h1>
<p class="lede">${place}</p>
${notice}
${summaryFacts(data.schedules)}
${comparisonLine(data)}
${onThisPage(data)}
${schedulePicker(data.schedules, data.year)}
${adSlot(site, "below-summary")}
${scheduleSections(data)}
${adSlot(site, "before-comparison")}
${neighborSection(data)}
${detailSections(data)}
${historySection(data)}
${morePayBlock(data.morePay ?? [])}
${faqSection(site.origin, { ...yearFacts(data.schedules), district, year: data.year, schedules: data.schedules, summary: data.summary }, data.demo ? [] : [datasetNode(site.origin, data)])}
${adSlot(site, "page-end")}`;
}

/** Học khu có trong danh mục nhưng chưa có bảng published: trang này luôn noindex. */
/** Trang cảm ơn sau khi gửi "Request this district" (D-121). */
export function requestThanksPage(district: District): Html {
  const base = districtPath(district.state.slug, district.slug);
  return html`<h1>Thanks, your request is recorded</h1>
<p class="lede">We count requests to decide which districts to add next. ${district.name} will be listed once we find and check its salary schedule.</p>
<p>We did not store anything about you, only that the district was requested today.</p>
<p><a href="${base}">Back to ${district.name}</a> · <a href="/${district.state.slug}">Other districts in ${district.state.name}</a></p>`;
}

export function missingSchedulePage(district: District, requests = 0): Html {
  const crumbs = breadcrumbs([
    { label: "Home", href: "/" },
    { label: district.state.name, href: `/${district.state.slug}` },
    { label: district.name },
  ]);
  const place = placeLine(district.city, district.county, district.state.name);
  const website = safeHttpUrl(district.website);
  const link = website
    ? html`<p>The district’s own website may have it: <a href="${website}" rel="nofollow noopener">${website}</a></p>`
    : html``;
  return html`${crumbs}
<h1>${district.name}</h1>
<p class="lede">${place}</p>
<p class="notice"><strong>Schedule not found.</strong> We have not published a salary schedule for this district yet.</p>
${link}
<section aria-labelledby="request-heading" class="request-box">
<h2 id="request-heading">Want this district added?</h2>
<p>Let us know you need it. Districts with more requests are added first.${requests > 0 ? ` Requested ${requests.toLocaleString("en-US")} ${requests === 1 ? "time" : "times"} so far.` : ""}</p>
<form method="post" action="${districtPath(district.state.slug, district.slug)}/request">
<button type="submit">Request this district</button>
</form>
</section>
<p><a href="/${district.state.slug}">Other districts in ${district.state.name}</a></p>`;
}
