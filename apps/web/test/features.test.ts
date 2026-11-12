/** Báo lỗi, xóa cache và các hàm thuần (máy tính, so sánh, định dạng, Turnstile). */
import { beforeEach, describe, expect, it } from "vitest";
import { standard } from "../../../packages/db/test/fixtures";
import { cachePurger, tokensMatch } from "../src/cache";
import { calculate, positionToIndex } from "../src/calc";
import { compareCell, parseDistrictKeys } from "../src/compare";
import { DEMO_SCHEDULE } from "../src/demo";
import { formatCents, formatDate, safeHttpUrl } from "../src/format";
import { SITEVERIFY_URL, verifyTurnstile } from "../src/turnstile";
import { db, form, page, request, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});

async function countReports(): Promise<number | undefined> {
  const row = await db.prepare("SELECT COUNT(*) AS n FROM error_reports").first<{ n: number }>();
  return row?.n;
}

const REPORTS_ON = {
  TURNSTILE_SITE_KEY: "1x00000000000000000000AA",
  TURNSTILE_SECRET_KEY: "test-secret",
};

describe("form báo lỗi", () => {
  it("tắt khi chưa có khóa Turnstile: không có nút, đường dẫn trả 404", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).not.toContain("Report an error</a>");
    expect((await request("/report?d=test-state/test-valley-unified")).status).toBe(404);
    const post = form({ d: "test-state/test-valley-unified", message: "x".repeat(20) });
    expect((await request("/report", post)).status).toBe(404);
  });

  it("bật khi có khóa: nút trên trang học khu, form có Turnstile", async () => {
    const { a } = await seed();
    const html = await page("/test-state/test-valley-unified", REPORTS_ON);
    expect(html).toContain(`href="/report?d=test-state/test-valley-unified&amp;s=${a.scheduleId}"`);
    const path = `/report?d=test-state/test-valley-unified&s=${a.scheduleId}`;
    const report = await page(path, REPORTS_ON);
    expect(report).toContain('class="cf-turnstile" data-sitekey="1x00000000000000000000AA"');
    expect(report).toContain("challenges.cloudflare.com/turnstile/v0/api.js");
  });

  it("từ chối nội dung quá ngắn, bảng không published, token rỗng; không lưu gì", async () => {
    const { a, c } = await seed();
    const key = "test-state/test-valley-unified";
    const short = await request("/report", form({ d: key, message: "short" }), REPORTS_ON);
    expect(short.status).toBe(400);
    const draft = form({ d: key, s: String(c.scheduleId), message: "x".repeat(20) });
    expect((await request("/report", draft, REPORTS_ON)).status).toBe(400);
    const noToken = form({ d: key, s: String(a.scheduleId), message: "x".repeat(20) });
    const res = await request("/report", noToken, REPORTS_ON);
    expect(res.status).toBe(400);
    expect(await res.text()).toContain("The spam check did not pass");
    expect(await countReports()).toBe(0);
  });

  it("trường bẫy bị điền: báo đã nhận nhưng không lưu", async () => {
    await seed();
    const key = "test-state/test-valley-unified";
    const bot = form({ d: key, message: "x".repeat(20), website: "x" });
    const res = await request("/report", bot, REPORTS_ON);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("Report received");
    expect(await countReports()).toBe(0);
  });
});

describe("Turnstile", () => {
  it("gửi secret, token và IP tới Siteverify; chỉ success true mới qua", async () => {
    const calls: { url: string; body: FormData }[] = [];
    const fake = (ok: boolean) =>
      (async (url: RequestInfo | URL, init?: RequestInit) => {
        calls.push({ url: String(url), body: init?.body as FormData });
        return Response.json({ success: ok });
      }) as typeof fetch;
    expect(await verifyTurnstile("s", "t", "203.0.113.1", fake(true))).toBe(true);
    expect(calls[0]?.url).toBe(SITEVERIFY_URL);
    expect(calls[0]?.body.get("secret")).toBe("s");
    expect(calls[0]?.body.get("response")).toBe("t");
    expect(calls[0]?.body.get("remoteip")).toBe("203.0.113.1");
    expect(await verifyTurnstile("s", "t", null, fake(false))).toBe(false);
    expect(await verifyTurnstile("s", "", null, fake(true))).toBe(false);
    const broken = (async () => {
      throw new Error("network");
    }) as typeof fetch;
    expect(await verifyTurnstile("s", "t", null, broken)).toBe(false);
  });
});

