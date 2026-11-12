/** Trang chủ, trang bang, trang tìm kiếm và các trang lỗi. */
import type {
  DistrictListItem,
  DistrictSort,
  SearchHit,
  SortDirection,
  State,
  StateCount,
} from "@pay-schedules/db";
import { html } from "hono/html";
import { plural, schoolYearLabel } from "../format";
import { breadcrumbs, type Html } from "./layout";
import { districtPath, hitList, moneyCell, searchForm } from "./parts";

// ---------------------------------------------------------------- trang chủ

export function homePage(states: StateCount[]): Html {
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
  return html`<h1>Public school teacher salary schedules</h1>
<p class="lede">Look up the salary schedule a school district publishes, with a link to the source document for every table.</p>
${form}
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

export interface StatePageData {
  state: State;
  items: DistrictListItem[];
  totals: { districts: number; withSchedule: number };
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
    table = html`<div class="table-scroll" role="region" aria-label="Districts in ${state.name}" tabindex="0">
<table class="districts" data-sortable="${sortable}">
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
  return html`${crumbs}
<h1>${state.name} teacher salary schedules</h1>
<p class="lede">${withSchedule} of ${total} in ${state.name} have a published salary schedule on this site.</p>
${table}
${pagination}`;
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
  return html`<h1>Page not found</h1>
<p>The address may be mistyped, or the page may have moved.</p>
<p><a href="/">Home</a> · <a href="/search">Search school districts</a></p>`;
}

export function errorPage(): Html {
  return html`<h1>Something went wrong</h1>
<p>The page could not be loaded. Please try again in a moment.</p>
<p><a href="/">Home</a></p>`;
}
