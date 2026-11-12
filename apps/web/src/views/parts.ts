/** Mảnh HTML dùng chung giữa các trang. */
import type { SearchHit, Summary } from "@pay-schedules/db";
import { html, raw } from "hono/html";
import { formatCents, schoolYearLabel } from "../format";
import type { Html } from "./layout";

export function districtPath(stateSlug: string, districtSlug: string): string {
  return `/${stateSlug}/${districtSlug}`;
}

/** "Testville, Test County, Test State": bỏ phần nào dữ liệu không có. */
export function placeLine(city: string | null, county: string | null, state: string): string {
  const parts: string[] = [];
  if (city) {
    parts.push(city);
  }
  if (county) {
    parts.push(county);
  }
  parts.push(state);
  return parts.join(", ");
}

/** Ô tiền trong bảng so sánh. `data-sort-value` để `site.js` sắp xếp; ô thiếu số luôn xếp cuối. */
export function moneyCell(cents: number | null): Html {
  if (cents === null) {
    return html`<td class="empty" data-sort-value="">—</td>`;
  }
  return html`<td data-sort-value="${cents}">${formatCents(cents)}</td>`;
}

/** Một dòng của bảng ba mốc so sánh (BA bậc 1, MA bậc 10, tối đa). */
export function benchmarkRow(name: Html, summary: Summary | null, own: boolean): Html {
  const year = summary ? schoolYearLabel(summary.schoolYear) : "";
  const start = moneyCell(summary?.startBaCents ?? null);
  const ma10 = moneyCell(summary?.maStep10Cents ?? null);
  const max = moneyCell(summary?.maxSalaryCents ?? null);
  const rowClass = own ? raw(' class="self-row"') : "";
  return html`<tr${rowClass}><th scope="row">${name}</th><td>${year}</td>${start}${ma10}${max}</tr>\n`;
}

export interface SearchFormOptions {
  action: string;
  query: string;
  label: string;
  /** Trường ẩn gửi kèm (trang /compare giữ danh sách học khu đang so). */
  hidden?: Record<string, string>;
  button?: string;
}

export function searchForm(options: SearchFormOptions): Html {
  const hidden: Html[] = [];
  for (const [name, value] of Object.entries(options.hidden ?? {})) {
    hidden.push(html`<input type="hidden" name="${name}" value="${value}">`);
  }
  const button = options.button ?? "Search";
  return html`<form class="search-form" method="get" action="${options.action}" role="search">
${hidden}<label for="q">${options.label}</label>
<div class="search-row">
<input id="q" name="q" type="search" value="${options.query}" maxlength="80" autocomplete="off" required>
<button type="submit">${button}</button>
</div>
</form>`;
}

/** Danh sách kết quả tìm kiếm; `hrefOf` quyết định mỗi kết quả trỏ đi đâu. */
export function hitList(hits: SearchHit[], hrefOf: (hit: SearchHit) => string): Html {
  const items: Html[] = [];
  for (const hit of hits) {
    const place = placeLine(hit.city, hit.county, hit.state.name);
    const badge = hit.hasSchedule ? html`` : html` <span class="badge">No schedule yet</span>`;
    const item = html`<li><a href="${hrefOf(hit)}">${hit.name}</a>${badge}<br><span class="muted">${place}</span></li>\n`;
    items.push(item);
  }
  return html`<ul class="result-list">
${items}</ul>`;
}
