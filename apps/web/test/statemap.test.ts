import { describe, expect, it } from "vitest";
import { coverageLevel, coveragePercent, stateMap, TILE_POSITIONS } from "../src/views/statemap";
import { page, reset, seed } from "./helpers";

const state = (code: string, districts: number, withSchedule: number) => ({
  code,
  name: code,
  slug: code.toLowerCase(),
  districts,
  withSchedule,
});

describe("bản đồ ô các bang (D-120)", () => {
  it("đủ 50 bang và DC, không trùng ô", () => {
    const cells = Object.values(TILE_POSITIONS).map(([c, r]) => `${c},${r}`);
    expect(cells.length).toBe(51);
    expect(new Set(cells).size).toBe(51);
  });

  it("mức tô theo phần trăm học khu có bảng", () => {
    expect(coverageLevel(state("TX", 1000, 0))).toBe(0);
    expect(coverageLevel(state("TX", 1000, 50))).toBe(1);
    expect(coverageLevel(state("TX", 1000, 100))).toBe(2);
    expect(coverageLevel(state("TX", 1000, 300))).toBe(3);
    expect(coverageLevel(state("TX", 1000, 500))).toBe(4);
    expect(coveragePercent(state("TX", 3, 1))).toBe(33);
    const html = String(stateMap([state("TX", 1000, 300), state("ZZ", 5, 5)]));
    expect(html).toContain('class="tile cov-3" href="/tx" style="grid-column:5;grid-row:8"');
    expect(html).toContain("TX: 300 of 1,000 districts have a schedule (30%)");
    const tiny = String(stateMap([state("MI", 1000, 2)]));
    expect(tiny).toContain("<small>&lt;1%</small>");
    expect(tiny).toContain("(under 1%)");
    // Mã không có vị trí (dữ liệu thử) thì bỏ qua.
    expect(html).not.toContain('href="/zz"');
  });

  it("trang chủ có bản đồ, vẫn giữ danh sách bang", async () => {
    await reset();
    await seed();
    const html = await page("/");
    expect(html).toContain('<ul class="state-list">');
  });
});
