/** Trang chủ, trang bang, trang tìm kiếm và các trang lỗi. */
import type {
  Coverage,
  DistrictListItem,
  DistrictSort,
  LargeDistrict,
  PayOverview,
  RecentDistrict,
  SearchHit,
  SortDirection,
  State,
  StateCount,
} from "@pay-schedules/db";
import { html } from "hono/html";
import { formatCents, plural, schoolYearLabel } from "../format";
import { breadcrumbs, type Html } from "./layout";
import { coverageLine, payOverview, recentList } from "./overview";
import { benchmarkRow, districtPath, hitList, moneyCell, searchForm } from "./parts";

// ---------------------------------------------------------------- trang chủ

/** "19.1M", "850K", "640": số học sinh gọn cho ô thống kê ở trang chủ. */
export function studentsShort(students: number): string {
  if (students >= 1_000_000) {
    return `${(students / 1_000_000).toFixed(1)}M`;
  }
  if (students >= 10_000) {
    return `${Math.round(students / 1000)}K`;
  }
  return students.toLocaleString("en-US");
}

export interface HomePageData {
  states: StateCount[];
  coverage: Coverage;
  pay: PayOverview;
  recent: RecentDistrict[];
  /** Học khu đông học sinh nhất có số liệu: bảng mẫu ở trang chủ. */
  largest?: LargeDistrict[];
}

export const HOME_RECENT = 8;
export const HOME_LARGEST = 10;

/** Bảng mẫu ở trang chủ: ba mốc lương của các học khu lớn nhất, cùng cột với bảng của trang bang. */
export function largestTable(items: LargeDistrict[]): Html {
  if (items.length === 0) {
    return html``;
  }
  const rows = items.map((item) => {
    const href = districtPath(item.stateSlug, item.slug);
    const name = html`<a href="${href}">${item.name}</a> <span class="muted">${item.stateCode}</span>`;
    return benchmarkRow(name, item.summary, false);
  });
  return html`<section aria-labelledby="largest-heading">
<h2 id="largest-heading">The largest districts at a glance</h2>
<p>Three points on each district’s latest schedule: where a new teacher with a bachelor’s degree starts, a master’s degree at step 10, and the top of the scale.</p>
<div class="table-scroll" role="region" aria-label="Largest districts" tabindex="0">
<table class="districts benchmarks">
<caption>The ${items.length} largest school districts by enrollment whose latest schedule shows a starting salary for a bachelor’s degree. A dash means the schedule has no such cell.</caption>
<thead>
<tr><th scope="col">District</th><th scope="col">School year</th><th scope="col">BA, step 1</th><th scope="col">MA, step 10</th><th scope="col">Maximum</th></tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>
</section>`;
}

