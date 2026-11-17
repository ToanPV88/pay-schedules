/**
 * Bản đồ ô các bang trên trang chủ (DECISIONS.md D-120): mỗi bang một ô vuông theo vị trí gần đúng,
 * tô theo phần trăm học khu đã có bảng lương. Ô là liên kết tới trang bang; danh sách bang bên dưới
 * vẫn giữ cho người dùng trình đọc màn hình và khi CSS không tải.
 */
import type { StateCount } from "@pay-schedules/db";
import { html } from "hono/html";
import type { Html } from "./layout";

/** Vị trí ô (cột, hàng; đếm từ 1), bố cục quen thuộc của bản đồ ô nước Mỹ. */
export const TILE_POSITIONS: Record<string, [number, number]> = {
  AK: [1, 1],
  ME: [12, 1],
  VT: [11, 2],
  NH: [12, 2],
  WA: [2, 3],
  ID: [3, 3],
  MT: [4, 3],
  ND: [5, 3],
  MN: [6, 3],
  IL: [7, 3],
  WI: [8, 3],
  MI: [9, 3],
  NY: [10, 3],
  RI: [11, 3],
  MA: [12, 3],
  OR: [2, 4],
  NV: [3, 4],
  WY: [4, 4],
  SD: [5, 4],
  IA: [6, 4],
  IN: [7, 4],
  OH: [8, 4],
  PA: [9, 4],
  NJ: [10, 4],
  CT: [11, 4],
  CA: [2, 5],
  UT: [3, 5],
  CO: [4, 5],
  NE: [5, 5],
  MO: [6, 5],
  KY: [7, 5],
  WV: [8, 5],
  VA: [9, 5],
  MD: [10, 5],
  DE: [11, 5],
  AZ: [3, 6],
  NM: [4, 6],
  KS: [5, 6],
  AR: [6, 6],
  TN: [7, 6],
  NC: [8, 6],
  SC: [9, 6],
  DC: [10, 6],
  OK: [5, 7],
  LA: [6, 7],
  MS: [7, 7],
  AL: [8, 7],
  GA: [9, 7],
  HI: [1, 8],
  TX: [5, 8],
  FL: [10, 8],
};

/** Mức tô: 0 = chưa có bảng nào; 1..4 theo phần trăm học khu có bảng. */
export function coverageLevel(state: StateCount): number {
  if (state.withSchedule === 0 || state.districts === 0) {
    return 0;
  }
  const share = state.withSchedule / state.districts;
  if (share < 0.1) {
    return 1;
  }
  if (share < 0.25) {
    return 2;
  }
  return share < 0.5 ? 3 : 4;
}

export function coveragePercent(state: StateCount): number {
  return state.districts === 0 ? 0 : Math.round((state.withSchedule / state.districts) * 100);
}

const LEGEND = ["No schedules yet", "Under 10%", "10–24%", "25–49%", "50% or more"];

export function stateMap(states: StateCount[]): Html {
  const tiles: Html[] = [];
  for (const state of states) {
    const pos = TILE_POSITIONS[state.code];
    if (!pos) {
      continue;
    }
    const level = coverageLevel(state);
    const pct = coveragePercent(state);
    const label = `${state.name}: ${state.withSchedule.toLocaleString("en-US")} of ${state.districts.toLocaleString("en-US")} districts have a schedule (${pct}%)`;
    const style = `grid-column:${pos[0]};grid-row:${pos[1]}`;
    tiles.push(
      html`<a class="tile cov-${level}" href="/${state.slug}" style="${style}" aria-label="${label}" title="${label}"><span>${state.code}</span><small>${level === 0 ? "" : `${pct}%`}</small></a>`,
    );
  }
  if (tiles.length === 0) {
    return html``;
  }
  const legend = LEGEND.map(
    (text, i) => html`<li><span class="swatch cov-${i}" aria-hidden="true"></span>${text}</li>`,
  );
  return html`<figure class="state-map">
<div class="tiles">${tiles}</div>
<figcaption>Share of each state’s school districts with a published teacher salary schedule on this site. Select a state to browse its districts.</figcaption>
<ul class="map-legend">${legend}</ul>
</figure>`;
}
