import { env, exports } from "cloudflare:workers";
import { describe, expect, it } from "vitest";

const BASE = "https://example.invalid";
// Số migration trong packages/db/migrations, đã áp trong test/apply-migrations.ts.
const MIGRATIONS = (env as unknown as { TEST_MIGRATIONS: unknown[] }).TEST_MIGRATIONS.length;

function get(path: string): Promise<Response> {
  return exports.default.fetch(new Request(`${BASE}${path}`));
}

describe("vận hành", () => {
  it("trang chủ render HTML từ D1", async () => {
    const res = await get("/");
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    const body = await res.text();
    expect(body).toContain("Pay Schedules");
    expect(body).toContain("Browse by state");
  });

  it("healthz báo đã áp migration", async () => {
    const res = await get("/healthz");
    expect(res.status).toBe(200);
    expect(MIGRATIONS).toBeGreaterThanOrEqual(3);
    expect(await res.json()).toEqual({
      ok: true,
      environment: "production",
      migrations: MIGRATIONS,
    });
  });
});

describe("chưa cho lập chỉ mục (DECISIONS.md D-002)", () => {
  it("mọi phản hồi có X-Robots-Tag noindex", async () => {
    for (const path of ["/", "/healthz", "/robots.txt", "/sitemap.xml", "/about", "/khong-co"]) {
      const res = await get(path);
      expect(res.headers.get("x-robots-tag"), path).toBe("noindex, nofollow");
    }
  });

  it("robots.txt chặn tất cả", async () => {
    const res = await get("/robots.txt");
    expect(await res.text()).toBe("User-agent: *\nDisallow: /\n");
  });

  it("thẻ meta robots là noindex", async () => {
    const body = await (await get("/")).text();
    expect(body).toContain('<meta name="robots" content="noindex, nofollow">');
  });
});

describe("an toàn", () => {
  it("trang không tồn tại trả 404", async () => {
    const res = await get("/khong-co");
    expect(res.status).toBe(404);
  });

  it("có header chống đoán kiểu nội dung", async () => {
    const res = await get("/");
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("trang mẫu /demo không có ở production", async () => {
    const res = await get("/demo");
    expect(res.status).toBe(404);
  });
});
