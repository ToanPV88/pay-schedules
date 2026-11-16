import { env } from "cloudflare:workers";
import { deleteOldErrorReports, REPORT_RETENTION_DAYS } from "@pay-schedules/db";
import { beforeEach, describe, expect, it } from "vitest";
import worker from "../src/index";
import { db, page, reset, seed } from "./helpers";

async function addReport(districtId: number, createdAt: string): Promise<void> {
  await db
    .prepare(
      "INSERT INTO error_reports (district_id, page_path, message, created_at) VALUES (?, ?, ?, ?)",
    )
    .bind(districtId, "/test-state/test-valley-unified", "Step 3 looks wrong here.", createdAt)
    .run();
}

async function countReports(): Promise<number> {
  const row = await db.prepare("SELECT COUNT(*) AS n FROM error_reports").first<{ n: number }>();
  return row?.n ?? -1;
}

describe("thời hạn lưu báo lỗi (D-109)", () => {
  beforeEach(async () => {
    await reset();
  });

  it("xóa báo lỗi gửi quá 180 ngày, giữ báo lỗi mới", async () => {
    const { a } = await seed();
    const now = new Date("2026-11-16T12:00:00Z");
    await addReport(a.districtId, "2026-05-01T00:00:00Z"); // 199 ngày
    await addReport(a.districtId, "2026-05-20T11:59:59Z"); // vừa quá 180 ngày
    await addReport(a.districtId, "2026-06-01T00:00:00Z"); // 168 ngày
    expect(REPORT_RETENTION_DAYS).toBe(180);
    expect(await deleteOldErrorReports(db, REPORT_RETENTION_DAYS, now)).toBe(2);
    expect(await countReports()).toBe(1);
  });

  it("việc định kỳ của Worker gọi việc xóa", async () => {
    const { a } = await seed();
    await addReport(a.districtId, "2020-01-01T00:00:00Z");
    const waits: Promise<unknown>[] = [];
    const ctx = {
      waitUntil: (p: Promise<unknown>) => waits.push(p),
      passThroughOnException: () => {},
      props: {},
    } as unknown as ExecutionContext;
    const controller = { cron: "41 9 * * *", scheduledTime: Date.now(), noRetry: () => {} };
    await worker.scheduled(controller as ScheduledController, env, ctx);
    await Promise.all(waits);
    expect(await countReports()).toBe(0);
  });

  it("trang Privacy ghi đúng thời hạn và việc đếm theo IP", async () => {
    const html = await page("/privacy");
    expect(html).toContain(`deleted ${REPORT_RETENTION_DAYS} days after they are sent`);
    expect(html).toContain("kept in memory only");
  });

  it("footer có dòng bản quyền", async () => {
    const html = await page("/about");
    expect(html).toMatch(/<p class="copyright">© \d{4} Pay Schedules\./);
  });
});
