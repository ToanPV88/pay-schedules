/**
 * Cache ở edge (DECISIONS.md D-102). Worker bật Workers Cache trong wrangler.jsonc
 * (`"cache": { "enabled": true }`); trang được cache theo `Cache-Control` và gắn `Cache-Tag`, để
 * pipeline xóa có chọn lọc bằng `ctx.cache.purge({ tags })` khi publish.
 *
 * Theo tài liệu Cloudflare (tra 2026-11-12), Workers Cache chạy cả trên workers.dev và mỗi bản
 * xem trước có cache riêng, nên giả định của D-007 (Cache API không chạy trên *.workers.dev) không
 * áp cho cách này. Kiểm thực tế bằng header `Cf-Cache-Status` trên bản xem trước.
 */
import { listStateCodesOfDistricts } from "@pay-schedules/db";

/** Trang dữ liệu: trình duyệt giữ 5 phút, edge 1 ngày, phục vụ bản cũ tối đa 1 giờ khi làm mới. */
export const PAGE_CACHE = "public, max-age=300, s-maxage=86400, stale-while-revalidate=3600";
/** Trang tĩnh (about, methodology…) đổi theo bản deploy; mỗi phiên bản Worker có cache riêng. */
export const STATIC_PAGE_CACHE = "public, max-age=3600, s-maxage=604800";
export const NO_STORE = "no-store";

export const TAG_ALL = "pages";
export const TAG_HOME = "home";
export const TAG_SITEMAP = "sitemap";
export const TAG_COMPARE = "compare";

export function districtTag(id: number): string {
  return `district-${id}`;
}

export function stateTag(code: string): string {
  return `state-${code.toLowerCase()}`;
}

export function cacheTags(...tags: string[]): string {
  return [TAG_ALL, ...tags].join(",");
}

/** Kết quả của `ctx.cache.purge()`. Kiểu viết tay vì @cloudflare/workers-types có thể chưa có. */
export interface PurgeResult {
  success: boolean;
  errors?: { code: number; message: string }[];
}

export interface PurgeOptions {
  tags?: string[];
  pathPrefixes?: string[];
  purgeEverything?: boolean;
}

export interface CachePurger {
  purge(options: PurgeOptions): Promise<PurgeResult>;
}

/** `ctx.cache` khi runtime có Workers Cache; null khi không (môi trường test, tính năng tắt). */
export function cachePurger(ctx: unknown): CachePurger | null {
  const cache = (ctx as { cache?: Partial<CachePurger> } | undefined)?.cache;
  return cache && typeof cache.purge === "function" ? (cache as CachePurger) : null;
}

export const MAX_PURGE_DISTRICTS = 100;

/**
 * Thẻ cần xóa khi pipeline publish bảng của các học khu `districtIds`: trang của chính học khu
 * (mọi năm), trang bang, trang chủ, sitemap, trang so sánh, và học khu lân cận (bảng so sánh của
 * họ đọc số của học khu vừa đổi; PLAN Công đoạn 6).
 */
export async function purgeTags(db: D1Database, districtIds: number[]): Promise<string[]> {
  const ids = [...new Set(districtIds)];
  if (ids.length === 0) {
    return [];
  }
  const marks = ids.map(() => "?").join(", ");
  const sql = `SELECT DISTINCT district_id FROM district_neighbors WHERE neighbor_id IN (${marks})`;
  const { results } = await db
    .prepare(sql)
    .bind(...ids)
    .all<{ district_id: number }>();
  const affected = [...new Set([...ids, ...results.map((r) => r.district_id)])];
  const states = await listStateCodesOfDistricts(db, affected);
  const tags = new Set<string>([TAG_HOME, TAG_SITEMAP, TAG_COMPARE]);
  for (const id of affected) {
    tags.add(districtTag(id));
  }
  for (const code of states) {
    tags.add(stateTag(code));
  }
  return [...tags];
}

/** So sánh hằng thời gian cho token, để thời gian phản hồi không lộ token đúng tới đâu. */
export async function tokensMatch(given: string, expected: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(given)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const x = new Uint8Array(a);
  const y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i += 1) {
    diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  }
  return diff === 0;
}