describe("xóa cache khi publish", () => {
  const purge = (ids: unknown, token = "Bearer test-token") => ({
    method: "POST",
    headers: { Authorization: token, "Content-Type": "application/json" },
    body: JSON.stringify({ districtIds: ids }),
  });
  const ENV = { PURGE_TOKEN: "test-token" };

  it("cần token đúng", async () => {
    const { a } = await seed();
    expect((await request("/internal/purge", purge([a.districtId], ""), ENV)).status).toBe(401);
    expect((await request("/internal/purge", purge([a.districtId], "Bearer x"), ENV)).status).toBe(
      401,
    );
    // Chưa đặt PURGE_TOKEN: luôn từ chối.
    expect((await request("/internal/purge", purge([a.districtId]))).status).toBe(401);
  });

  it("xóa trang học khu, học khu lân cận, bang, trang chủ, sitemap, so sánh", async () => {
    const { a, b } = await seed();
    const seen: unknown[] = [];
    const ctx = {
      waitUntil: () => {},
      passThroughOnException: () => {},
      props: {},
      cache: {
        purge: async (options: unknown) => {
          seen.push(options);
          return { success: true };
        },
      },
    } as unknown as ExecutionContext;
    const res = await request("/internal/purge", purge([a.districtId]), ENV, ctx);
    expect(res.status).toBe(200);
    const tags = (seen[0] as { tags: string[] }).tags;
    for (const tag of [
      `district-${a.districtId}`,
      `district-${b.districtId}`,
      "state-zz",
      "home",
      "sitemap",
      "compare",
    ]) {
      expect(tags, tag).toContain(tag);
    }
  });

  it("không có Workers Cache trong môi trường: trả 501 kèm danh sách thẻ", async () => {
    const { a } = await seed();
    const res = await request("/internal/purge", purge([a.districtId]), ENV);
    expect(res.status).toBe(501);
    expect(((await res.json()) as { tags: string[] }).tags).toContain(`district-${a.districtId}`);
    expect((await request("/internal/purge", purge([]), ENV)).status).toBe(400);
  });

  it("nhận diện ctx.cache và so token", async () => {
    expect(cachePurger(undefined)).toBeNull();
    expect(cachePurger({})).toBeNull();
    expect(cachePurger({ cache: { purge: async () => ({ success: true }) } })).not.toBeNull();
    expect(await tokensMatch("abc", "abc")).toBe(true);
    expect(await tokensMatch("abd", "abc")).toBe(false);
  });
});

describe("hàm thuần", () => {
  it("định dạng tiền và ngày", () => {
    expect(formatCents(5_000_000)).toBe("$50,000");
    expect(formatCents(2_550)).toBe("$25.50");
    expect(formatCents(123_456_789)).toBe("$1,234,567.89");
    expect(formatCents(-15_000)).toBe("-$150");
    expect(formatDate("2026-11-12T07:00:00Z")).toBe("November 12, 2026");
    expect(formatDate("not a date")).toBe("not a date");
  });

  it("chỉ nhận link http và https", () => {
    expect(safeHttpUrl("https://example.invalid/a.pdf")).toBe("https://example.invalid/a.pdf");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("not a url")).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });

  it("máy tính đọc đúng ô, không nội suy", () => {
    const first = calculate(DEMO_SCHEDULE, 0, 0);
    expect(first?.amountCents).toBe(5_000_000);
    expect(first?.nextStepRaiseCents).toBe(150_000);
    expect(first?.perDayCents).toBe(Math.round(5_000_000 / 185));
    // Ô trống có ghi chú: không có số, không có phép tính nào.
    const empty = calculate(DEMO_SCHEDULE, 3, 0);
    expect(empty?.amountCents).toBeNull();
    expect(empty?.note).toBe("No initial placement in this lane");
    expect(calculate(DEMO_SCHEDULE, 9, 0)).toBeNull();
    expect(calculate(DEMO_SCHEDULE, 0, 99)).toBeNull();
    expect(positionToIndex("3", 5)).toBe(2);
    expect(positionToIndex("9", 5)).toBe(0);
    expect(positionToIndex("-1", 5)).toBe(0);
    expect(positionToIndex(undefined, 5)).toBe(0);
  });

  it("đọc danh sách học khu cần so sánh: bỏ mục sai, trùng, quá bốn", () => {
    const keys = parseDistrictKeys("a/b,a/b,BAD,c/d,e/f,g/h,i/j");
    expect(keys.map((k) => `${k.stateSlug}/${k.districtSlug}`)).toEqual([
      "a/b",
      "c/d",
      "e/f",
      "g/h",
    ]);
    expect(parseDistrictKeys(undefined)).toEqual([]);
  });

  it("ô so sánh theo lane chuẩn hóa và vị trí bậc", () => {
    expect(compareCell(DEMO_SCHEDULE, "MA", 2).amountCents).toBe(5_550_000);
    expect(compareCell(DEMO_SCHEDULE, "PhD", 1).reason).toBe("No PhD lane on this schedule");
    expect(compareCell(DEMO_SCHEDULE, "MA", 99).reason).toBe("Schedule has 15 steps");
    expect(compareCell(null, "MA", 1).reason).toBe("No published schedule");
    expect(standard.lanes.length).toBe(4);
  });
});
