import { beforeEach, describe, expect, it } from "vitest";
import { axisMoney, chartLanes, niceStep, spreadLabels, xTickIndexes } from "../src/views/chart";
import { page, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});

describe("biểu đồ lương theo bậc", () => {
  it("chọn tối đa bốn lane: đầu, cuối và hai lane cách đều", () => {
    expect(chartLanes(1)).toEqual([0]);
    expect(chartLanes(4)).toEqual([0, 1, 2, 3]);
    expect(chartLanes(9)).toEqual([0, 3, 5, 8]);
  });

  it("bước chia trục tròn và nhãn tiền gọn", () => {
    expect(niceStep(2_100_000)).toBe(1_000_000);
    expect(niceStep(4_700_000)).toBe(2_000_000);
    expect(axisMoney(4_500_000)).toBe("$45k");
    expect(axisMoney(5_250_000)).toBe("$52.5k");
    expect(axisMoney(2_550)).toBe("$25.50");
  });

  it("nhãn trục x cách đều, không dính vào nhãn bậc cuối", () => {
    expect(xTickIndexes(5)).toEqual([0, 1, 2, 3, 4]);
    // 16 bậc (0-15): mỗi 2 bậc một nhãn, bỏ bậc 14 vì sát bậc cuối.
    expect(xTickIndexes(16)).toEqual([0, 2, 4, 6, 8, 10, 12, 15]);
    expect(xTickIndexes(41)).toEqual([0, 6, 12, 18, 24, 30, 40]);
  });

  it("nhãn cuối đường không chồng nhau và nằm trong khung", () => {
    const ys = spreadLabels([100, 104, 50], 13, 10, 200);
    expect(ys[2]).toBe(50);
    expect(Math.abs((ys[1] ?? 0) - (ys[0] ?? 0))).toBeGreaterThanOrEqual(13);
    const crowded = spreadLabels([195, 196, 197], 13, 10, 200);
    expect(Math.max(...crowded)).toBeLessThanOrEqual(200);
  });

  it("trang học khu có biểu đồ SVG kèm chú giải và dữ liệu cho chú thích", async () => {
    const { a } = await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain("<h3>How pay grows with each step</h3>");
    expect(html).toContain('<figure class="pay-chart" data-chart="');
    expect(html).toContain(
      `aria-labelledby="chart-${a.scheduleId}-title chart-${a.scheduleId}-desc"`,
    );
    // Bảng chuẩn có bốn lane: chú giải đủ bốn, không có câu "x of y lanes".
    expect(html).toContain('<li><span class="key s4"></span>MA+30</li>');
    expect(html).not.toContain("lanes are shown");
    expect(html).toContain("BA starts at $50,000; the highest amount shown is $62,000.");
  });
});
