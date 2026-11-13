/**
 * Truy vấn chỉ đọc cho website (Công đoạn 6). Chỉ trả dữ liệu của bảng lương `published`:
 * dữ liệu chưa qua Validate không hiện ra ngoài (AGENTS.md §2.4). "Bảng lương" ở đây là bảng
 * loại `teacher`; các loại khác thuộc Công đoạn 10.
 */

import { displayName, displayNameOrNull } from "./names";

export interface State {
  code: string;
  name: string;
  slug: string;
}

export interface StateCount extends State {
  /** Số học khu đang hoạt động. */
  districts: number;
  /** Số học khu có ít nhất một bảng lương published. */
  withSchedule: number;
}

export interface District {
  id: number;
  ncesId: string | null;
  name: string;
  slug: string;
  city: string | null;
  county: string | null;
  website: string | null;
  enrollment: number | null;
  active: boolean;
  state: State;
}

/** Ba mốc so sánh của `district_summary`. Mốc nào pipeline chưa tính được thì là null. */
export interface Summary {
  schoolYear: string;
  startBaCents: number | null;
  maStep10Cents: number | null;
  maxSalaryCents: number | null;
}

export interface DistrictListItem {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  county: string | null;
  hasSchedule: boolean;
  summary: Summary | null;
}

export interface Neighbor {
  id: number;
  name: string;
  slug: string;
  stateSlug: string;
  distanceKm: number | null;
  summary: Summary;
}

export interface PublishedSchedule {
  id: number;
  schoolYear: string;
  title: string;
  publishedAt: string | null;
}

export interface YearHistory {
  schoolYear: string;
  schedules: number;
  /** Null khi năm đó có bảng không tính theo năm (không so được). */
  minCents: number | null;
  maxCents: number | null;
}

export interface SearchHit {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  county: string | null;
  state: State;
  hasSchedule: boolean;
}

export interface SitemapRow {
  stateSlug: string;
  districtSlug: string;
  schoolYear: string;
  lastPublished: string | null;
}

export const DISTRICT_SORTS = ["name", "start", "ma10", "max"] as const;
export type DistrictSort = (typeof DISTRICT_SORTS)[number];
export type SortDirection = "asc" | "desc";

// ---------------------------------------------------------------- mảnh SQL dùng chung
// Các mảnh dưới đây là hằng số trong mã, không chứa dữ liệu người dùng.

const HAS_SCHEDULE = `EXISTS (SELECT 1 FROM schedules p
         WHERE p.district_id = d.id AND p.status = 'published' AND p.schedule_type = 'teacher')`;

/** Điều kiện nối `district_summary ds`: năm học mới nhất mà bảng nguồn còn `published`. */
const LATEST_SUMMARY = `ds.district_id = d.id AND ds.school_year = (
         SELECT MAX(x.school_year) FROM district_summary x
           JOIN schedules sx ON sx.id = x.schedule_id
          WHERE x.district_id = d.id AND sx.status = 'published')`;

const SUMMARY_COLUMNS =
  "ds.school_year, ds.start_ba_cents, ds.ma_step10_cents, ds.max_salary_cents";

interface SummaryColumns {
  school_year: string | null;
  start_ba_cents: number | null;
  ma_step10_cents: number | null;
  max_salary_cents: number | null;
}

function toSummary(row: SummaryColumns): Summary | null {
  if (row.school_year === null) {
    return null;
  }
  return {
    schoolYear: row.school_year,
    startBaCents: row.start_ba_cents,
    maStep10Cents: row.ma_step10_cents,
    maxSalaryCents: row.max_salary_cents,
  };
}

// ---------------------------------------------------------------- bang

const SQL_STATES = `
  SELECT s.code, s.name, s.slug,
         COUNT(d.id) AS districts,
         COUNT(p.district_id) AS with_schedule
    FROM states s
    LEFT JOIN districts d ON d.state = s.code AND d.active = 1
    LEFT JOIN (SELECT DISTINCT district_id FROM schedules
                WHERE status = 'published' AND schedule_type = 'teacher') p
           ON p.district_id = d.id
   GROUP BY s.code
   ORDER BY s.name`;

