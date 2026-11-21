/** Trang phụ cấp HLV (PLAN Công đoạn 11) trên dữ liệu GIẢ LẬP; trang cũ không đổi. */
import { beforeEach, describe, expect, it } from "vitest";
import { BASE, db, page, request, reset, seed, tableRows } from "./helpers";

async function insertStipends(districtId: number, documentId: number): Promise<number> {
  const res = await db
    .prepare(
      `INSERT INTO schedules (district_id, school_year, schedule_type, title, pay_basis,
                              source_document_id, source_page, status, published_at)
       VALUES (?, '2025-26', 'extra_duty', 'Athletic Stipends', 'annual', ?, 9, 'published',
               '2026-11-20T00:00:00Z')`,
    )
    .bind(districtId, documentId)
    .run();
  const id = Number(res.meta.last_row_id);
  const rows: [string, number | null][] = [
    ["Head Football Coach", 650_000],
    ["Assistant Football Coach", 350_000],
    ["Head Volleyball Coach", 420_000],
    ["Band Director", null],
  ];
  for (const [i, [label, cents]] of rows.entries()) {
    const step = await db
      .prepare("INSERT INTO steps (schedule_id, position, label_raw) VALUES (?, ?, ?)")
      .bind(id, i + 1, label)
      .run();
    await db
      .prepare(
        "INSERT INTO cells (schedule_id, step_id, lane_id, amount_cents, note) VALUES (?, ?, NULL, ?, ?)",
      )
      .bind(id, Number(step.meta.last_row_id), cents, cents === null ? "N/A" : null)
      .run();
  }
  return id;
}

const A = "/test-state/test-valley-unified";
const B = "/test-state/canon-test";

describe("phụ cấp HLV", () => {
  let oldSitemap = "";
  beforeEach(async () => {
    await reset();
    const { a } = await seed();
    oldSitemap = await page("/sitemap.xml");
    await insertStipends(a.districtId, a.documentId);
  });

  it("trang coaching-stipends có bảng, canonical riêng và nguồn", async () => {
    const res = await request(`${A}/coaching-stipends`, {}, { INDEXABLE: "true" });
    expect(res.status).toBe(200);
    const html = await res.text();
    expect(html).toContain("Coaching Stipends 2025");
    expect(html).toContain(`<link rel="canonical" href="${BASE}${A}/coaching-stipends">`);
    expect(html).toContain('content="index, follow"');
    const id = html.match(/id="(stipends-\d+)"/)?.[1] ?? "";
    const rows = tableRows(html, id);
    expect(rows[0]).toEqual(["Head Football Coach", "$6,500"]);
    expect(rows).toHaveLength(4);
    expect(html).toContain("Source document");
  });

  it("học khu không có bảng phụ cấp: 404", async () => {
    expect((await request(`${B}/coaching-stipends`)).status).toBe(404);
  });

  it("trang học khu thêm liên kết, bảng giáo viên giữ nguyên", async () => {
    const html = await page(A);
    expect(html).toContain(`href="${A}/coaching-stipends"`);
    expect(html).toContain("More pay at this district");
    expect(html).toContain("Certificated Salary Schedule");
    expect(html).not.toContain("Head Football Coach");
    expect(await page(B)).not.toContain("More pay at this district");
  });

  it("sitemap cũ không đổi; sitemap riêng và robots.txt có trang mới", async () => {
    expect(await page("/sitemap.xml")).toBe(oldSitemap);
    const extra = await page("/sitemap-extra-pay.xml");
    expect(extra).toContain(`${BASE}${A}/coaching-stipends`);
    expect(extra).not.toContain("canon-test");
    const robots = await page("/robots.txt", { INDEXABLE: "true" });
    expect(robots).toContain("Sitemap: https://example.invalid/sitemap.xml");
    expect(robots).toContain("Sitemap: https://example.invalid/sitemap-extra-pay.xml");
  });

  it("mọi URL trong sitemap cũ vẫn 200 với canonical như cũ", async () => {
    const locs = [...oldSitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1] ?? "");
    expect(locs.length).toBeGreaterThan(0);
    for (const loc of locs) {
      const res = await request(loc.replace(BASE, ""));
      expect(res.status, loc).toBe(200);
      const html = await res.text();
      expect(html, loc).toContain(`<link rel="canonical" href="${loc}">`);
    }
  });
});
