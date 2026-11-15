import { beforeEach, describe, expect, it } from "vitest";
import { page, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});
describe("mục lục và câu hỏi thu gọn ở trang học khu", () => {
  it("có mục lục trỏ tới các phần, câu hỏi dạng details (câu đầu mở sẵn)", async () => {
    const { a } = await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain('<nav class="on-page" aria-label="On this page">');
    expect(html).toContain(`<a href="#schedule-${a.scheduleId}-heading">Salary schedule</a>`);
    expect(html).toContain(`<a href="#calc-heading-${a.scheduleId}">Calculator</a>`);
    expect(html).toContain(`<h3 id="calc-heading-${a.scheduleId}">Salary calculator</h3>`);
    expect(html).toContain('<a href="#faq-heading">Questions</a>');
    expect(html).toContain('<details class="faq" open><summary><h3>');
    expect((html.match(/<details class="faq">/g) ?? []).length).toBeGreaterThan(0);
  });
});
