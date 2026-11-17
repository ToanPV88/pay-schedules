/**
 * Phần "đối đầu" của trang so sánh hai học khu (D-118): bảng ba mốc lương, hạng trong bang, số học
 * sinh, và câu tóm tắt sinh từ số liệu.
 */
import type { SummaryEntry } from "@pay-schedules/db";
import { html } from "hono/html";
import { formatCents, schoolYearLabel } from "../format";
import { type Milestone, ordinal, rankOf } from "../ranks";
import type { Html } from "./layout";
import { districtPath } from "./parts";
import { MILESTONE_INFO } from "./rankings";

function value(e: SummaryEntry, m: Milestone): number | null {
  return m === "start" ? e.startBaCents : m === "ma10" ? e.maStep10Cents : e.maxSalaryCents;
}

function diffCell(a: number | null, b: number | null, nameA: string, nameB: string): Html {
  if (a === null || b === null) {
    return html`<td class="empty">—</td>`;
  }
  const d = a - b;
  if (Math.abs(d) < 100) {
    return html`<td>About the same</td>`;
  }
  return html`<td>${formatCents(Math.abs(d))} more in ${d > 0 ? nameA : nameB}</td>`;
}

/** Câu tóm tắt: chênh lệch lương khởi điểm và mức tối đa. */
export function pairSummary(a: SummaryEntry, b: SummaryEntry): string {
  const parts: string[] = [];
  for (const m of ["start", "max"] as const) {
    const va = value(a, m);
    const vb = value(b, m);
    if (va === null || vb === null) {
      continue;
    }
    const label =
      m === "start"
        ? "Starting pay"
        : parts.length > 0
          ? "the top of the scale"
          : "The top of the scale";
    const d = va - vb;
    if (Math.abs(d) < 100) {
      parts.push(`${label} is about the same (${formatCents(va)})`);
    } else {
      const higher = d > 0 ? a.name : b.name;
      parts.push(
        `${label} is ${formatCents(Math.abs(d))} higher in ${higher} (${formatCents(va)} vs ${formatCents(vb)})`,
      );
    }
  }
  return parts.length > 0 ? `${parts.join("; ")}.` : "";
}

export function headToHead(a: SummaryEntry, b: SummaryEntry, all: SummaryEntry[]): Html {
  const rows: Html[] = [];
  for (const m of ["start", "ma10", "max"] as const) {
    const va = value(a, m);
    const vb = value(b, m);
    if (va === null && vb === null) {
      continue;
    }
    const cell = (v: number | null) =>
      v === null ? html`<td class="empty">—</td>` : html`<td>${formatCents(v)}</td>`;
    rows.push(
      html`<tr><th scope="row">${MILESTONE_INFO[m].label}</th>${cell(va)}${cell(vb)}${diffCell(va, vb, a.name, b.name)}</tr>\n`,
    );
  }
  const rank = (e: SummaryEntry) => {
    const r = rankOf(
      all.filter((x) => x.stateCode === e.stateCode),
      e.id,
      "start",
    );
    return r ? `${ordinal(r.rank)} of ${r.total.toLocaleString("en-US")} in ${e.stateName}` : "—";
  };
  const students = (e: SummaryEntry) =>
    e.enrollment === null ? "—" : e.enrollment.toLocaleString("en-US");
  rows.push(
    html`<tr><th scope="row">Starting pay rank</th><td>${rank(a)}</td><td>${rank(b)}</td><td></td></tr>\n`,
  );
  rows.push(
    html`<tr><th scope="row">Students</th><td>${students(a)}</td><td>${students(b)}</td><td></td></tr>\n`,
  );
  rows.push(
    html`<tr><th scope="row">School year</th><td>${schoolYearLabel(a.schoolYear)}</td><td>${schoolYearLabel(b.schoolYear)}</td><td></td></tr>\n`,
  );
  const link = (e: SummaryEntry) =>
    html`<a href="${districtPath(e.stateSlug, e.slug)}">${e.name}</a>`;
  return html`<section aria-labelledby="head-heading">
<h2 id="head-heading">Head to head</h2>
<div class="table-scroll" role="region" aria-label="Head to head" tabindex="0">
<table class="pair-table">
<thead><tr><th scope="col"></th><th scope="col">${link(a)}</th><th scope="col">${link(b)}</th><th scope="col">Difference</th></tr></thead>
<tbody>
${rows}</tbody>
</table>
</div>
<p class="muted">From each district’s latest published schedule. Starting pay is the bachelor’s column at step 1; the master’s figure is step 10. See each district page for the full table and source document.</p>
</section>`;
}
