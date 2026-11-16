/** Ghi báo lỗi của người dùng (bảng `error_reports`, migration 0010). */

export const REPORT_MIN_LENGTH = 10;
export const REPORT_MAX_LENGTH = 2000;

export interface NewErrorReport {
  districtId: number;
  scheduleId: number | null;
  pagePath: string;
  message: string;
}

const SQL_INSERT = `
  INSERT INTO error_reports (district_id, schedule_id, page_path, message)
  VALUES (?, ?, ?, ?)`;

export async function insertErrorReport(db: D1Database, report: NewErrorReport): Promise<number> {
  const stmt = db
    .prepare(SQL_INSERT)
    .bind(report.districtId, report.scheduleId, report.pagePath, report.message);
  const result = await stmt.run();
  return Number(result.meta.last_row_id);
}

/** Báo lỗi bị xóa sau số ngày này kể từ lúc gửi (DECISIONS.md D-109; trang /privacy ghi cùng số). */
export const REPORT_RETENTION_DAYS = 180;

/** Xóa báo lỗi gửi trước `now` quá `days` ngày; trả số dòng đã xóa. */
export async function deleteOldErrorReports(
  db: D1Database,
  days = REPORT_RETENTION_DAYS,
  now = new Date(),
): Promise<number> {
  // created_at dạng "2026-11-16T02:00:00Z" (không có phần nghìn giây) nên so chuỗi được.
  const cutoff = new Date(now.getTime() - days * 86_400_000).toISOString().replace(/\.\d+Z$/, "Z");
  const result = await db
    .prepare("DELETE FROM error_reports WHERE created_at < ?")
    .bind(cutoff)
    .run();
  return result.meta.changes;
}
