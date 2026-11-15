import { beforeEach, describe, expect, it } from "vitest";
import { DEMO_SCHEDULE } from "../src/demo";
import { schedulePicker } from "../src/views/district";
import { page, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});

describe("chọn nhanh bảng lương và cỡ chữ bảng", () => {
  it("học khu có nhiều bảng: danh sách đầu trang trỏ tới từng bảng, có khoảng lương", () => {
    const second = { ...DEMO_SCHEDULE, id: 902, title: "Counselors and Nurses" };
    const html = String(schedulePicker([DEMO_SCHEDULE, second], "2025-26"));
    expect(html).toContain('<h2 id="picker-heading">Salary schedules for 2025–26</h2>');
    expect(html).toContain("publishes 2 salary schedules for 2025–26");
    expect(html).toContain(`href="#schedule-${DEMO_SCHEDULE.id}-heading"`);
    expect(html).toContain('href="#schedule-902-heading"');
    expect(html).toContain("Counselors and Nurses");
    expect(html).toContain("15 steps × 4 lanes");
    expect(html).toMatch(/\$50,000–\$\d{2},\d{3} per year/);
  });

  it("một bảng thì không có danh sách", () => {
    expect(String(schedulePicker([DEMO_SCHEDULE], "2025-26"))).toBe("");
  });

  it("bảng lương có nút cỡ chữ, ẩn sẵn chờ JavaScript", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain('<div class="table-tools" data-text-size hidden>');
    expect(html).toContain('aria-label="Larger table text"');
    expect(html).not.toContain('id="picker-heading"');
  });
});
