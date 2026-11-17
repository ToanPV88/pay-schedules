/**
 * Một tên miền chính (DECISIONS.md D-113). Production trả lời ở payschedules.org,
 * www.payschedules.org và pay-schedules.<tài khoản>.workers.dev; mọi địa chỉ khác tên miền chính
 * chuyển 301 về đó, giữ đường dẫn và tham số, để máy tìm kiếm chỉ thấy một bản của mỗi trang.
 * Bản xem trước không đặt CANONICAL_ORIGIN nên không chuyển.
 */

/** Lệnh nội bộ (service binding của trang duyệt) và kiểm tra sức khỏe không bị chuyển. */
const EXEMPT = /^\/(healthz|internal\/)/;

/** Địa chỉ đích khi request phải chuyển về tên miền chính; null khi không cần. */
export function canonicalRedirect(
  requestUrl: string,
  method: string,
  canonicalOrigin: string | undefined,
): string | null {
  if (!canonicalOrigin || (method !== "GET" && method !== "HEAD")) {
    return null;
  }
  const url = new URL(requestUrl);
  if (url.origin === canonicalOrigin || EXEMPT.test(url.pathname)) {
    return null;
  }
  return `${canonicalOrigin}${url.pathname}${url.search}`;
}