interface StateCountRow extends State {
  districts: number;
  with_schedule: number;
}

export async function listStates(db: D1Database): Promise<StateCount[]> {
  const { results } = await db.prepare(SQL_STATES).all<StateCountRow>();
  return results.map((r) => ({
    code: r.code,
    name: r.name,
    slug: r.slug,
    districts: r.districts,
    withSchedule: r.with_schedule,
  }));
}

export async function getStateBySlug(db: D1Database, slug: string): Promise<State | null> {
  const stmt = db.prepare("SELECT code, name, slug FROM states WHERE slug = ?").bind(slug);
  return await stmt.first<State>();
}

// ---------------------------------------------------------------- học khu

const SQL_DISTRICT = `
  SELECT d.id, d.nces_id, d.name, d.slug, d.city, d.county, d.website, d.enrollment, d.active,
         s.code AS state_code, s.name AS state_name, s.slug AS state_slug
    FROM districts d JOIN states s ON s.code = d.state`;

interface DistrictRow {
  id: number;
  nces_id: string | null;
  name: string;
  slug: string;
  city: string | null;
  county: string | null;
  website: string | null;
  enrollment: number | null;
  active: number;
  state_code: string;
  state_name: string;
  state_slug: string;
}

function toDistrict(r: DistrictRow): District {
  return {
    id: r.id,
    ncesId: r.nces_id,
    name: displayName(r.name),
    slug: r.slug,
    city: displayNameOrNull(r.city),
    county: displayNameOrNull(r.county),
    website: r.website,
    enrollment: r.enrollment,
    active: r.active === 1,
    state: { code: r.state_code, name: r.state_name, slug: r.state_slug },
  };
}

export async function getDistrictBySlug(
  db: D1Database,
  stateSlug: string,
  districtSlug: string,
): Promise<District | null> {
  const sql = `${SQL_DISTRICT} WHERE s.slug = ? AND d.slug = ?`;
  const stmt = db.prepare(sql).bind(stateSlug, districtSlug);
  const row = await stmt.first<DistrictRow>();
  return row ? toDistrict(row) : null;
}

export async function getDistrictById(db: D1Database, id: number): Promise<District | null> {
  const stmt = db.prepare(`${SQL_DISTRICT} WHERE d.id = ?`).bind(id);
  const row = await stmt.first<DistrictRow>();
  return row ? toDistrict(row) : null;
}

const SORT_COLUMNS: Record<Exclude<DistrictSort, "name">, string> = {
  start: "ds.start_ba_cents",
  ma10: "ds.ma_step10_cents",
  max: "ds.max_salary_cents",
};

function districtOrder(sort: DistrictSort, dir: SortDirection): string {
  const direction = dir === "desc" ? "DESC" : "ASC";
  if (sort === "name") {
    return `d.name COLLATE NOCASE ${direction}, d.id`;
  }
  // Học khu chưa có số liệu luôn xếp cuối, dù tăng hay giảm.
  const column = SORT_COLUMNS[sort];
  return `(${column} IS NULL), ${column} ${direction}, d.name COLLATE NOCASE, d.id`;
}

interface DistrictListRow extends SummaryColumns {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  county: string | null;
  has_schedule: number;
}

export interface DistrictListOptions {
  sort: DistrictSort;
  dir: SortDirection;
  limit: number;
  offset: number;
}

