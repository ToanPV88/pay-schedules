/** Binding và biến của Worker. Biến khai trong wrangler.jsonc; bí mật đặt bằng `wrangler secret put`. */
export type Env = {
  DB: D1Database;
  ASSETS: Fetcher;
  ENVIRONMENT: string;
  INDEXABLE: string;
  /** "true": chừa chỗ cho khung quảng cáo. Mã quảng cáo gắn ở Công đoạn 8. */
  AD_SLOTS?: string;
  /** Khóa công khai của Turnstile. Rỗng thì form báo lỗi tắt (DECISIONS.md D-104). */
  TURNSTILE_SITE_KEY?: string;
  /** Bí mật: khóa bí mật của Turnstile. */
  TURNSTILE_SECRET_KEY?: string;
  /** Bí mật: cho phép pipeline gọi POST /internal/purge (DECISIONS.md D-102). */
  PURGE_TOKEN?: string;
  /** Địa chỉ liên hệ hiện ở trang /contact. Rỗng cho tới khi chủ dự án chọn. */
  CONTACT_EMAIL?: string;
};

export type AppEnv = { Bindings: Env };

/** Tên tạm cho tới khi chủ dự án chọn tên site (DECISIONS.md D-002). */
export const SITE_NAME = "Pay Schedules";

export function isIndexable(env: Env): boolean {
  return env.INDEXABLE === "true";
}

export function isProduction(env: Env): boolean {
  return env.ENVIRONMENT === "production";
}

export function adSlotsEnabled(env: Env): boolean {
  return env.AD_SLOTS === "true";
}

/** Form báo lỗi chỉ bật khi có đủ hai khóa Turnstile. */
export function reportsEnabled(env: Env): boolean {
  return Boolean(env.TURNSTILE_SITE_KEY) && Boolean(env.TURNSTILE_SECRET_KEY);
}
