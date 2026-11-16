/**
 * Dòng ghi nguồn ở cuối tệp CSV và Excel (DECISIONS.md D-109): bảng thuộc học khu nào, tài liệu
 * gốc, ngày tải tài liệu, trang của site đã tổng hợp bảng. Người dùng lại dữ liệu thấy nguồn và
 * đường dẫn về site ngay trong tệp.
 */
import type { District, Schedule } from "@pay-schedules/db";
import { SITE_NAME } from "./env";
import { sourceLanding } from "./format";

export interface SourceLines {
  heading: string;
  source: string;
  compiled: string;
  verify: string;
}

export function sourceLines(district: District, schedule: Schedule, pageUrl: string): SourceLines {
  const title = schedule.title ? `${schedule.title}, ` : "";
  const source = sourceLanding(schedule.source.url)?.href ?? schedule.source.url;
  const page = schedule.source.page === null ? "" : `, page ${schedule.source.page}`;
  const retrieved = schedule.source.fetchedAt.slice(0, 10);
  return {
    heading: `${district.name}, ${title}${schedule.schoolYear}`,
    source: `Source: ${source}${page} (retrieved ${retrieved})`,
    compiled: `Compiled by ${SITE_NAME}: ${pageUrl}`,
    verify: "Verify against the source document before relying on these figures.",
  };
}
