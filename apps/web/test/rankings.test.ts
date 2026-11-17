import { beforeEach, describe, expect, it } from "vitest";
import { page, request, reset, seed } from "./helpers";

describe("trang xếp hạng (D-116)", () => {
  beforeEach(async () => {
    await reset();
    await seed();
  });

  it("tổng quan: ba mốc, học khu có số mới được xếp", async () => {
    const html = await page("/rankings");
    expect(html).toContain("<h1>Teacher salary rankings</h1>");
    expect(html).toContain('id="rank-starting-pay"');
    expect(html).toContain('id="rank-top-of-scale"');
    // Không học khu nào có số MA bậc 10 trong dữ liệu mẫu: không có mục đó.
    expect(html).not.toContain('id="rank-masters-step-10"');
    expect(html).toContain('href="/rankings/top-of-scale"');
  });

  it("toàn quốc một mốc: thứ tự, số tiền, liên kết bang", async () => {
    const html = await page("/rankings/top-of-scale");
    const valley = html.indexOf("Test Valley Unified");
    const canon = html.indexOf("Cañon Test");
    expect(valley).toBeGreaterThan(0);
    expect(canon).toBeGreaterThan(valley);
    expect(html).toContain("$62,000");
    expect(html).toContain('href="/rankings/top-of-scale/test-state"');
    expect(html).toContain('aria-current="page">Top of the scale</a>');
  });

  it("theo bang: ít học khu thì noindex; mốc hay bang lạ thì 404", async () => {
    const html = await page("/rankings/starting-pay/test-state", { INDEXABLE: "true" });
    expect(html).toContain("Test State districts by starting pay");
    expect(html).toContain('content="noindex');
    expect((await request("/rankings/salary")).status).toBe(404);
    expect((await request("/rankings/starting-pay/no-such-state")).status).toBe(404);
  });

  it("menu có Rankings; sitemap vẫn chỉ gồm trang học khu", async () => {
    const xml = await (await request("/sitemap.xml")).text();
    expect(xml).not.toContain("/rankings");
    expect(await page("/about")).toContain('<a href="/rankings">Rankings</a>');
  });
});
