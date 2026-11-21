/**
 * Trang phụ cấp huấn luyện viên và việc ngoài giờ của một học khu (PLAN Công đoạn 11):
 * `/{state}/{district}/coaching-stipends`. Hàng là vị trí, cột là mức kinh nghiệm hoặc "Amount".
 * Trang chỉ tồn tại khi học khu có bảng published; không có thì 404, không bao giờ vào sitemap.
 */
import type { Cell, District, Schedule } from "@pay-schedules/db";
import { html } from "hono/html";
import { formatCents, schoolYearLabel } from "../format";
import { adSlot, breadcrumbs, type Html, type Site } from "./layout";
import { districtPath, placeLine } from "./parts";
import { sourceBlock } from "./schedule";

export const COACHING_SLUG = "coaching-stipends";

export function coachingPath(stateSlug: string, districtSlug: string): string {
  return `${districtPath(stateSlug, districtSlug)}/${COACHING_SLUG}`;
}

function amountCell(cell: Cell | null): Html {
  if (cell?.amountCents !== null && cell?.amountCents !== undefined) {
    return html`<td>${formatCents(cell.amountCents)}</td>`;
  }
  return html`<td class="empty">—<span class="visually-hidden"> No amount in the source</span></td>`;
}

/** Bảng phụ cấp bằng thẻ table thật, đọc được khi tắt JavaScript. */
export function stipendTable(schedule: Schedule, caption: string): Html {
  const head =
    schedule.lanes.length === 0
      ? [html`<th scope="col">Amount</th>`]
      : schedule.lanes.map((lane) => html`<th scope="col">${lane.labelRaw}</th>`);
  const rows = schedule.steps.map(
    (step, i) =>
      html`<tr><th scope="row">${step.labelRaw}</th>${(schedule.cells[i] ?? []).map(amountCell)}</tr>\n`,
  );
  const scroll = schedule.steps.length > 12 ? "table-scroll tall" : "table-scroll";
  return html`<div class="${scroll}" role="region" aria-label="${caption}" tabindex="0">
<table class="schedule" id="stipends-${schedule.id}">
<caption>${caption}</caption>
<thead><tr><th scope="col">Position</th>${head}</tr></thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
}

/** Khoảng phụ cấp (nhỏ nhất, lớn nhất) trên mọi bảng; null khi không có số nào. */
export function stipendRange(schedules: Schedule[]): { min: number; max: number } | null {
  const amounts = schedules.flatMap((s) =>
    s.cells.flatMap((row) => row.map((c) => c?.amountCents ?? null)),
  );
  const nums = amounts.filter((a): a is number => a !== null);
  if (nums.length === 0) {
    return null;
  }
  return { min: Math.min(...nums), max: Math.max(...nums) };
}

export function coachingTitle(district: District, year: string): string {
  return `${district.name} Coaching Stipends ${schoolYearLabel(year)}`;
}

export function coachingDescription(district: District, schedules: Schedule[]): string {
  const year = schedules[0]?.schoolYear ?? "";
  const range = stipendRange(schedules);
  const rows = schedules.reduce((n, s) => n + s.steps.length, 0);
  const span = range ? ` from ${formatCents(range.min)} to ${formatCents(range.max)}` : "";
  return `${district.name} (${district.state.code}) coaching and extra-duty stipends for ${schoolYearLabel(year)}: ${rows} positions${span}, from the district's published document.`;
}

export function coachingPage(site: Site, district: District, schedules: Schedule[]): Html {
  const base = districtPath(district.state.slug, district.slug);
  const year = schedules[0]?.schoolYear ?? "";
  const crumbs = breadcrumbs([
    { label: "Home", href: "/" },
    { label: district.state.name, href: `/${district.state.slug}` },
    { label: district.name, href: base },
    { label: "Coaching stipends" },
  ]);
  const many = schedules.length > 1;
  const range = stipendRange(schedules);
  const tables = schedules.map((s) => {
    const heading = many ? html`<h2 id="stipends-${s.id}-heading">${s.title}</h2>` : html``;
    return html`<section>
${heading}
${stipendTable(s, `${s.title}, ${schoolYearLabel(s.schoolYear)}`)}
</section>`;
  });
  const sources = schedules.map(
    (s) => html`${many ? html`<h3>${s.title}</h3>` : html``}${sourceBlock(s, null)}`,
  );
  const lede = range
    ? html`<p>Stipends paid on top of salary for coaching and other extra duties, as printed by the district. Amounts run from <strong>${formatCents(range.min)}</strong> to <strong>${formatCents(range.max)}</strong> a season or year.</p>`
    : html``;
  return html`${crumbs}
<h1>${coachingTitle(district, year)}</h1>
<p class="lede">${placeLine(district.city, district.county, district.state.name)}</p>
${lede}
<p><a href="${base}">Teacher salary schedule for ${district.name}</a></p>
${adSlot(site, "below-summary")}
${tables}
<section aria-labelledby="source-heading">
<h2 id="source-heading">Source</h2>
${sources}
</section>
${adSlot(site, "page-end")}`;
}

/** Khối "More pay at this district" trên trang học khu; rỗng khi không có trang nào. */
export function morePayBlock(links: { href: string; label: string }[]): Html {
  if (links.length === 0) {
    return html``;
  }
  return html`<section aria-labelledby="more-pay-heading">
<h2 id="more-pay-heading">More pay at this district</h2>
<ul>${links.map((l) => html`<li><a href="${l.href}">${l.label}</a></li>`)}</ul>
</section>`;
}
