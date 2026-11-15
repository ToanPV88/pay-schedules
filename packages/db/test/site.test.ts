import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import {
  buildSearchQuery,
  countDistrictsOfState,
  displayName,
  getDistrictBySlug,
  getLatestSummary,
  getPublishedScheduleDistrict,
  insertErrorReport,
  listDistrictsOfState,
  listNeighbors,
  listPublishedSchedules,
  listSitemapRows,
  listStates,
  listYearHistory,
  searchDistricts,
} from "../src";
import { oddLanes, standard, stepsOnly } from "./fixtures";
import { insertFixture, resetData } from "./insert";

const db = env.DB;

const SUMMARY = `INSERT INTO district_summary (district_id, school_year, schedule_id, start_ba_cents,
                   ma_step10_cents, max_salary_cents, computed_at)
                 VALUES (?, ?, ?, ?, ?, ?, '2026-11-12T08:00:00Z')`;

/** Ba học khu: hai có bảng published (a, b), một chỉ có bảng draft (c). */
async function seed() {
  const a = await insertFixture(db, standard);
  const b = await insertFixture(db, oddLanes);
  const c = await insertFixture(db, stepsOnly, "draft");
  const summary = db.prepare(SUMMARY);
  await summary.bind(a.districtId, "2025-26", a.scheduleId, 5_000_000, null, 6_200_000).run();
  await summary.bind(b.districtId, "2024-25", b.scheduleId, null, null, 5_700_000).run();
  await db
    .prepare("INSERT INTO district_neighbors VALUES (?, ?, 12.5), (?, ?, 30)")
    .bind(a.districtId, b.districtId, a.districtId, c.districtId)
    .run();
  return { a, b, c };
}

beforeEach(async () => {
  await db.prepare("DELETE FROM error_reports").run();
  await resetData(db);
});

describe("bang và học khu", () => {
  it("đếm học khu và học khu có bảng published", async () => {
    await seed();
    const states = await listStates(db);
    expect(states).toEqual([
      { code: "ZZ", name: "Test State", slug: "test-state", districts: 3, withSchedule: 2 },
    ]);
    expect(await countDistrictsOfState(db, "ZZ")).toEqual({ districts: 3, withSchedule: 2 });
  });

  it("danh sách học khu kèm mốc so sánh; thiếu số luôn xếp cuối", async () => {
    await seed();
    const byName = await listDistrictsOfState(db, "ZZ", {
      sort: "name",
      dir: "asc",
      limit: 50,
      offset: 0,
    });
    expect(byName.map((d) => d.slug)).toEqual(["canon-test", "test-ridge", "test-valley-unified"]);
    expect(byName.map((d) => d.hasSchedule)).toEqual([true, false, true]);
    expect(byName[2]?.summary?.startBaCents).toBe(5_000_000);
    for (const dir of ["asc", "desc"] as const) {
      const byStart = await listDistrictsOfState(db, "ZZ", {
        sort: "start",
        dir,
        limit: 50,
        offset: 0,
      });
      expect(byStart[0]?.slug).toBe("test-valley-unified");
    }
  });

  it("học khu tìm theo slug, kèm bang", async () => {
    await seed();
    const d = await getDistrictBySlug(db, "test-state", "canon-test");
    expect(d?.name).toBe("Cañon Test School District");
    expect(d?.state).toEqual({ code: "ZZ", name: "Test State", slug: "test-state" });
    expect(await getDistrictBySlug(db, "test-state", "khong-co")).toBeNull();
  });
});

