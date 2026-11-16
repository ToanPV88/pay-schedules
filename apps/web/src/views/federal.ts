/**
 * Trang bảng lương liên bang (DECISIONS.md D-065): OPM General Schedule (bảng cơ bản và vùng
 * locality) và bảng lương y tá VA theo cơ sở. Bảng là thẻ table thật, đọc được khi tắt JavaScript.
 */
import type { PayTable, PayTableInfo, VaStation } from "@pay-schedules/db";
import { html } from "hono/html";
import { formatCents } from "../format";
import { breadcrumbs, type Html } from "./layout";

export const FEDERAL_PATH = "/federal-pay";
export const VA_NURSE_PATH = "/va-nurse-pay";

export function gsPath(slug: string): string {
  return `${FEDERAL_PATH}/gs/${slug}`;
}

export function vaStationPath(groupSlug: string): string {
  return `${VA_NURSE_PATH}/${groupSlug}`;
}

function safeHttpUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

function dateText(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
      });
}

/** Bảng ngạch × bậc. Ô có chú thích (vd. "*": trần lương) hiện dấu sao và title. */
export function payTableHtml(table: PayTable, caption: string): Html {
  const head = table.cols.map((c) => html`<th scope="col">${c}</th>`);
  const rows = table.rows.map((label, i) => {
    const cells = (table.cells[i] ?? []).map((cell) => {
      if (!cell) {
        return html`<td class="empty">—<span class="visually-hidden"> No amount in the source</span></td>`;
      }
      const mark = cell.note
        ? html`<sup title="${table.notes ?? cell.note}">${cell.note}</sup>`
        : "";
      return html`<td data-cents="${cell.cents}">${formatCents(cell.cents)}${mark}</td>`;
    });
    return html`<tr><th scope="row">${label}</th>${cells}</tr>\n`;
  });
  return html`<div class="table-scroll" role="region" aria-label="${caption}" tabindex="0">
<table class="schedule" id="pay-${table.id}">
<caption>${caption}</caption>
<thead><tr><th scope="col">${table.rowHeader}</th>${head}</tr></thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
}

function sourceFacts(table: PayTable, publisher: string): Html {
  const url = safeHttpUrl(table.sourceUrl);
  const link = url
    ? html`<a href="${url}" rel="nofollow noopener">${publisher}</a> (official ${url.endsWith(".xlsx") ? "workbook" : "table"})`
    : html`${table.sourceUrl}`;
  const effective = table.effectiveDate
    ? html`<div><dt>Effective</dt><dd>${dateText(table.effectiveDate)}</dd></div>`
    : "";
  const notes = table.notes
    ? html`<div><dt>Note in the source</dt><dd>${table.notes}</dd></div>`
    : "";
  return html`<dl class="facts source">
<div><dt>Source</dt><dd>${link}</dd></div>
<div><dt>Title in the source</dt><dd>${table.title}</dd></div>
${effective}${notes}
<div><dt>Retrieved</dt><dd>${dateText(table.fetchedAt)}</dd></div>
</dl>`;
}

/** Hàng thấp nhất / cao nhất của một bảng, cho phần tóm tắt. */
function range(table: PayTable): { low: number | null; high: number | null } {
  const values = table.cells.flat().flatMap((c) => (c ? [c.cents] : []));
  return {
    low: values.length ? Math.min(...values) : null,
    high: values.length ? Math.max(...values) : null,
  };
}

// ---------------------------------------------------------------- General Schedule

export interface FederalIndexData {
  year: number;
  base: PayTable | null;
  localities: PayTableInfo[];
  vaYear: number | null;
}

export function federalIndexPage(data: FederalIndexData): Html {
  const crumbs = breadcrumbs([{ label: "Home", href: "/" }, { label: "Federal pay" }]);
  const list = data.localities.map((t) => html`<li><a href="${gsPath(t.slug)}">${t.name}</a></li>`);
  const base = data.base
    ? html`<h2>${data.year} General Schedule base pay</h2>
<p>The base table applies before locality pay. Almost every GS employee also receives a locality
payment, so check the table for your locality pay area below.</p>
${payTableHtml(data.base, `${data.year} General Schedule annual rates by grade and step (base, before locality pay)`)}
${sourceFacts(data.base, "U.S. Office of Personnel Management")}`
    : "";
  const va = data.vaYear
    ? html`<h2>VA nurse pay</h2>
<p>Registered nurses at the Department of Veterans Affairs are paid on local nurse pay schedules
set by each VA facility. <a href="${VA_NURSE_PATH}">See ${data.vaYear} VA nurse pay by facility</a>.</p>`
    : "";
  return html`${crumbs}
<h1>Federal pay tables ${data.year}</h1>
<p class="lead">Official ${data.year} General Schedule (GS) pay tables from the U.S. Office of
Personnel Management: the base table and every locality pay area, by grade and step.</p>
${base}
<h2 id="localities">${data.year} GS locality pay tables</h2>
<ul class="columns">${list}</ul>
${va}`;
}

export interface GsLocalityData {
  table: PayTable;
  localities: PayTableInfo[];
}

export function gsLocalityPage(data: GsLocalityData): Html {
  const { table } = data;
  const name = table.family === "gs" ? "General Schedule base" : table.name;
  const crumbs = breadcrumbs([
    { label: "Home", href: "/" },
    { label: "Federal pay", href: FEDERAL_PATH },
    { label: name },
  ]);
  const { low, high } = range(table);
  const others = data.localities
    .filter((t) => t.slug !== table.slug)
    .map((t) => html`<li><a href="${gsPath(t.slug)}">${t.name}</a></li>`);
  const summary =
    low !== null && high !== null
      ? html`<p class="lead">In ${table.year}, General Schedule annual pay in the ${name} locality pay
area runs from ${formatCents(low)} (GS-1, step 1) to ${formatCents(high)}.</p>`
      : "";
  return html`${crumbs}
<h1>${table.year} GS pay: ${name}</h1>
${summary}
${payTableHtml(table, `${table.year} General Schedule annual rates by grade and step, ${name}`)}
${sourceFacts(table, "U.S. Office of Personnel Management")}
<h2>Other locality pay areas</h2>
<ul class="columns">${others}</ul>`;
}

// ---------------------------------------------------------------- VA nurses

export function vaIndexPage(year: number, stations: VaStation[]): Html {
  const crumbs = breadcrumbs([
    { label: "Home", href: "/" },
    { label: "Federal pay", href: FEDERAL_PATH },
    { label: "VA nurse pay" },
  ]);
  const rows = stations.map(
    (s) => html`<tr><th scope="row"><a href="${vaStationPath(s.groupSlug)}">${s.name}</a></th>
<td>${s.stateName ?? "—"}</td><td>${s.tables}</td>
<td>${s.minCents === null ? "—" : formatCents(s.minCents)}</td>
<td>${s.maxCents === null ? "—" : formatCents(s.maxCents)}</td></tr>\n`,
  );
  return html`${crumbs}
<h1>VA nurse pay ${year} by facility</h1>
<p class="lead">Each VA facility sets locality pay schedules for its registered nurses (Title 38).
These are the official ${year} schedules published by the VA Office of the Chief Human Capital
Officer, by facility (station).</p>
<div class="table-scroll" role="region" aria-label="VA facilities" tabindex="0">
<table class="listing">
<thead><tr><th scope="col">Facility</th><th scope="col">State</th><th scope="col">Schedules</th>
<th scope="col">Lowest</th><th scope="col">Highest</th></tr></thead>
<tbody>
${rows}</tbody>
</table>
</div>`;
}

export function vaStationPage(name: string, tables: PayTable[]): Html {
  const crumbs = breadcrumbs([
    { label: "Home", href: "/" },
    { label: "Federal pay", href: FEDERAL_PATH },
    { label: "VA nurse pay", href: VA_NURSE_PATH },
    { label: name },
  ]);
  const year = tables[0]?.year ?? "";
  const toc = tables.map((t) => html`<li><a href="#pay-${t.id}">${t.title}</a></li>`);
  const sections = tables.map(
    (t) => html`<section>
<h2>${t.title}</h2>
${t.area ? html`<p>Applies in: ${t.area}</p>` : ""}
${payTableHtml(t, `${t.title}, annual rates by grade and step`)}
${sourceFacts(t, "VA Office of the Chief Human Capital Officer")}
</section>`,
  );
  return html`${crumbs}
<h1>${name}: nurse pay ${year}</h1>
<p class="lead">${tables.length} nurse locality pay schedules (annual rates by grade and step) for
this VA facility.</p>
<ul>${toc}</ul>
${sections}`;
}