export function homePage(data: HomePageData): Html {
  const { states, coverage } = data;
  const items: Html[] = [];
  for (const state of states) {
    const total = plural(state.districts, "district", "districts");
    const count = `${state.withSchedule.toLocaleString("en-US")} of ${total} with a schedule`;
    const item = html`<li><a href="/${state.slug}">${state.name}</a> <span class="muted">${count}</span></li>\n`;
    items.push(item);
  }
  let stateList = html`<p>No states have been loaded yet.</p>`;
  if (items.length > 0) {
    stateList = html`<ul class="state-list">
${items}</ul>`;
  }
  const form = searchForm({
    action: "/search",
    query: "",
    label: "Find a school district by name, city or county",
  });
  const lede =
    coverage.districts > 0
      ? `${coverageLine(coverage)} Every table links to the document it came from.`
      : "Look up the salary schedule a school district publishes, with a link to the source document for every table.";
  let recent = html``;
  if (data.recent.length > 0) {
    recent = html`<section aria-labelledby="recent-heading">
<h2 id="recent-heading">Recently updated</h2>
${recentList(data.recent, true)}
<p><a href="/recently-updated">All recently updated districts</a></p>
</section>`;
  }
  let stats = html``;
  if (coverage.districts > 0) {
    stats = html`<dl class="stats">
<div><dt>School districts</dt><dd>${coverage.districts.toLocaleString("en-US")}</dd></div>
<div><dt>States</dt><dd>${coverage.states.toLocaleString("en-US")}</dd></div>
<div><dt>Students covered</dt><dd>${studentsShort(coverage.students)}</dd></div>
</dl>`;
  }
  return html`<div class="hero">
<h1>Public school teacher salary schedules</h1>
<p class="lede">${lede}</p>
${form}
${stats}
</div>
${payOverview(data.pay, "across the site", true)}
${largestTable(data.largest ?? [])}
${recent}
<section aria-labelledby="states-heading">
<h2 id="states-heading">Browse by state</h2>
${stateList}
</section>
<section aria-labelledby="reading-heading">
<h2 id="reading-heading">How to read a salary schedule</h2>
<p>Most districts pay teachers from a grid. Each row is a <strong>step</strong>, which usually tracks years of credited experience. Each column is a <strong>lane</strong>, which tracks education, such as a bachelor’s degree (BA), a master’s degree (MA) or a master’s degree plus 30 graduate credits (MA+30).</p>
<p>Your salary is the cell where your step and your lane meet. Districts differ in how they credit experience from other employers and in which credits count toward a lane, so the district’s own document is the authority.</p>
<p>Every table on this site links to the document it came from. See <a href="/methodology">how the data is collected and checked</a>.</p>
</section>`;
}

// ---------------------------------------------------------------- trang bang

export const STATE_PAGE_SIZE = 200;
export const STATE_RECENT = 6;

export interface StatePageData {
  state: State;
  pay: PayOverview;
  recent: RecentDistrict[];
  items: DistrictListItem[];
  totals: {
    districts: number;
    withSchedule: number;
  };
  /** Học khu xếp theo lương khởi điểm và theo mức tối đa, giảm dần (cho hai bảng xếp hạng). */
  topStart?: DistrictListItem[];
  topMax?: DistrictListItem[];
  sort: DistrictSort;
  dir: SortDirection;
  /** Trang hiện tại, đếm từ 1. */
  page: number;
}

/** Đường dẫn trang bang với cách sắp xếp và số trang; tham số mặc định thì bỏ khỏi URL. */
export function statePath(
  slug: string,
  sort: DistrictSort,
  dir: SortDirection,
  page: number,
): string {
  const params: string[] = [];
  if (sort !== "name" || dir !== "asc") {
    params.push(`sort=${sort}`, `dir=${dir}`);
  }
  if (page > 1) {
    params.push(`p=${page}`);
  }
  return params.length > 0 ? `/${slug}?${params.join("&")}` : `/${slug}`;
}

function sortHeader(data: StatePageData, key: DistrictSort, label: string): Html {
  const active = data.sort === key;
  const firstDirection: SortDirection = key === "name" ? "asc" : "desc";
  let next = firstDirection;
  if (active) {
    next = data.dir === "asc" ? "desc" : "asc";
  }
  const href = statePath(data.state.slug, key, next, 1);
  if (!active) {
    return html`<th scope="col"><a href="${href}" data-sort-first="${firstDirection}">${label}</a></th>`;
  }
  const aria = data.dir === "asc" ? "ascending" : "descending";
  return html`<th scope="col" aria-sort="${aria}"><a href="${href}" data-sort-first="${firstDirection}">${label}</a></th>`;
}

/** Thanh độ phủ của bang: bao nhiêu phần trăm học khu đã có bảng lương trên site. */
export function coverageMeter(totals: { districts: number; withSchedule: number }): Html {
  if (totals.districts === 0) {
    return html``;
  }
  const percent = Math.round((totals.withSchedule / totals.districts) * 100);
  return html`<div class="coverage">
<div class="coverage-bar" role="img" aria-label="${percent}% of districts have a published schedule"><span style="width: ${percent}%"></span></div>
<p class="muted">${percent}% of districts covered so far. We add districts as we find and check their documents.</p>
</div>`;
}