/** Học khu đang hoạt động của một bang, kèm ba mốc lương của năm mới nhất (nếu có). */
export async function listDistrictsOfState(
  db: D1Database,
  stateCode: string,
  options: DistrictListOptions,
): Promise<DistrictListItem[]> {
  const sql = `
  SELECT d.id, d.name, d.slug, d.city, d.county, ${SUMMARY_COLUMNS},
         ${HAS_SCHEDULE} AS has_schedule
    FROM districts d
    LEFT JOIN district_summary ds ON ${LATEST_SUMMARY}
   WHERE d.state = ? AND d.active = 1
   ORDER BY ${districtOrder(options.sort, options.dir)}
   LIMIT ? OFFSET ?`;
  const stmt = db.prepare(sql).bind(stateCode, options.limit, options.offset);
  const { results } = await stmt.all<DistrictListRow>();
  return results.map((r) => ({
    id: r.id,
    name: displayName(r.name),
    slug: r.slug,
    city: displayNameOrNull(r.city),
    county: displayNameOrNull(r.county),
    hasSchedule: r.has_schedule === 1,
    summary: toSummary(r),
  }));
}

const SQL_STATE_TOTALS = `
  SELECT COUNT(*) AS districts, COALESCE(SUM(${HAS_SCHEDULE}), 0) AS with_schedule
    FROM districts d WHERE d.state = ? AND d.active = 1`;

export async function countDistrictsOfState(
  db: D1Database,
  stateCode: string,
): Promise<{ districts: number; withSchedule: number }> {
  const stmt = db.prepare(SQL_STATE_TOTALS).bind(stateCode);
  const row = await stmt.first<{ districts: number; with_schedule: number }>();
  return { districts: row?.districts ?? 0, withSchedule: row?.with_schedule ?? 0 };
}

// ---------------------------------------------------------------- bảng lương của một học khu

const SQL_PUBLISHED = `
  SELECT id, school_year, title, published_at
    FROM schedules
   WHERE district_id = ? AND status = 'published' AND schedule_type = 'teacher'
   ORDER BY school_year DESC, title, id`;

interface PublishedRow {
  id: number;
  school_year: string;
  title: string;
  published_at: string | null;
}

/** Bảng lương giáo viên đang published của học khu, năm mới nhất trước. */
export async function listPublishedSchedules(
  db: D1Database,
  districtId: number,
): Promise<PublishedSchedule[]> {
  const stmt = db.prepare(SQL_PUBLISHED).bind(districtId);
  const { results } = await stmt.all<PublishedRow>();
  return results.map((r) => ({
    id: r.id,
    schoolYear: r.school_year,
    title: r.title,
    publishedAt: r.published_at,
  }));
}

const SQL_HISTORY = `
  SELECT s.school_year,
         COUNT(DISTINCT s.id) AS schedules,
         MIN(c.amount_cents) AS min_cents,
         MAX(c.amount_cents) AS max_cents,
         SUM(s.pay_basis <> 'annual') AS non_annual
    FROM schedules s
    LEFT JOIN cells c ON c.schedule_id = s.id
   WHERE s.district_id = ? AND s.status = 'published' AND s.schedule_type = 'teacher'
   GROUP BY s.school_year
   ORDER BY s.school_year DESC`;

interface HistoryRow {
  school_year: string;
  schedules: number;
  min_cents: number | null;
  max_cents: number | null;
  non_annual: number | null;
}

/** Mỗi năm học có bảng published: số bảng, ô thấp nhất và cao nhất (khi mọi bảng tính theo năm). */
export async function listYearHistory(db: D1Database, districtId: number): Promise<YearHistory[]> {
  const stmt = db.prepare(SQL_HISTORY).bind(districtId);
  const { results } = await stmt.all<HistoryRow>();
  return results.map((r) => {
    const comparable = (r.non_annual ?? 0) === 0;
    return {
      schoolYear: r.school_year,
      schedules: r.schedules,
      minCents: comparable ? r.min_cents : null,
      maxCents: comparable ? r.max_cents : null,
    };
  });
}

/** Bảng `published` thuộc học khu nào; null nếu không tồn tại hoặc chưa published. */
export async function getPublishedScheduleDistrict(
  db: D1Database,
  scheduleId: number,
): Promise<number | null> {
  const sql = "SELECT district_id FROM schedules WHERE id = ? AND status = 'published'";
  const stmt = db.prepare(sql).bind(scheduleId);
  const row = await stmt.first<{ district_id: number }>();
  return row?.district_id ?? null;
}

