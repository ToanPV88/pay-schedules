import { describe, expect, it } from "vitest";
import { DEMO_DISTRICT } from "../src/demo";
import { changeText, type DistrictPageData, historySection } from "../src/views/district";
import { stateTopLists, TOP_MIN } from "../src/views/pages";

describe("so sánh qua các năm", () => {
  it("mức thay đổi có số tiền và phần trăm", () => {
    expect(changeText(9_000_000, 9_186_000)).toBe("+$1,860 (+2.1%)");
    expect(changeText(9_000_000, 8_910_000)).toBe("−$900 (−1.0%)");
    expect(changeText(null, 9_000_000)).toBe("—");
  });

  it("từ hai năm trở lên: bảng theo năm tăng dần, năm đang xem không có link", () => {
    const data = {
      district: DEMO_DISTRICT,
      year: "2025-26",
      latestYear: "2025-26",
      history: [
        { schoolYear: "2025-26", schedules: 1, minCents: 5_000_000, maxCents: 7_700_000 },
        { schoolYear: "2024-25", schedules: 1, minCents: 4_850_000, maxCents: 7_500_000 },
      ],
    } as unknown as DistrictPageData;
    const html = String(historySection(data));
    expect(html).toContain('<h2 id="years-heading">Pay over the years</h2>');
    expect(html.indexOf("2024–25")).toBeLessThan(html.indexOf("2025–26"));
    expect(html).toContain('2025–26 <span class="muted">(this page)</span>');
    expect(html).toContain("<td>+$2,000 (+2.7%)</td>");
  });

  it("một năm: câu cũ, không có bảng", () => {
    const data = {
      district: DEMO_DISTRICT,
      year: "2025-26",
      latestYear: "2025-26",
      history: [{ schoolYear: "2025-26", schedules: 1, minCents: 1, maxCents: 2 }],
    } as unknown as DistrictPageData;
    const html = String(historySection(data));
    expect(html).toContain("Other school years");
    expect(html).not.toContain("<table");
  });
});

describe("bảng xếp hạng của bang", () => {
  const state = { code: "ZZ", name: "Test State", slug: "test-state" };
  const item = (n: number, start: number | null) => ({
    id: n,
    name: `District ${n}`,
    slug: `district-${n}`,
    city: null,
    county: null,
    hasSchedule: true,
    summary: {
      schoolYear: "2025-26",
      startBaCents: start,
      maStep10Cents: null,
      maxSalaryCents: 9_000_000 - n,
    },
  });

  it("đủ số học khu thì hiện, bỏ học khu thiếu số", () => {
    const top = [item(1, 6_000_000), item(2, null), item(3, 5_500_000), item(4, 5_000_000)];
    const html = String(stateTopLists(state, top, top));
    expect(html).toContain("Highest-paying districts in Test State");
    expect(html).toContain("Highest starting salary (BA, step 1)");
    const startList = html.slice(html.indexOf("Highest starting"), html.indexOf("Highest top"));
    expect(startList).not.toContain("district-2");
    expect(html).toContain('<a href="/test-state/district-1">District 1</a><span>$60,000</span>');
  });

  it(`dưới ${TOP_MIN} học khu có số thì không hiện`, () => {
    const top = [item(1, 6_000_000), item(2, null)];
    const html = String(stateTopLists(state, top, top.slice(0, 1)));
    expect(html).toBe("");
  });
});
