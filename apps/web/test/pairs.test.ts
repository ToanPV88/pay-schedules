import { beforeEach, describe, expect, it } from "vitest";
import { featuredPairs, isCanonicalOrder, pairPath, parsePair } from "../src/pairs";
import { db, page, request, reset, seed } from "./helpers";

async function seedWithEnrollment() {
  const ids = await seed();
  // Valley lớn hơn Cañon: thứ tự chuẩn là valley trước. Cañon cần lương khởi điểm để thành cặp nổi bật.
  await db
    .prepare("UPDATE districts SET enrollment = 50000 WHERE id = ?")
    .bind(ids.a.districtId)
    .run();
  await db
    .prepare("UPDATE districts SET enrollment = 9000 WHERE id = ?")
    .bind(ids.b.districtId)
    .run();
  await db
    .prepare("UPDATE district_summary SET start_ba_cents = 4800000 WHERE district_id = ?")
    .bind(ids.b.districtId)
    .run();
  return ids;
}

const PATH = "/compare/zz-test-valley-unified-vs-zz-canon-test";

describe("trang so sánh hai học khu (D-118)", () => {
  beforeEach(async () => {
    await reset();
  });

  it("tách đường dẫn: đúng dạng, sai dạng, trùng nhau", () => {
    expect(parsePair("tx-houston-isd-vs-tx-dallas-isd")).toEqual([
      { stateCode: "TX", slug: "houston-isd" },
      { stateCode: "TX", slug: "dallas-isd" },
    ]);
    expect(parsePair("houston-vs-dallas")).toBeNull();
    expect(parsePair("tx-a-vs-tx-b-vs-tx-c")).toBeNull();
    expect(parsePair("tx-a-vs-tx-a")).toBeNull();
    expect(parsePair("TX-a-vs-tx-b")).toBeNull();
    expect(pairPath({ stateCode: "TX", slug: "a" }, { stateCode: "CA", slug: "b" })).toBe(
      "/compare/tx-a-vs-ca-b",
    );
  });

  it("trang đối đầu: bảng ba mốc, câu tóm tắt, bảng cùng ô; cặp nổi bật được index", async () => {
    await seedWithEnrollment();
    const html = await page(PATH, { INDEXABLE: "true" });
    expect(html).toContain(
      "<h1>Test Valley Unified School District vs Cañon Test School District teacher salary</h1>",
    );
    expect(html).toContain(
      "Starting pay is $2,000 higher in Test Valley Unified School District ($50,000 vs $48,000); the top of the scale is $5,000 higher in Test Valley Unified School District ($62,000 vs $57,000).",
    );
    expect(html).toContain('id="head-heading"');
    expect(html).toContain("$5,000 more in Test Valley Unified School District");
    expect(html).toContain('id="same-cell-heading"');
    expect(html).toContain('content="index, follow"');
    expect(html).toContain(`<link rel="canonical" href="https://example.invalid${PATH}">`);
  });

  it("thứ tự ngược chuyển 301; học khu lạ 404", async () => {
    await seedWithEnrollment();
    const res = await request("/compare/zz-canon-test-vs-zz-test-valley-unified?step=2");
    expect(res.status).toBe(301);
    expect(res.headers.get("Location")).toBe(`${PATH}?step=2`);
    expect((await request("/compare/zz-test-valley-unified-vs-zz-nowhere")).status).toBe(404);
    expect((await request("/compare/not-a-pair")).status).toBe(404);
  });

  it("cặp nổi bật: /compare gợi ý, trang học khu liên kết", async () => {
    await seedWithEnrollment();
    const compare = await page("/compare");
    expect(compare).toContain("Popular comparisons");
    expect(compare).toContain(`href="${PATH}"`);
    const district = await page("/test-state/test-valley-unified");
    expect(district).toContain(
      `<a href="${PATH}">Test Valley Unified School District vs Cañon Test School District</a>`,
    );
  });

  it("thiếu số học sinh thì không thành cặp nổi bật (noindex)", async () => {
    await seed();
    // Không có số học sinh thì xếp theo tên: Cañon đứng trước.
    const html = await page("/compare/zz-canon-test-vs-zz-test-valley-unified", {
      INDEXABLE: "true",
    });
    expect(html).toContain('content="noindex');
    expect(featuredPairs([])).toEqual([]);
    const e = (enrollment: number | null, name: string) =>
      ({ enrollment, name }) as Parameters<typeof isCanonicalOrder>[0];
    expect(isCanonicalOrder(e(10, "B"), e(5, "A"))).toBe(true);
    expect(isCanonicalOrder(e(5, "A"), e(5, "B"))).toBe(true);
    expect(isCanonicalOrder(e(null, "A"), e(1, "B"))).toBe(false);
  });
});
