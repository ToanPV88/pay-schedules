/**
 * Số liệu tổng hợp cho trang chủ, trang bang và trang "Recently updated": học khu có bảng, học
 * sinh được phủ, trung vị lương ở ba mốc, học khu mới cập nhật. Chỉ đọc, không đổi schema.
 */
import { displayName, displayNameOrNull } from "./names";

/** Một học khu ở một mốc lương (dùng cho thấp nhất/cao nhất). */
export interface DistrictAmount {
  name: string;
  slug: string;
  stateSlug: string;
  stateName: string;
  cents: number;
}

/** Trung vị một mốc lương và số học khu dùng để tính. */
export interface Median {
  cents: number | null;
  districts: number;
}

export interface PayOverview {
  /** Trung vị lương khởi điểm (BA bậc 1), MA bậc 10 và mức tối đa của bảng tính theo năm. */
  start: Median;
  maStep10: Median;
  max: Median;
  lowestStart: DistrictAmount | null;
  highestStart: DistrictAmount | null;
  highestMax: DistrictAmount | null;
}

export interface Coverage {
  states: number;
  districts: number;
  students: number;
  schedules: number;
}

interface SummaryRow {
  name: string;
  slug: string;
  state_slug: string;
  state_name: string;
  start_ba_cents: number | null;
  ma_step10_cents: number | null;
  max_salary_cents: number | null;
}

// Mốc của năm mới nhất mỗi học khu, chỉ từ bảng giáo viên published tính theo năm: lương ngày và
// lương năm không so được với nhau.
const SQL_LATEST_SUMMARY = `
  WITH latest AS (
    SELECT ds.district_id, ds.start_ba_cents, ds.ma_step10_cents, ds.max_salary_cents,
           ROW_NUMBER() OVER (PARTITION BY ds.district_id ORDER BY ds.school_year DESC) AS rn
      FROM district_summary ds
      JOIN schedules s ON s.id = ds.schedule_id
     WHERE s.status = 'published' AND s.schedule_type = 'teacher' AND s.pay_basis = 'annual'
  )
  SELECT d.name, d.slug, st.slug AS state_slug, st.name AS state_name,
         l.start_ba_cents, l.ma_step10_cents, l.max_salary_cents
    FROM latest l
    JOIN districts d ON d.id = l.district_id AND d.active = 1
    JOIN states st ON st.code = d.state
   WHERE l.rn = 1`;

export function median(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const upper = sorted[mid] ?? 0;
  if (sorted.length % 2 === 1) {
    return upper;
  }
  // Trung bình hai số giữa, làm tròn tới đô la: trung vị là số tham khảo, không phải ô của bảng.
  return Math.round(((sorted[mid - 1] ?? upper) + upper) / 200) * 100;
}

function medianOf(rows: SummaryRow[], pick: (r: SummaryRow) => number | null): Median {
  const values = rows.map(pick).filter((v): v is number => v !== null);
  return { cents: median(values), districts: values.length };
}

function extreme(
  rows: SummaryRow[],
  pick: (r: SummaryRow) => number | null,
  better: (a: number, b: number) => boolean,
): DistrictAmount | null {
  let best: SummaryRow | null = null;
  let bestValue = 0;
  for (const row of rows) {
    const value = pick(row);
    if (value !== null && (best === null || better(value, bestValue))) {
      best = row;
      bestValue = value;
    }
  }
  if (best === null) {
    return null;
  }
  return {
    name: displayName(best.name),
    slug: best.slug,
    stateSlug: best.state_slug,
    stateName: best.state_name,
    cents: bestValue,
  };
}

/** Trung vị và thấp nhất/cao nhất của toàn site, hoặc của một bang khi có `stateCode`. */
export async function getPayOverview(db: D1Database, stateCode?: string): Promise<PayOverview> {
  const sql = stateCode ? `${SQL_LATEST_SUMMARY} AND d.state = ?` : SQL_LATEST_SUMMARY;
  const stmt = stateCode ? db.prepare(sql).bind(stateCode) : db.prepare(sql);
  const { results } = await stmt.all<SummaryRow>();
  const start = (r: SummaryRow) => r.start_ba_cents;
  const max = (r: SummaryRow) => r.max_salary_cents;
  return {
    start: medianOf(results, start),
    maStep10: medianOf(results, (r) => r.ma_step10_cents),
    max: medianOf(results, max),
    lowestStart: extreme(results, start, (a, b) => a < b),
    highestStart: extreme(results, start, (a, b) => a > b),
    highestMax: extreme(results, max, (a, b) => a > b),
  };
}

const SQL_COVERAGE = `
  SELECT COUNT(DISTINCT d.state) AS states,
         COUNT(*) AS districts,
         COALESCE(SUM(d.enrollment), 0) AS students,
         COALESCE(SUM(p.schedules), 0) AS schedules
    FROM districts d
    JOIN (SELECT district_id, COUNT(*) AS schedules FROM schedules
           WHERE status = 'published' AND schedule_type = 'teacher'
           GROUP BY district_id) p ON p.district_id = d.id
   WHERE d.active = 1`;

/** Số bang, học khu, học sinh và bảng lương giáo viên published trên site. */
export async function getCoverage(db: D1Database): Promise<Coverage> {
  const row = await db.prepare(SQL_COVERAGE).first<Coverage>();
  return row ?? { states: 0, districts: 0, students: 0, schedules: 0 };
}

export interface RecentDistrict {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  stateSlug: string;
  stateName: string;
  schoolYear: string;
  schedules: number;
  updatedAt: string;
}

interface RecentRow {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  state_slug: string;
  state_name: string;
  school_year: string;
  schedules: number;
  updated_at: string;
}

const SQL_RECENT = `
  SELECT d.id, d.name, d.slug, d.city, st.slug AS state_slug, st.name AS state_name,
         MAX(s.school_year) AS school_year, COUNT(*) AS schedules,
         MAX(s.published_at) AS updated_at
    FROM schedules s
    JOIN districts d ON d.id = s.district_id AND d.active = 1
    JOIN states st ON st.code = d.state
   WHERE s.status = 'published' AND s.schedule_type = 'teacher'`;

/** Học khu có bảng giáo viên published, bảng mới publish gần nhất trước. */
export async function listRecentlyUpdated(
  db: D1Database,
  options: { limit: number; offset?: number; stateCode?: string },
): Promise<RecentDistrict[]> {
  const filter = options.stateCode ? " AND d.state = ?" : "";
  const sql = `${SQL_RECENT}${filter}
   GROUP BY d.id
   ORDER BY updated_at DESC, d.name
   LIMIT ? OFFSET ?`;
  const params: unknown[] = options.stateCode ? [options.stateCode] : [];
  params.push(options.limit, options.offset ?? 0);
  const { results } = await db
    .prepare(sql)
    .bind(...params)
    .all<RecentRow>();
  return results.map((r) => ({
    id: r.id,
    name: displayName(r.name),
    slug: r.slug,
    city: displayNameOrNull(r.city),
    stateSlug: r.state_slug,
    stateName: r.state_name,
    schoolYear: r.school_year,
    schedules: r.schedules,
    updatedAt: r.updated_at,
  }));
}
