/**
 * Biểu đồ "lương tăng theo bậc": SVG vẽ phía server, không thư viện, không cần JavaScript để xem.
 * Mỗi đường là một lane (tối đa bốn lane: đầu, cuối và hai lane cách đều ở giữa); bảng lương ngay
 * phía trên là bản đầy đủ để đọc số. `public/site.js` thêm đường dóng và chú thích khi rê chuột.
 *
 * Màu theo bảng màu tham chiếu của skill dataviz (đã chạy validate_palette cho nền sáng #ffffff và
 * nền tối #191919: đạt CVD, độ sáng, độ bão hòa; hai màu ở nền sáng dưới 3:1 nên có nhãn trực tiếp ở
 * cuối đường và bảng số đi kèm).
 */
import type { Schedule } from "@pay-schedules/db";
import { html, raw } from "hono/html";
import { formatCents, stepLabel } from "../format";
import type { Html } from "./layout";

/** Số lane tối đa vẽ trên một biểu đồ. */
export const MAX_SERIES = 4;

const W = 420;
const H = 250;
const M = { top: 12, right: 96, bottom: 34, left: 50 };
const LABEL_GAP = 13;

interface Series {
  laneIndex: number;
  label: string;
  cents: (number | null)[];
}

/** Chọn lane để vẽ: tất cả nếu không quá bốn, ngược lại lấy đầu, cuối và hai lane ở giữa. */
export function chartLanes(count: number): number[] {
  if (count <= MAX_SERIES) {
    return Array.from({ length: count }, (_, i) => i);
  }
  const picks = [0, Math.round((count - 1) / 3), Math.round((2 * (count - 1)) / 3), count - 1];
  return [...new Set(picks)];
}

/** Bước chia trục tròn (1, 2, 2.5, 5 × 10^k) cho khoảng `span` với khoảng `target` vạch. */
export function niceStep(span: number, target = 4): number {
  if (span <= 0) {
    return 1;
  }
  const raw = span / target;
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * power >= raw) {
      return m * power;
    }
  }
  return 10 * power;
}

