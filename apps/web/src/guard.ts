/**
 * Chặn lấy dữ liệu hàng loạt và chống đội chi phí (DECISIONS.md D-108).
 *
 * Workers Cache phục vụ trang đã cache mà không gọi Worker, nên mọi request tới đây đều là lần trượt
 * cache: dựng trang, đọc D1, sinh file tải. Hai lớp chặn:
 *
 * 1. Giới hạn tần suất theo IP (Workers Rate Limiting binding; đếm riêng ở mỗi điểm Cloudflare):
 *    trang, API và file tải mỗi loại một ngưỡng. Vượt thì trả 429. Binding thiếu hoặc lỗi thì cho qua
 *    (fail-open), để sự cố của tính năng chặn không làm sập site.
 * 2. Chuẩn hoá tham số: tham số mà trang không dùng (vd. ?x=1, utm_*, fbclid) làm trượt cache và bắt
 *    D1 chạy lại. Gặp thì chuyển 301 về địa chỉ chỉ còn tham số hợp lệ; bản chuyển hướng được cache.
 */
import type { Context, Next } from "hono";
import { NO_STORE } from "./cache";
import type { AppEnv, Env, RateLimiter } from "./env";

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

/** true khi được đi tiếp. Không có IP (chạy local, test) hoặc không có binding thì cho qua. */
async function withinLimit(env: Env, kind: LimitKind, ip: string | undefined): Promise<boolean> {
  const limiter = limiterOf(env, kind);
  if (!limiter || !ip) {
    return true;
  }
  try {
    const { success } = await limiter.limit({ key: `${kind}:${ip}` });
    return success;
  } catch {
    return true;
  }
}

export async function guard(c: Context<AppEnv>, next: Next): Promise<Response | undefined> {
  const url = new URL(c.req.url);
  if (EXEMPT.test(url.pathname)) {
    await next();
    return;
  }
  const kind = limitKind(c.req.method, url.pathname);
  if (!(await withinLimit(c.env, kind, c.req.header("cf-connecting-ip")))) {
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
