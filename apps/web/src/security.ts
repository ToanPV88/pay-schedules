/**
 * Header bảo mật cho mọi phản hồi của Worker (trang, API, tệp tải).
 *
 * CSP: chỉ chạy script của chính site (site.js), script menu nội tuyến theo hash, và Turnstile của
 * Cloudflare ở trang báo lỗi. Thuộc tính style="" được phép (thanh tỉ lệ, biểu đồ); thẻ <style> và
 * script nội tuyến khác thì không. JSON-LD (type="application/ld+json") là khối dữ liệu, CSP không chặn.
 * Khi gắn Cloudflare Web Analytics hoặc AdSense (Công đoạn 8) phải thêm nguồn của chúng vào đây.
 */

/** sha256 (base64) của NAV_SCRIPT_BODY trong views/layout.ts. Test kiểm tra giá trị này còn khớp. */
export const NAV_SCRIPT_HASH = "sha256-S7agJCkbCA9eBnby9jOW+MzEngAlMEbHJuXU3HWXxy8=";

const TURNSTILE_ORIGIN = "https://challenges.cloudflare.com";

export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  `script-src 'self' '${NAV_SCRIPT_HASH}' ${TURNSTILE_ORIGIN}`,
  "style-src 'self'",
  "style-src-attr 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src 'self' ${TURNSTILE_ORIGIN}`,
  `frame-src ${TURNSTILE_ORIGIN}`,
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

/** Header đặt cho mọi phản hồi động. HSTS bản đầy đủ (includeSubDomains, preload) chờ tên miền riêng. */
export const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy": CONTENT_SECURITY_POLICY,
  "Strict-Transport-Security": "max-age=31536000",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  // Không đặt Cross-Origin-Opener-Policy: với COOP, Lighthouse trong CI lỗi NO_NAVSTART (Chrome đổi
  // tiến trình khi điều hướng từ about:blank). Site không có cửa sổ bật lên hay đăng nhập nên COOP
  // gần như không thêm gì.
};