describe("chỉ dữ liệu published ra ngoài", () => {
  it("bảng draft không có trong danh sách, lịch sử, sitemap", async () => {
    const { a, c } = await seed();
    expect((await listPublishedSchedules(db, a.districtId)).map((s) => s.id)).toEqual([
      a.scheduleId,
    ]);
    expect(await listPublishedSchedules(db, c.districtId)).toEqual([]);
    expect(await listYearHistory(db, c.districtId)).toEqual([]);
    expect(await getPublishedScheduleDistrict(db, c.scheduleId)).toBeNull();
    expect(await getPublishedScheduleDistrict(db, a.scheduleId)).toBe(a.districtId);
    // canon-test không có lân cận (trang noindex) nên không nằm trong sitemap; c chỉ có draft.
    const sitemap = await listSitemapRows(db);
    expect(sitemap.map((r) => r.districtSlug)).toEqual(["test-valley-unified"]);
  });

  it("sitemap chỉ gồm trang được index: lân cận phải có số so sánh của bảng published", async () => {
    const { a, b } = await seed();
    await db
      .prepare("INSERT INTO district_neighbors VALUES (?, ?, 12.5)")
      .bind(b.districtId, a.districtId)
      .run();
    expect((await listSitemapRows(db)).map((r) => r.districtSlug)).toEqual([
      "canon-test",
      "test-valley-unified",
    ]);
    // lân cận duy nhất của a là b (và c chỉ có draft): b không còn bảng published thì a rớt
    await db
      .prepare("DELETE FROM district_neighbors WHERE district_id = ? AND neighbor_id = ?")
      .bind(a.districtId, b.districtId)
      .run();
    expect((await listSitemapRows(db)).map((r) => r.districtSlug)).toEqual(["canon-test"]);
  });

  it("lịch sử năm học có ô thấp nhất và cao nhất", async () => {
    const { a } = await seed();
    expect(await listYearHistory(db, a.districtId)).toEqual([
      { schoolYear: "2025-26", schedules: 1, minCents: 5_000_000, maxCents: 6_200_000 },
    ]);
  });

  it("học khu lân cận chỉ gồm học khu có số liệu so sánh", async () => {
    const { a, b } = await seed();
    const neighbors = await listNeighbors(db, a.districtId, 10);
    expect(neighbors.map((n) => n.id)).toEqual([b.districtId]);
    expect(neighbors[0]?.summary.maxSalaryCents).toBe(5_700_000);
    expect((await getLatestSummary(db, a.districtId))?.schoolYear).toBe("2025-26");
  });
});

describe("tìm kiếm", () => {
  it("chỉ giữ chữ và số, mỗi từ khớp tiền tố", () => {
    expect(buildSearchQuery('  Test "valley"* OR x ')).toBe('"Test"* "valley"* "OR"* "x"*');
    expect(buildSearchQuery("<>!!")).toBeNull();
    expect(buildSearchQuery("")).toBeNull();
  });

  it("tìm theo tên, thành phố, quận; không phân biệt dấu", async () => {
    await seed();
    const slugs = async (q: string) => (await searchDistricts(db, q, 10)).map((h) => h.slug);
    expect(await slugs("valley")).toEqual(["test-valley-unified"]);
    expect(await slugs("canon")).toEqual(["canon-test"]);
    expect(await slugs("fremont")).toEqual(["canon-test"]);
    expect(await slugs("tes ridg")).toEqual(["test-ridge"]);
    expect(await slugs('"; DROP TABLE districts; --')).toEqual([]);
    expect(await slugs("zzz")).toEqual([]);
  });
});

describe("báo lỗi", () => {
  it("ghi báo lỗi; nội dung quá ngắn bị schema từ chối", async () => {
    const { a } = await seed();
    const report = {
      districtId: a.districtId,
      scheduleId: a.scheduleId,
      pagePath: "/test-state/test-valley-unified",
      message: "Step 3 in the MA lane looks wrong.",
    };
    const id = await insertErrorReport(db, report);
    expect(id).toBeGreaterThan(0);
    await expect(insertErrorReport(db, { ...report, message: "short" })).rejects.toThrow();
  });
});

describe("tên hiển thị (D-105)", () => {
  it("tên viết hoa toàn bộ đổi sang Title Case, giữ viết tắt và số La Mã", () => {
    expect(displayName("LITTLEFIELD ISD")).toBe("Littlefield ISD");
    expect(displayName("SCHOOL DISTRICT OF THE CITY OF ERIE")).toBe(
      "School District of the City of Erie",
    );
    expect(displayName("SPRINGFIELD R-XII")).toBe("Springfield R-XII");
    const stMarys = displayName("ST. MARY'S COUNTY PUBLIC SCHOOLS");
    expect(stMarys).toBe("St. Mary's County Public Schools");
    expect(displayName("O'NEILL PUBLIC SCHOOLS")).toBe("O'Neill Public Schools");
    expect(displayName("CAÑON CITY RE-1")).toBe("Cañon City RE-1");
  });

  it("tên đã có chữ thường thì giữ nguyên", () => {
    expect(displayName("DeSoto Cons SD 86")).toBe("DeSoto Cons SD 86");
    expect(displayName("MS Achievement SD Of Yazoo City")).toBe("MS Achievement SD Of Yazoo City");
  });

  it("trang trả tên hiển thị, dữ liệu gốc không đổi", async () => {
    const { a } = await seed();
    await db
      .prepare("UPDATE districts SET name = 'TEST VALLEY ISD', city = 'TESTVILLE' WHERE id = ?")
      .bind(a.districtId)
      .run();
    const district = await getDistrictBySlug(db, "test-state", "test-valley-unified");
    expect(district?.name).toBe("Test Valley ISD");
    expect(district?.city).toBe("Testville");
    const raw = await db
      .prepare("SELECT name FROM districts WHERE id = ?")
      .bind(a.districtId)
      .first<{ name: string }>();
    expect(raw?.name).toBe("TEST VALLEY ISD");
  });
});
