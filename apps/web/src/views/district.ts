/** Trang học khu (PLAN Công đoạn 6: tám phần theo thứ tự) và trang "schedule not found". */
import type {
  District,
  Neighbor,
  PayBasis,
  Schedule,
  Summary,
  YearHistory,
} from "@pay-schedules/db";
import { html } from "hono/html";
import { scheduleRange } from "../calc";
import { formatCents, payBasisNoun, safeHttpUrl, schoolYearLabel } from "../format";
import { adSlot, breadcrumbs, type Html, type Site } from "./layout";
import { benchmarkRow, districtPath, placeLine } from "./parts";
import {
  calculator,
  hasStipendsOrNotes,
  scheduleTable,
  sourceBlock,
  stipendsAndNotes,
} from "./schedule";

export interface Selection {
  scheduleId: number;
  laneIndex: number;
  stepIndex: number;
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
  /** Đường dẫn nhận form máy tính (chính trang này). */
  path: string;
  /** Trang mẫu với dữ liệu giả lập (chỉ ở bản xem trước). */
  demo: boolean;
}

export function districtTitle(district: District, year: string): string {
  return `${district.name} Teacher Salary Schedule ${schoolYearLabel(year)}`;
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
    const section = html`<section aria-labelledby="schedule-${schedule.id}-heading">
<h2 id="schedule-${schedule.id}-heading">${heading}</h2>
${scheduleTable(schedule, caption)}
<h3>Salary calculator</h3>
<p>Pick a lane and a step to read the amount from the table above.</p>
${calc}
</section>
`;
    sections.push(section);
  }
  return html`${sections}`;
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
    const name = html`<a href="${href}">${neighbor.name}</a>`;
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
<caption>Three benchmarks from each district’s latest published schedule. A dash means the schedule has no such cell.</caption>
<thead>
<tr><th scope="col">District</th><th scope="col">School year</th><th scope="col">BA, step 1</th><th scope="col">MA, step 10</th><th scope="col">Maximum</th></tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>
${compare}
</section>`;
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
    sources.push(html`${label}${sourceBlock(schedule, report)}`);
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

function historySection(data: DistrictPageData): Html {
  const base = districtPath(data.district.state.slug, data.district.slug);
  const items: Html[] = [];
  for (const entry of data.history) {
    if (entry.schoolYear === data.year) {
      continue;
    }
    const href = entry.schoolYear === data.latestYear ? base : `${base}/${entry.schoolYear}`;
    let range = "";
    if (entry.minCents !== null && entry.maxCents === entry.minCents) {
      range = `: ${formatCents(entry.minCents)}`;
    } else if (entry.minCents !== null && entry.maxCents !== null) {
      range = `: ${formatCents(entry.minCents)} to ${formatCents(entry.maxCents)}`;
    }
    items.push(html`<li><a href="${href}">${schoolYearLabel(entry.schoolYear)}</a>${range}</li>\n`);
  }
  let list = html`<p>No other school years have been published for this district yet.</p>`;
  if (items.length > 0) {
    list = html`<ul>
${items}</ul>`;
  }
  return html`<section aria-labelledby="years-heading">
<h2 id="years-heading">Other school years</h2>
${list}
</section>`;
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
${adSlot(site, "below-summary")}
${scheduleSections(data)}
${adSlot(site, "before-comparison")}
${neighborSection(data)}
${detailSections(data)}
${historySection(data)}
${adSlot(site, "page-end")}`;
}

/** Học khu có trong danh mục nhưng chưa có bảng published: trang này luôn noindex. */
export function missingSchedulePage(district: District): Html {
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
<p><a href="/${district.state.slug}">Other districts in ${district.state.name}</a></p>`;
}