/** Số học khu tối thiểu để một danh sách xếp hạng của bang đáng hiện. */
export const TOP_MIN = 3;
export const TOP_LIMIT = 10;

function topList(
  stateSlug: string,
  items: DistrictListItem[],
  amountOf: (item: DistrictListItem) => number | null,
): Html | null {
  const ranked = items
    .map((item) => ({ item, cents: amountOf(item) }))
    .filter((x): x is { item: DistrictListItem; cents: number } => x.cents !== null)
    .slice(0, TOP_LIMIT);
  if (ranked.length < TOP_MIN) {
    return null;
  }
  const rows = ranked.map(
    ({ item, cents }) =>
      html`<li><a href="${districtPath(stateSlug, item.slug)}">${item.name}</a><span>${formatCents(cents)}</span></li>\n`,
  );
  return html`<ol class="top-list">
${rows}</ol>`;
}

/** Hai bảng xếp hạng của bang: lương khởi điểm (BA, bậc 1) và mức tối đa cao nhất. */
export function stateTopLists(
  state: State,
  topStart: DistrictListItem[],
  topMax: DistrictListItem[],
): Html {
  const start = topList(state.slug, topStart, (i) => i.summary?.startBaCents ?? null);
  const max = topList(state.slug, topMax, (i) => i.summary?.maxSalaryCents ?? null);
  if (!start && !max) {
    return html``;
  }
  const blocks: Html[] = [];
  if (start) {
    blocks.push(html`<div><h3>Highest starting salary (BA, step 1)</h3>${start}</div>`);
  }
  if (max) {
    blocks.push(html`<div><h3>Highest top of the scale</h3>${max}</div>`);
  }
  return html`<section aria-labelledby="top-heading">
<h2 id="top-heading">Highest-paying districts in ${state.name}</h2>
<div class="top-lists">${blocks}</div>
<p class="muted">From each district’s latest published teacher schedule. Districts without that figure are not ranked; amounts are not adjusted for cost of living.</p>
</section>`;
}

