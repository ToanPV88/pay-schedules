import { beforeEach, describe, expect, it } from "vitest";
import { page, request, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});

interface SuggestBody {
  q: string;
  hits: { name: string; place: string; href: string; hasSchedule: boolean }[];
}

describe("gợi ý học khu khi gõ", () => {
  it("/api/suggest trả JSON cùng thứ tự với /search, có đường dẫn và nơi chốn", async () => {
    await seed();
    const res = await request("/api/suggest?q=test%20vall");
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("application/json");
    expect(res.headers.get("X-Robots-Tag")).toContain("noindex");
    const body = (await res.json()) as SuggestBody;
    expect(body.q).toBe("test vall");
    expect(body.hits[0]).toEqual({
      name: "Test Valley Unified School District",
      place: "Testville, Test County, Test State",
      href: "/test-state/test-valley-unified",
      hasSchedule: true,
    });
  });

  it("dưới hai ký tự thì không tìm", async () => {
    await seed();
    const body = (await (await request("/api/suggest?q=t")).json()) as SuggestBody;
    expect(body.hits).toEqual([]);
  });

  it("ô tìm kiếm ở trang chủ và /search bật gợi ý; trang chủ nạp site.js", async () => {
    await seed();
    const home = await page("/");
    expect(home).toContain('data-suggest="/api/suggest"');
    expect(home).toContain('<script src="/site.js" defer></script>');
    expect(await page("/search?q=test")).toContain('data-suggest="/api/suggest"');
    // Ô chọn học khu của /compare dẫn vào luồng riêng, không gợi ý.
    expect(await page("/compare")).not.toContain("data-suggest");
  });

  it("robots.txt chặn /api/", async () => {
    const res = await request("/robots.txt", {}, { INDEXABLE: "true" });
    expect(await res.text()).toContain("Disallow: /api/");
  });
});
