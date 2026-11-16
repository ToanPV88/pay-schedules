/**
 * Khóa tạm theo IP khi đăng nhập trang duyệt sai nhiều lần (DECISIONS.md D-110).
 *
 * Hai lớp, như giới hạn tần suất của web (D-108): đếm trong bộ nhớ isolate (chính xác trong từng
 * isolate) và Workers Rate Limiting binding (rộng tay, chỉ là lớp phụ). Chỉ lần sai mới bị đếm, nên
 * người nhập đúng mật khẩu không bao giờ bị binding chặn. Không ghi gì vào D1: kẻ dò mật khẩu không
 * làm tốn lượt ghi.
 */

/** Sai quá số lần này trong cửa sổ thì khóa. */
export const MAX_FAILURES = 10;
/** Độ dài cửa sổ đếm và thời gian khóa. */
export const LOCK_MS = 15 * 60_000;
/** Số IP giữ trong bộ nhớ; quá thì bỏ mục đã hết hạn, vẫn quá thì xóa hết. */
const MAX_KEYS = 2_000;

interface Failures {
  first: number;
  count: number;
  lockedUntil: number;
}

const failures = new Map<string, Failures>();

export interface RateLimiter {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

/** Thời điểm hết khóa (ms) nếu IP đang bị khóa; 0 nếu không. */
export function lockedUntil(ip: string, now = Date.now()): number {
  const entry = failures.get(ip);
  return entry && entry.lockedUntil > now ? entry.lockedUntil : 0;
}

/** Ghi một lần sai; trả true khi lần này làm IP bị khóa (hoặc IP đã bị khóa). */
export function recordFailure(ip: string, now = Date.now()): boolean {
  let entry = failures.get(ip);
  if (!entry || (now - entry.first >= LOCK_MS && entry.lockedUntil <= now)) {
    if (!entry && failures.size >= MAX_KEYS) {
      for (const [key, e] of failures) {
        if (now - e.first >= LOCK_MS && e.lockedUntil <= now) {
          failures.delete(key);
        }
      }
      if (failures.size >= MAX_KEYS) {
        failures.clear();
      }
    }
    entry = { first: now, count: 0, lockedUntil: 0 };
    failures.set(ip, entry);
  }
  entry.count += 1;
  if (entry.count >= MAX_FAILURES && entry.lockedUntil <= now) {
    entry.lockedUntil = now + LOCK_MS;
  }
  return entry.lockedUntil > now;
}

/** Đăng nhập đúng thì xóa bộ đếm của IP. */
export function clearFailures(ip: string): void {
  failures.delete(ip);
}

export function resetLockout(): void {
  failures.clear();
}

/** Hỏi binding cho một lần sai; binding thiếu hoặc lỗi thì coi như chưa vượt. */
export async function bindingBlocks(
  limiter: RateLimiter | undefined,
  ip: string,
): Promise<boolean> {
  if (!limiter) {
    return false;
  }
  try {
    const { success } = await limiter.limit({ key: `auth:${ip}` });
    return !success;
  } catch {
    return false;
  }
}
