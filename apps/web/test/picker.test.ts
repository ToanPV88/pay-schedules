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

describe("ô trống của bảng lương", () => {
  it("ghi chú chung 'Blank in the source document' chỉ còn dấu gạch, không title", async () => {
    const { scheduleTable } = await import("../src/views/schedule");
    const cells = DEMO_SCHEDULE.cells.map((row, i) =>
      row.map((cell, j) =>
        i === 1 && j === 2 ? { amountCents: null, note: "Blank in the source document" } : cell,
      ),
    );
    const html = String(scheduleTable({ ...DEMO_SCHEDULE, cells }, "Demo"));
    expect(html).toContain(
      '<td class="empty">—<span class="visually-hidden"> No amount in the source</span></td>',
    );
    expect(html).not.toContain('title="Blank in the source document"');
    // Ghi chú riêng của tài liệu vẫn có ở title.
    expect(html).toContain('title="No initial placement in this lane"');
    expect(html).toContain("<caption>Demo. A dash means the document shows no amount");
  });
});