// ---------------------------------------------------------------- tóm tắt và lân cận

const SQL_SUMMARY = `
  SELECT ${SUMMARY_COLUMNS}
    FROM districts d JOIN district_summary ds ON ${LATEST_SUMMARY}
   WHERE d.id = ?`;

export async function getLatestSummary(
  db: D1Database,
  districtId: number,
): Promise<Summary | null> {
  const stmt = db.prepare(SQL_SUMMARY).bind(districtId);
  const row = await stmt.first<SummaryColumns>();
  return row ? toSummary(row) : null;
}

const SQL_NEIGHBORS = `
  SELECT d.id, d.name, d.slug, st.slug AS state_slug, n.distance_km, ${SUMMARY_COLUMNS}
    FROM district_neighbors n
    JOIN districts d ON d.id = n.neighbor_id AND d.active = 1
    JOIN states st ON st.code = d.state
    JOIN district_summary ds ON ${LATEST_SUMMARY}
   WHERE n.district_id = ?
   ORDER BY (n.distance_km IS NULL), n.distance_km, d.name COLLATE NOCASE
   LIMIT ?`;

interface NeighborRow extends SummaryColumns {
  id: number;
  name: string;
  slug: string;
  state_slug: string;
  distance_km: number | null;
}

/** Học khu lân cận có số liệu so sánh, gần nhất trước. */
export async function listNeighbors(
  db: D1Database,
  districtId: number,
  limit: number,
): Promise<Neighbor[]> {
  const stmt = db.prepare(SQL_NEIGHBORS).bind(districtId, limit);
  const { results } = await stmt.all<NeighborRow>();
  const neighbors: Neighbor[] = [];
  for (const r of results) {
    const summary = toSummary(r);
    if (summary) {
      neighbors.push({
        id: r.id,
        name: displayName(r.name),
        slug: r.slug,
        stateSlug: r.state_slug,
        distanceKm: r.distance_km,
        summary,
      });
    }
  }
  return neighbors;
}

// ---------------------------------------------------------------- tìm kiếm

const MAX_SEARCH_TOKENS = 8;
const MAX_TOKEN_LENGTH = 40;

/**
 * Đổi chuỗi người dùng gõ thành truy vấn FTS5 an toàn: chỉ chữ và số lọt vào, mỗi từ khớp tiền tố,
 * mọi từ đều phải có (cách travienphi làm, REUSE_AUDIT.md §5). Trả null khi không còn từ nào.
 */
export function buildSearchQuery(input: string): string | null {
  const tokens = input.normalize("NFKC").match(/[\p{L}\p{N}]+/gu) ?? [];
  const kept = tokens.slice(0, MAX_SEARCH_TOKENS).map((t) => t.slice(0, MAX_TOKEN_LENGTH));
  if (kept.length === 0) {
    return null;
  }
  return kept.map((t) => `"${t}"*`).join(" ");
}

const SQL_SEARCH = `
  SELECT d.id, d.name, d.slug, d.city, d.county,
         st.code AS state_code, st.name AS state_name, st.slug AS state_slug,
         ${HAS_SCHEDULE} AS has_schedule
    FROM districts_fts
    JOIN districts d ON d.id = districts_fts.rowid
    JOIN states st ON st.code = d.state
   WHERE districts_fts MATCH ? AND d.active = 1
   ORDER BY bm25(districts_fts, 10.0, 4.0, 2.0), has_schedule DESC, d.enrollment DESC, d.name
   LIMIT ?`;

interface SearchRow {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  county: string | null;
  state_code: string;
  state_name: string;
  state_slug: string;
  has_schedule: number;
}

