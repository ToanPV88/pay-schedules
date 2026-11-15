/** Số liệu tổng hợp (trang chủ, trang bang) và trang "Recently updated". */
import type { Coverage, DistrictAmount, PayOverview, RecentDistrict } from "@pay-schedules/db";
import { html } from "hono/html";
import { formatCents, formatDate, plural, schoolYearLabel } from "../format";
import { breadcrumbs, type Html } from "./layout";
import { districtPath } from "./parts";

function money(cents: number | null): string {
  return cents === null ? "—" : formatCents(cents);
}

function districtLink(d: DistrictAmount, withState: boolean): Html {
  const state = withState ? html` <span class="muted">(${d.stateName})</span>` : html``;
  return html`<a href="${districtPath(d.stateSlug, d.slug)}">${d.name}</a>${state}`;
}

/**
 * Trung vị ba mốc và thấp nhất/cao nhất. `scope` là "across the site" hoặc "in {State}";
 * `withState` ghi bang cạnh tên học khu (trang chủ).
 */
export function payOverview(pay: PayOverview, scope: string, withState: boolean): Html {
  if (pay.start.districts === 0 && pay.max.districts === 0) {
    return html``;
  }
  const n = Math.max(pay.start.districts, pay.max.districts);
  const extremes: Html[] = [];
  if (pay.lowestStart && pay.highestStart && pay.start.districts > 1) {
    extremes.push(
      html`<li>Lowest starting salary: ${formatCents(pay.lowestStart.cents)} at ${districtLink(pay.lowestStart, withState)}</li>`,
    );
    extremes.push(
      html`<li>Highest starting salary: ${formatCents(pay.highestStart.cents)} at ${districtLink(pay.highestStart, withState)}</li>`,
    );
  }
  if (pay.highestMax && pay.max.districts > 1) {
    extremes.push(
      html`<li>Highest top of scale: ${formatCents(pay.highestMax.cents)} at ${districtLink(pay.highestMax, withState)}</li>`,
    );
  }
  const list = extremes.length > 0 ? html`<ul>${extremes}</ul>` : html``;
  return html`<section aria-labelledby="pay-heading">
<h2 id="pay-heading">Teacher pay ${scope}</h2>
<dl class="facts">
<div><dt>Median starting salary (BA, step 1)</dt><dd>${money(pay.start.cents)}</dd></div>
<div><dt>Median MA, step 10</dt><dd>${money(pay.maStep10.cents)}</dd></div>
<div><dt>Median top of scale</dt><dd>${money(pay.max.cents)}</dd></div>
</dl>
${list}
<p class="muted">Medians of the latest published teacher schedule of ${plural(n, "district", "districts")}: half of the districts pay more, half pay less. Only schedules stated as annual salaries are counted, since daily or hourly rates do not compare. Each figure comes from the district’s own document; see <a href="/methodology#state-medians">methodology</a>.</p>
</section>`;
}

/** "2,709 districts in 50 states, covering 16.3 million students." */
export function coverageLine(coverage: Coverage): string {
  const districts = plural(coverage.districts, "school district", "school districts");
  const states = plural(coverage.states, "state", "states");
  return `Salary schedules of ${districts} in ${states}, covering ${studentsLabel(coverage.students)}.`;
}

export function studentsLabel(students: number): string {
  if (students >= 1_000_000) {
    return `${(students / 1_000_000).toFixed(1)} million students`;
  }
  return plural(students, "student", "students");
}

function recentItem(item: RecentDistrict, withState: boolean): Html {
  const href = districtPath(item.stateSlug, item.slug);
  const where = [item.city, withState ? item.stateName : null].filter(Boolean).join(", ");
  const place = where ? html` <span class="muted">${where}</span>` : html``;
  const count = item.schedules > 1 ? ` · ${item.schedules} schedules` : "";
  return html`<li><a href="${href}">${item.name}</a>${place}<br><span class="muted">${schoolYearLabel(item.schoolYear)}${count} · updated ${formatDate(item.updatedAt)}</span></li>
`;
}

/** Danh sách học khu mới cập nhật; trống thì không hiện gì. */
export function recentList(items: RecentDistrict[], withState: boolean): Html {
  if (items.length === 0) {
    return html``;
  }
  return html`<ul class="result-list recent-list">
${items.map((item) => recentItem(item, withState))}</ul>`;
}

export const RECENT_PAGE_SIZE = 100;

export interface RecentPageData {
  items: RecentDistrict[];
  total: number;
  page: number;
}

export function recentPath(page: number): string {
  return page > 1 ? `/recently-updated?page=${page}` : "/recently-updated";
}

export function recentPage(data: RecentPageData): Html {
  const pages = Math.max(1, Math.ceil(data.total / RECENT_PAGE_SIZE));
  const pager: Html[] = [];
  if (data.page > 1) {
    pager.push(html`<a href="${recentPath(data.page - 1)}" rel="prev">Previous</a>`);
  }
  if (pages > 1) {
    pager.push(html`<span>Page ${data.page} of ${pages}</span>`);
  }
  if (data.page < pages) {
    pager.push(html`<a href="${recentPath(data.page + 1)}" rel="next">Next</a>`);
  }
  const pagination =
    pager.length > 0 ? html`<nav class="pagination" aria-label="Pages">${pager}</nav>` : html``;
  const list =
    data.items.length > 0 ? recentList(data.items, true) : html`<p>No schedules yet.</p>`;
  const crumbs = breadcrumbs([{ label: "Home", href: "/" }, { label: "Recently updated" }]);
  return html`${crumbs}
<h1>Recently updated salary schedules</h1>
<p class="lede">School districts whose teacher salary schedule was most recently added or updated on this site, newest first.</p>
${list}
${pagination}`;
}
