import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import {
  countSameNameInState,
  getCoverage,
  getPayOverview,
  listRecentlyUpdated,
  median,
} from "../src";
import { oddLanes, standard, stepsOnly } from "./fixtures";
import { insertFixture, resetData } from "./insert";

const db = env.DB;

const SUMMARY = `INSERT INTO district_summary (district_id, school_year, schedule_id, start_ba_cents,
                   ma_step10_cents, max_salary_cents, computed_at)
                 VALUES (?, ?, ?, ?, ?, ?, '2026-11-12T08:00:00Z')`;

/** a, b: bảng published; c: chỉ có bảng draft. */
async function seed() {
  const a = await insertFixture(db, standard);
  const b = await insertFixture(db, oddLanes);
  const c = await insertFixture(db, stepsOnly, "draft");
  const summary = db.prepare(SUMMARY);
  await summary.bind(a.districtId, "2025-26", a.scheduleId, 5_000_000, 6_000_000, 6_200_000).run();
  await summary.bind(b.districtId, "2024-25", b.scheduleId, 4_000_000, null, 5_700_000).run();
  await summary.bind(c.districtId, "2025-26", c.scheduleId, 1_000_000, null, 9_900_000).run();
  await db
    .prepare("UPDATE districts SET enrollment = 1000 WHERE id IN (?, ?, ?)")
    .bind(a.districtId, b.districtId, c.districtId)
    .run();
  await db
    .prepare("UPDATE schedules SET published_at = '2026-11-14T00:00:00Z' WHERE id = ?")
    .bind(b.scheduleId)
    .run();
  return { a, b, c };
}

beforeEach(async () => {
  await resetData(db);
});

describe("số liệu tổng hợp", () => {
  it("trung vị", () => {
    expect(median([])).toBeNull();
    expect(median([3, 1, 2])).toBe(2);
    expect(median([400, 100, 300, 200])).toBe(300); // (200 + 300) / 2 = 250 cent, làm tròn tới đô la
    expect(median([5_000_000, 6_000_001])).toBe(5_500_000);
  });

  it("chỉ tính bảng published; thấp nhất và cao nhất kèm học khu", async () => {
    await seed();
    const pay = await getPayOverview(db);
    expect(pay.start).toEqual({ cents: 4_500_000, districts: 2 });
    expect(pay.maStep10).toEqual({ cents: 6_000_000, districts: 1 });
    expect(pay.max).toEqual({ cents: 5_950_000, districts: 2 });
    expect(pay.lowestStart?.slug).toBe("canon-test");
    expect(pay.highestStart?.slug).toBe("test-valley-unified");
    expect(pay.highestMax).toMatchObject({ slug: "test-valley-unified", cents: 6_200_000 });
    expect((await getPayOverview(db, "ZZ")).start.districts).toBe(2);
    expect((await getPayOverview(db, "CA")).start).toEqual({ cents: null, districts: 0 });
  });

  it("bảng không tính theo năm không vào trung vị", async () => {
    const { b } = await seed();
    await db
      .prepare("UPDATE schedules SET pay_basis = 'daily' WHERE id = ?")
      .bind(b.scheduleId)
      .run();
    expect((await getPayOverview(db)).start).toEqual({ cents: 5_000_000, districts: 1 });
  });

  it("độ phủ: học khu có bảng published và học sinh của họ", async () => {
    await seed();
    expect(await getCoverage(db)).toEqual({
      states: 1,
      districts: 2,
      students: 2000,
      schedules: 2,
    });
  });

  it("mới cập nhật: bảng publish gần nhất trước, có phân trang và lọc bang", async () => {
    await seed();
    const recent = await listRecentlyUpdated(db, { limit: 10 });
    expect(recent.map((r) => r.slug)).toEqual(["canon-test", "test-valley-unified"]);
    expect(recent[0]).toMatchObject({
      stateSlug: "test-state",
      schedules: 1,
      schoolYear: "2024-25",
    });
    expect((await listRecentlyUpdated(db, { limit: 1, offset: 1 })).map((r) => r.slug)).toEqual([
      "test-valley-unified",
    ]);
    expect(await listRecentlyUpdated(db, { limit: 10, stateCode: "CA" })).toEqual([]);
  });

  it("đếm học khu cùng tên trong cùng bang", async () => {
    const { a, b } = await seed();
    expect(await countSameNameInState(db, a.districtId)).toBe(1);
    await db
      .prepare("UPDATE districts SET name = (SELECT name FROM districts WHERE id = ?) WHERE id = ?")
      .bind(a.districtId, b.districtId)
      .run();
    expect(await countSameNameInState(db, a.districtId)).toBe(2);
  });
});