/** Tìm học khu theo tên, thành phố, quận. */
export async function searchDistricts(
  db: D1Database,
  input: string,
  limit: number,
): Promise<SearchHit[]> {
  const query = buildSearchQuery(input);
  if (query === null) {
    return [];
  }
  const stmt = db.prepare(SQL_SEARCH).bind(query, limit);
  const { results } = await stmt.all<SearchRow>();
  return results.map((r) => ({
    id: r.id,
    name: displayName(r.name),
    slug: r.slug,
    city: displayNameOrNull(r.city),
    county: displayNameOrNull(r.county),
    state: { code: r.state_code, name: r.state_name, slug: r.state_slug },
    hasSchedule: r.has_schedule === 1,
  }));
}

// ---------------------------------------------------------------- sitemap

/** Giới hạn của giao thức sitemap cho một tệp. Vượt số này thì cần sitemap index (Công đoạn 7). */
export const SITEMAP_LIMIT = 50_000;

const SQL_SITEMAP = `
  SELECT st.slug AS state_slug, d.slug AS district_slug, s.school_year,
         MAX(s.published_at) AS last_published
    FROM schedules s
    JOIN districts d ON d.id = s.district_id
    JOIN states st ON st.code = d.state
   WHERE s.status = 'published' AND s.schedule_type = 'teacher'
   GROUP BY d.id, s.school_year
   ORDER BY st.slug, d.slug, s.school_year DESC
   LIMIT ?`;

interface SitemapDbRow {
  state_slug: string;
  district_slug: string;
  school_year: string;
  last_published: string | null;
}

/** Mỗi (học khu, năm học) có bảng published; trong một học khu, năm mới nhất đứng trước. */
export async function listSitemapRows(db: D1Database): Promise<SitemapRow[]> {
  const stmt = db.prepare(SQL_SITEMAP).bind(SITEMAP_LIMIT);
  const { results } = await stmt.all<SitemapDbRow>();
  return results.map((r) => ({
    stateSlug: r.state_slug,
    districtSlug: r.district_slug,
    schoolYear: r.school_year,
    lastPublished: r.last_published,
  }));
}

// ---------------------------------------------------------------- xóa cache

/** Mã bang của các học khu, để biết phải xóa cache trang bang nào khi publish. */
export async function listStateCodesOfDistricts(db: D1Database, ids: number[]): Promise<string[]> {
  if (ids.length === 0) {
    return [];
  }
  const marks = ids.map(() => "?").join(", ");
  const sql = `SELECT DISTINCT state FROM districts WHERE id IN (${marks}) ORDER BY state`;
  const stmt = db.prepare(sql).bind(...ids);
  const { results } = await stmt.all<{ state: string }>();
  return results.map((r) => r.state);
}

/**
 * Kiểm tra tự động đã báo ở bảng của tệp nguồn của bang mà bảng vẫn publish "như nguồn" (D-028):
 * dòng review_queue đã đóng với resolution bắt đầu bằng "as reported".
 */
const SQL_AS_REPORTED = `
SELECT schedule_id, reason FROM review_queue
 WHERE schedule_id IN (SELECT value FROM json_each(?)) AND resolution LIKE 'as reported%'
 ORDER BY id`;

/** Mã kiểm tra (`monotonic_step`, `start_change`...) theo id bảng; bảng không bị báo thì vắng. */
export async function listAsReportedChecks(
  db: D1Database,
  scheduleIds: number[],
): Promise<Map<number, string[]>> {
  const out = new Map<number, string[]>();
  if (scheduleIds.length === 0) {
    return out;
  }
  const stmt = db.prepare(SQL_AS_REPORTED).bind(JSON.stringify(scheduleIds));
  const { results } = await stmt.all<{ schedule_id: number; reason: string }>();
  for (const row of results) {
    const code = /^\[([a-z_]+)\]/.exec(row.reason)?.[1];
    if (!code) {
      continue;
    }
    const codes = out.get(row.schedule_id) ?? [];
    if (!codes.includes(code)) {
      codes.push(code);
    }
    out.set(row.schedule_id, codes);
  }
  return out;
}