/** Nhãn trục y theo đô la: "$45k", "$52.5k" khi số lớn; "$25" với lương giờ. */
export function axisMoney(cents: number): string {
  const dollars = cents / 100;
  if (Math.abs(dollars) >= 10_000) {
    const k = dollars / 1000;
    return `$${Number.isInteger(k) ? k : k.toFixed(1)}k`;
  }
  return `$${Number.isInteger(dollars) ? dollars : dollars.toFixed(2)}`;
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function seriesOf(schedule: Schedule): Series[] {
  const count = Math.max(schedule.lanes.length, 1);
  const series: Series[] = [];
  for (const j of chartLanes(count)) {
    const cents = schedule.steps.map((_, i) => schedule.cells[i]?.[j]?.amountCents ?? null);
    if (cents.filter((c) => c !== null).length < 2) {
      continue;
    }
    series.push({ laneIndex: j, label: schedule.lanes[j]?.labelRaw ?? "Salary", cents });
  }
  return series;
}

/** Đặt nhãn cuối đường không chồng nhau: xếp theo y, đẩy xuống khi quá gần, rồi kéo lại vào khung. */
export function spreadLabels(ys: number[], gap: number, top: number, bottom: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const placed = order.map((o) => o.y);
  for (let k = 1; k < placed.length; k++) {
    placed[k] = Math.max(placed[k] ?? 0, (placed[k - 1] ?? 0) + gap);
  }
  const overflow = (placed[placed.length - 1] ?? 0) - bottom;
  if (overflow > 0) {
    for (let k = 0; k < placed.length; k++) {
      placed[k] = Math.max(top, (placed[k] ?? 0) - overflow);
    }
  }
  const out = new Array<number>(ys.length);
  for (const [k, o] of order.entries()) {
    out[o.i] = placed[k] ?? o.y;
  }
  return out;
}

/** Null khi bảng quá ngắn (dưới 3 bậc) hoặc không lane nào có từ hai ô có số. */
export function payChart(schedule: Schedule): Html | null {
  const steps = schedule.steps;
  if (steps.length < 3) {
    return null;
  }
  const series = seriesOf(schedule);
  if (series.length === 0) {
    return null;
  }
  const values = series.flatMap((s) => s.cents.filter((c): c is number => c !== null));
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const tick = niceStep(hi - lo);
  const yMin = Math.floor(lo / tick) * tick;
  const yMax = Math.max(Math.ceil(hi / tick) * tick, yMin + tick);
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const dx = steps.length > 1 ? plotW / (steps.length - 1) : 0;
  const xAt = (i: number) => M.left + i * dx;
  const yAt = (cents: number) => M.top + plotH - ((cents - yMin) / (yMax - yMin)) * plotH;
  const r = (n: number) => Math.round(n * 10) / 10;

  // Lưới ngang và nhãn trục y.
  const grid: string[] = [];
  for (let v = yMin; v <= yMax + tick / 2; v += tick) {
    const y = r(yAt(v));
    grid.push(
      `<line x1="${M.left}" x2="${W - M.right}" y1="${y}" y2="${y}"/><text x="${M.left - 6}" y="${y}" dy="0.32em" text-anchor="end">${axisMoney(v)}</text>`,
    );
  }
  // Nhãn trục x: tối đa khoảng 8 vạch, luôn có bậc đầu và bậc cuối.
  const every = Math.max(1, Math.ceil(steps.length / 8));
  const xTicks: string[] = [];
  for (const [i, step] of steps.entries()) {
    if (i % every !== 0 && i !== steps.length - 1) {
      continue;
    }
    if (i !== steps.length - 1 && steps.length - 1 - i < every / 2) {
      continue;
    }
    const label = escapeText(truncate(step.labelRaw, 6));
    xTicks.push(
      `<text x="${r(xAt(i))}" y="${H - M.bottom + 16}" text-anchor="middle">${label}</text>`,
    );
  }

  // Đường của từng lane; ô trống làm đứt đường thay vì nối qua.
  const paths: string[] = [];
  const ends: { x: number; y: number; label: string; k: number }[] = [];
  for (const [k, s] of series.entries()) {
    let d = "";
    let pen = false;
    let last: { i: number; c: number } | null = null;
    for (const [i, c] of s.cents.entries()) {
      if (c === null) {
        pen = false;
        continue;
      }
      d += `${pen ? "L" : "M"}${r(xAt(i))} ${r(yAt(c))}`;
      pen = true;
      last = { i, c };
    }
    paths.push(`<path class="s${k + 1}" d="${d}"/>`);
    if (last) {
      ends.push({ x: xAt(last.i), y: yAt(last.c), label: s.label, k });
    }
  }
  const labelYs = spreadLabels(
    ends.map((e) => e.y),
    LABEL_GAP,
    M.top + 4,
    H - M.bottom,
  );
  const marks: string[] = [];
  for (const [n, e] of ends.entries()) {
    const ly = labelYs[n] ?? e.y;
    const lx = W - M.right + 12;
    if (Math.abs(ly - e.y) > 2) {
      marks.push(`<path class="leader" d="M${r(e.x + 5)} ${r(e.y)}L${lx - 3} ${r(ly)}"/>`);
    }
    marks.push(`<circle class="s${e.k + 1}" cx="${r(e.x)}" cy="${r(e.y)}" r="3.5"/>`);
    marks.push(
      `<text class="end-label" x="${lx}" y="${r(ly)}" dy="0.32em">${escapeText(truncate(e.label, 12))}</text>`,
    );
  }

  const id = `chart-${schedule.id}`;
  const first = series[0];
  const firstStart = first?.cents.find((c) => c !== null) ?? null;
  const summary =
    firstStart === null
      ? "Line chart of pay by step."
      : `Line chart of pay by step. ${first?.label} starts at ${formatCents(firstStart)}; the highest amount shown is ${formatCents(hi)}.`;
  const total = Math.max(schedule.lanes.length, 1);
  const shown =
    total > series.length
      ? ` ${series.length} of ${total} lanes are shown; every lane is in the table above.`
      : "";
  const legend =
    series.length > 1
      ? html`<ul class="chart-legend">${series.map(
          (s, k) => html`<li><span class="key s${k + 1}"></span>${s.label}</li>`,
        )}</ul>`
      : html``;
  // Dữ liệu cho chú thích khi rê chuột (site.js); không cần để đọc biểu đồ.
  const data = JSON.stringify({
    w: W,
    x0: M.left,
    dx,
    steps: steps.map((s) => stepLabel(s)),
    series: series.map((s) => ({ label: s.label, cents: s.cents })),
  });
  const svg = raw(
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="${id}-title ${id}-desc" focusable="false">` +
      `<title id="${id}-title">How pay grows with each step</title><desc id="${id}-desc">${escapeText(summary)}</desc>` +
      `<g class="grid">${grid.join("")}</g><g class="x-axis">${xTicks.join("")}</g>` +
      `<line class="crosshair" x1="0" x2="0" y1="${M.top}" y2="${H - M.bottom}"/>` +
      `<g class="series">${paths.join("")}</g><g class="ends">${marks.join("")}</g></svg>`,
  );
  return html`<figure class="pay-chart" data-chart="${data}">
${legend}
${svg}
<div class="chart-tip" hidden></div>
<figcaption>Each line is one lane; steps run left to right.${shown}</figcaption>
</figure>`;
}

function escapeText(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
