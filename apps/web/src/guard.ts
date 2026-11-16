/**
 * Chặn lấy dữ liệu hàng loạt và chống đội chi phí (DECISIONS.md D-108).
 *
 * Workers Cache phục vụ trang đã cache mà không gọi Worker, nên mọi request tới đây đều là lần trượt
 * cache: dựng trang, đọc D1, sinh file tải. Hai lớp chặn:
 *
 * 1. Giới hạn tần suất theo IP: trang, API và file tải mỗi loại một ngưỡng; vượt thì trả 429. Đếm hai
 *    nơi: cửa sổ một phút trong bộ nhớ của isolate (chính xác trong từng isolate, nên một IP được tối
 *    đa ngưỡng × số isolate phục vụ nó), và Workers Rate Limiting binding. Cả hai chỉ là trần thô: đo
 *    trên workers.dev ngày 2026-11-16, binding không chặn lượt nào trong hơn 900 lượt/2 phút, và 40
 *    lượt tuần tự rơi vào 8 isolate (D-108). Binding thiếu hoặc lỗi thì cho qua.
 * 2. Chuẩn hoá tham số: tham số mà trang không dùng (vd. ?x=1, utm_*, fbclid) làm trượt cache và bắt
 *    D1 chạy lại. Gặp thì chuyển 301 về địa chỉ chỉ còn tham số hợp lệ; bản chuyển hướng được cache.
 */
import type { Context, Next } from "hono";
import { NO_STORE } from "./cache";
import { type AppEnv, type Env, isProduction, type RateLimiter } from "./env";

/** Tham số mỗi đường dẫn dùng. So theo thứ tự, mẫu đầu tiên khớp thắng. */
const ALLOWED_PARAMS: [RegExp, readonly string[]][] = [
  [/^\/search$/, ["q"]],
  [/^\/recently-updated$/, ["page"]],
  [/^\/calculator$/, ["d", "q", "s", "lane", "step", "near"]],
  [/^\/compare$/, ["d", "q", "lane", "step", "near"]],
  [/^\/report$/, ["d", "s"]],
  [/^\/api\/suggest$/, ["q"]],
  [/^\/api\/nearby$/, ["near"]],
  [/^\/demo$/, ["s", "lane", "step"]],
  [/^\/[^/]+\/[^/]+(\/[^/]+)?$/, ["s", "lane", "step"]],
  [/^\/[^/]+$/, ["sort", "dir", "p"]],
];

/** Không chuẩn hoá và không giới hạn: kiểm tra sức khỏe và lệnh nội bộ có xác thực của pipeline. */
const EXEMPT = /^\/(healthz|internal\/)/;

export function allowedParams(pathname: string): readonly string[] {
  for (const [pattern, params] of ALLOWED_PARAMS) {
    if (pattern.test(pathname)) {
      return params;
    }
  }
  return [];
}

/** Địa chỉ chuẩn khi URL có tham số lạ; null khi URL đã sạch. */
export function canonicalSearch(url: URL): string | null {
  if (url.search === "") {
    return null;
  }
  const allowed = allowedParams(url.pathname);
  const kept = new URLSearchParams();
  let dropped = false;
  for (const [key, value] of url.searchParams) {
    if (allowed.includes(key) && !kept.has(key)) {
      kept.append(key, value);
    } else {
      dropped = true;
    }
  }
  if (!dropped) {
    return null;
  }
  const search = kept.toString();
  return `${url.pathname}${search ? `?${search}` : ""}${url.hash}`;
}

export type LimitKind = "page" | "api" | "download";

export function limitKind(method: string, pathname: string): LimitKind {
  if (pathname.startsWith("/schedules/")) {
    return "download";
  }
  if (pathname.startsWith("/api/") || method === "POST") {
    return "api";
  }
  return "page";
}

function limiterOf(env: Env, kind: LimitKind): RateLimiter | undefined {
  if (kind === "download") {
    return env.DOWNLOAD_LIMITER;
  }
  return kind === "api" ? env.API_LIMITER : env.PAGE_LIMITER;
}

/** Ngưỡng mỗi phút của mỗi loại; trùng với `ratelimits` trong wrangler.jsonc. */
export const LIMITS: Record<LimitKind, number> = { page: 120, api: 60, download: 15 };
const WINDOW_MS = 60_000;
/** Số khóa (loại + IP) giữ trong bộ nhớ của isolate; quá thì bỏ các cửa sổ đã hết hạn. */
const MAX_KEYS = 5_000;
const windows = new Map<string, { start: number; count: number }>();

/** Cửa sổ cố định một phút trong bộ nhớ của isolate. */
export function localAllow(key: string, limit: number, now = Date.now()): boolean {
  let window = windows.get(key);
  if (!window || now - window.start >= WINDOW_MS) {
    if (!window && windows.size >= MAX_KEYS) {
      for (const [k, w] of windows) {
        if (now - w.start >= WINDOW_MS) {
          windows.delete(k);
        }
      }
      if (windows.size >= MAX_KEYS) {
        windows.clear();
      }
    }
    window = { start: now, count: 0 };
    windows.set(key, window);
  }
  window.count += 1;
  return window.count <= limit;
}

export function resetLocalLimits(): void {
  windows.clear();
}

/** Mã ngẫu nhiên của isolate, tạo ở request đầu (Workers không cho sinh số ngẫu nhiên ở global scope). */
let isolateId = "";
function isolateTag(): string {
  if (isolateId === "") {
    isolateId = crypto.randomUUID().slice(0, 8);
  }
  return isolateId;
}

export type LimitResult = "ok" | "blocked" | "local-blocked" | "no-ip" | "no-binding" | "error";

/** Không có IP (chạy local, test) thì cho qua; không có binding hoặc binding lỗi thì chỉ đếm local. */
async function checkLimit(env: Env, kind: LimitKind, ip: string | undefined): Promise<LimitResult> {
  if (!ip) {
    return "no-ip";
  }
  const key = `${kind}:${ip}`;
  if (!localAllow(key, LIMITS[kind])) {
    return "local-blocked";
  }
  const limiter = limiterOf(env, kind);
  if (!limiter) {
    return "no-binding";
  }
  try {
    const { success } = await limiter.limit({ key });
    return success ? "ok" : "blocked";
  } catch (err) {
    console.warn(`rate limit ${kind}: ${err instanceof Error ? err.message : String(err)}`);
    return "error";
  }
}

export async function guard(c: Context<AppEnv>, next: Next): Promise<Response | undefined> {
  const url = new URL(c.req.url);
  if (EXEMPT.test(url.pathname)) {
    await next();
    return;
  }
  const kind = limitKind(c.req.method, url.pathname);
  const result = await checkLimit(c.env, kind, c.req.header("cf-connecting-ip"));
  if (!isProduction(c.env)) {
    // Chỉ bản xem trước: để kiểm binding có chạy thật không.
    const ip = c.req.header("cf-connecting-ip") ?? "";
    const count = windows.get(`${kind}:${ip}`)?.count ?? 0;
    c.header("X-Rate-Limit", `${kind} ${result} n=${count} isolate=${isolateTag()}`);
  }
  if (result === "blocked" || result === "local-blocked") {
    c.header("Retry-After", "60");
    c.header("Cache-Control", NO_STORE);
    return c.text("Too many requests. Please wait a minute and try again.", 429);
  }
  if (c.req.method === "GET" || c.req.method === "HEAD") {
    const target = canonicalSearch(url);
    if (target !== null) {
      c.header("Cache-Control", "public, max-age=3600, s-maxage=86400");
      return c.redirect(target, 301);
    }
  }
  await next();
}
