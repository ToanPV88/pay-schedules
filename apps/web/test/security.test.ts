import { describe, expect, it } from "vitest";
import { CONTENT_SECURITY_POLICY, NAV_SCRIPT_HASH } from "../src/security";
import { NAV_SCRIPT_BODY } from "../src/views/layout";
import { request } from "./helpers";

async function sha256Base64(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  let binary = "";
  for (const byte of new Uint8Array(digest)) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

describe("header bảo mật", () => {
  it("hash của script menu trong CSP khớp với mã đang dùng", async () => {
    // Sửa NAV_SCRIPT_BODY mà quên cập nhật hash thì menu điện thoại sẽ bị CSP chặn.
    expect(NAV_SCRIPT_HASH).toBe(`sha256-${await sha256Base64(NAV_SCRIPT_BODY)}`);
  });

  it("mọi trang có CSP chặt, chống nhúng iframe, HSTS và Permissions-Policy", async () => {
    for (const path of ["/", "/about", "/khong-co-trang-nay", "/api/suggest?q=te", "/robots.txt"]) {
      const res = await request(path);
      expect(res.headers.get("Content-Security-Policy")).toBe(CONTENT_SECURITY_POLICY);
      expect(res.headers.get("X-Frame-Options")).toBe("DENY");
      expect(res.headers.get("Strict-Transport-Security")).toBe("max-age=31536000");
      expect(res.headers.get("Permissions-Policy")).toContain("geolocation=()");
      expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
    }
    expect(CONTENT_SECURITY_POLICY).toContain("frame-ancestors 'none'");
    expect(CONTENT_SECURITY_POLICY).not.toContain("'unsafe-eval'");
    expect(CONTENT_SECURITY_POLICY).not.toMatch(/script-src[^;]*'unsafe-inline'/);
  });
});
