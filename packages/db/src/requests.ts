/**
 * Yêu cầu bổ sung bảng lương (D-121): người xem bấm "Request this district" trên trang học khu chưa
 * có bảng. Đếm theo ngày, tối đa REQUESTS_PER_DAY_CAP mỗi học khu mỗi ngày để một người bấm liên tục
 * không đẩy học khu lên đầu danh sách ưu tiên.
 */

export const REQUESTS_PER_DAY_CAP = 20;

/** Ghi một yêu cầu cho ngày `day` (YYYY-MM-DD, UTC). */
export async function recordDistrictRequest(
  db: D1Database,
  districtId: number,
  day: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO district_requests (district_id, day, requests) VALUES (?, ?, 1)
       ON CONFLICT (district_id, day)
       DO UPDATE SET requests = MIN(requests + 1, ${REQUESTS_PER_DAY_CAP})`,
    )
    .bind(districtId, day)
    .run();
}

/** Tổng số yêu cầu của một học khu. */
export async function countDistrictRequests(db: D1Database, districtId: number): Promise<number> {
  const row = await db
    .prepare("SELECT COALESCE(SUM(requests), 0) AS n FROM district_requests WHERE district_id = ?")
    .bind(districtId)
    .first<{ n: number }>();
  return row?.n ?? 0;
}

export interface RequestedDistrict {
  id: number;
  name: string;
  state: string;
  ncesId: string | null;
  requests: number;
}

/** Học khu chưa có bảng published được yêu cầu nhiều nhất (để ưu tiên lấy dữ liệu). */
export async function listTopRequested(
  db: D1Database,
  limit: number,
): Promise<RequestedDistrict[]> {
  const { results } = await db
    .prepare(
      `SELECT d.id, d.name, d.state, d.nces_id AS ncesId, SUM(r.requests) AS requests
         FROM district_requests r
         JOIN districts d ON d.id = r.district_id
        WHERE NOT EXISTS (SELECT 1 FROM schedules s
                           WHERE s.district_id = d.id AND s.status = 'published')
        GROUP BY d.id
        ORDER BY requests DESC, d.name
        LIMIT ?`,
    )
    .bind(limit)
    .all<RequestedDistrict>();
  return results;
}
