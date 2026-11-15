import { beforeEach, describe, expect, it } from "vitest";
import { db, page, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});

describe("trang chủ và trang bang", () => {
  it("trang chủ có bảng mẫu các học khu lớn nhất, theo số học sinh", async () => {
    const { a, b } = await seed();
    await db
      .prepare("UPDATE districts SET enrollment = CASE id WHEN ? THEN 5000 WHEN ? THEN 9000 END")
      .bind(a.districtId, b.districtId)
      .run();
    const html = await page("/");
    expect(html).toContain('<h2 id="largest-heading">The largest districts at a glance</h2>');
    expect(html).toContain("The 2 largest school districts by enrollment");
    // Cañon Test đông hơn nên đứng trước; dòng có mã bang và ba mốc lương.
    const start = html.indexOf('id="largest-heading"');
    const section = html.slice(start, html.indexOf("</section>", start));
    const canon = section.indexOf('href="/test-state/canon-test"');
    const valley = section.indexOf('href="/test-state/test-valley-unified"');
    expect(canon).toBeGreaterThan(-1);
    expect(valley).toBeGreaterThan(canon);
    expect(section).toContain('<span class="muted">ZZ</span>');
  });

  it("học khu không có số học sinh thì không vào bảng mẫu", async () => {
    await seed();
    expect(await page("/")).not.toContain("largest-heading");
  });

  it("trang bang có thanh độ phủ", async () => {
    await seed();
    const html = await page("/test-state");
    // 2 trong 3 học khu có bảng published (học khu thứ ba chỉ có bảng draft).
    expect(html).toContain('aria-label="67% of districts have a published schedule"');
    expect(html).toContain('<span style="width: 67%"></span>');
  });
});