export function statePage(data: StatePageData): Html {
  const { state, totals } = data;
  const rows: Html[] = [];
  for (const item of data.items) {
    const href = districtPath(state.slug, item.slug);
    const year = item.summary ? schoolYearLabel(item.summary.schoolYear) : "";
    const flag = item.hasSchedule ? html`` : html` <span class="badge">No schedule yet</span>`;
    const sortName = item.name.toLowerCase();
    const start = moneyCell(item.summary?.startBaCents ?? null);
    const ma10 = moneyCell(item.summary?.maStep10Cents ?? null);
    const max = moneyCell(item.summary?.maxSalaryCents ?? null);
    const row = html`<tr>
<th scope="row" data-sort-value="${sortName}"><a href="${href}">${item.name}</a>${flag}</th>
<td>${item.city ?? ""}</td><td>${year}</td>${start}${ma10}${max}
</tr>
`;
    rows.push(row);
  }
  const pages = Math.max(1, Math.ceil(totals.districts / STATE_PAGE_SIZE));
  // Sắp xếp bằng JavaScript chỉ đúng khi mọi dòng nằm trên một trang; nhiều trang thì để server sắp.
  const sortable = pages === 1 ? "true" : "false";
  const pager: Html[] = [];
  if (data.page > 1) {
    const prev = statePath(state.slug, data.sort, data.dir, data.page - 1);
    pager.push(html`<a href="${prev}" rel="prev">Previous</a>`);
  }
  if (pages > 1) {
    pager.push(html`<span>Page ${data.page} of ${pages}</span>`);
  }
  if (data.page < pages) {
    const next = statePath(state.slug, data.sort, data.dir, data.page + 1);
    pager.push(html`<a href="${next}" rel="next">Next</a>`);
  }
  let pagination = html``;
  if (pager.length > 0) {
    pagination = html`<nav class="pagination" aria-label="Pages">${pager}</nav>`;
  }
  const total = plural(totals.districts, "district", "districts");
  const withSchedule = totals.withSchedule.toLocaleString("en-US");
  let table = html`<p>No districts have been loaded for this state yet.</p>`;
  if (rows.length > 0) {
    // Ô lọc chỉ hiện khi có JavaScript (site.js bỏ `hidden`); không có JavaScript thì dùng tìm kiếm.
    const scope = pages > 1 ? " on this page" : "";
    table = html`<div class="table-filter" hidden>
<label for="district-filter">Filter districts${scope} by name or city</label>
<input id="district-filter" type="search" autocomplete="off" data-filter-table="districts-table">
<p class="muted" data-filter-count aria-live="polite"></p>
</div>
<div class="table-scroll" role="region" aria-label="Districts in ${state.name}" tabindex="0">
<table class="districts" id="districts-table" data-sortable="${sortable}">
<caption>Benchmarks come from each district’s latest published schedule. Select a column heading to sort.</caption>
<thead>
<tr>${sortHeader(data, "name", "District")}<th scope="col">City</th><th scope="col">School year</th>${sortHeader(data, "start", "BA, step 1")}${sortHeader(data, "ma10", "MA, step 10")}${sortHeader(data, "max", "Maximum")}</tr>
</thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
  }
  const crumbs = breadcrumbs([{ label: "Home", href: "/" }, { label: state.name }]);
  let recent = html``;
  if (data.recent.length > 0) {
    recent = html`<section aria-labelledby="recent-heading">
<h2 id="recent-heading">Recently updated in ${state.name}</h2>
${recentList(data.recent, false)}
</section>`;
  }
  const listHeading =
    rows.length > 0 ? html`<h2 id="districts-heading">Districts in ${state.name}</h2>` : html``;
  return html`${crumbs}
<h1>${state.name} teacher salary schedules</h1>
<p class="lede">${withSchedule} of ${total} in ${state.name} have a published salary schedule on this site.</p>
${coverageMeter(totals)}
${payOverview(data.pay, `in ${state.name}`, false)}
${stateTopLists(state, data.topStart ?? [], data.topMax ?? [])}
${listHeading}
${table}
${pagination}
${recent}`;
}

// ---------------------------------------------------------------- tìm kiếm

export const SEARCH_LIMIT = 50;

export function searchPage(query: string, hits: SearchHit[]): Html {
  const form = searchForm({ action: "/search", query, label: "District name, city or county" });
  let results = html``;
  if (query !== "") {
    results = html`<p>No districts match “${query}”. Try fewer words or check the spelling.</p>`;
    if (hits.length > 0) {
      const list = hitList(hits, (hit) => districtPath(hit.state.slug, hit.slug));
      const shown = plural(hits.length, "district", "districts");
      const capped = hits.length === SEARCH_LIMIT;
      const more = capped ? " (first results only; add a word to narrow)" : "";
      results = html`<p>${shown} found${more}.</p>
${list}`;
    }
  }
  return html`<h1>Search school districts</h1>
${form}
${results}`;
}

// ---------------------------------------------------------------- lỗi

export function notFoundPage(): Html {
  const form = searchForm({
    action: "/search",
    query: "",
    label: "Find a school district by name, city or county",
  });
  return html`<h1>Page not found</h1>
<p class="lede">The address may be mistyped, or the page may have moved. Try finding the district instead.</p>
${form}
<ul class="chip-list">
<li><a href="/#states-heading">Browse by state</a></li>
<li><a href="/recently-updated">Recently updated</a></li>
<li><a href="/compare">Compare districts</a></li>
<li><a href="/calculator">Salary calculator</a></li>
<li><a href="/">Home</a></li>
</ul>`;
}

export function errorPage(): Html {
  return html`<h1>Something went wrong</h1>
<p>The page could not be loaded. Please try again in a moment.</p>
<p><a href="/">Home</a></p>`;
}
