import { beforeEach, describe, expect, it } from "vitest";
import { resetMenuCache } from "../src/index";
import { db, page, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
  resetMenuCache();
});

describe("trang chủ và trang bang", () => {
  it("trang chủ có bảng mẫu các học khu lớn nhất có lương khởi điểm, theo số học sinh", async () => {
    const { a, b } = await seed();
    await db
      .prepare("UPDATE districts SET enrollment = CASE id WHEN ? THEN 5000 WHEN ? THEN 9000 END")
      .bind(a.districtId, b.districtId)
      .run();
    let html = await page("/");
    expect(html).toContain('<h2 id="largest-heading">The largest districts at a glance</h2>');
    // Cañon Test đông hơn nhưng không có lương khởi điểm BA nên không vào bảng mẫu.
    expect(html).toContain("The 1 largest school districts by enrollment");
    let start = html.indexOf('id="largest-heading"');
    let section = html.slice(start, html.indexOf("</section>", start));
    expect(section).toContain('href="/test-state/test-valley-unified"');
    expect(section).not.toContain('href="/test-state/canon-test"');
    expect(section).toContain('<span class="muted">ZZ</span>');
    // Có lương khởi điểm thì vào, xếp theo số học sinh.
    await db
      .prepare("UPDATE district_summary SET start_ba_cents = 4900000 WHERE district_id = ?")
      .bind(b.districtId)
      .run();
    html = await page("/");
    start = html.indexOf('id="largest-heading"');
    section = html.slice(start, html.indexOf("</section>", start));
    const canon = section.indexOf('href="/test-state/canon-test"');
    const valley = section.indexOf('href="/test-state/test-valley-unified"');
    expect(canon).toBeGreaterThan(-1);
    expect(valley).toBeGreaterThan(canon);
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

  it("menu States chỉ có bang đã có bảng lương, xếp theo số học sinh", async () => {
    await seed();
    const html = await page("/about");
    const menu = html.slice(
      html.indexOf('<details class="states-menu">'),
      html.indexOf("</details>"),
    );
    expect(menu).toContain('<li><a href="/test-state">Test State</a></li>');
    expect(menu).not.toContain("California");
    expect(menu).toContain('<a href="/#states-heading">All states</a>');
  });

  it("chưa có bang nào có dữ liệu thì menu dùng danh sách sẵn", async () => {
    const html = await page("/about");
    expect(html).toContain('<li><a href="/california">California</a></li>');
  });

  it("trang bang lần đầu: học khu đã có bảng lên trước, 'No schedule yet' xếp sau", async () => {
    await seed();
    const html = await page("/test-state");
    const valley = html.indexOf(
      '<tr data-group="0">\n<th scope="row" data-sort-value="test valley',
    );
    const ridge = html.indexOf('<tr data-group="1">');
    expect(valley).toBeGreaterThan(-1);
    expect(ridge).toBeGreaterThan(valley);
  });

  it("link sắp xếp của bảng học khu trỏ tới bảng, không về đầu trang", async () => {
    await seed();
    const html = await page("/test-state");
    expect(html).toContain('href="/test-state?sort=start&amp;dir=desc#districts-heading"');
    expect(html).toContain('<h2 id="districts-heading">');
  });
});
