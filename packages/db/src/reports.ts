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
