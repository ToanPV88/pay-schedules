import { describe, expect, it } from "vitest";
import { CONTENT_SECURITY_POLICY, GTM_SCRIPT_HASH, NAV_SCRIPT_HASH } from "../src/security";
import { GTM_SCRIPT_BODY, gtmSnippet, NAV_SCRIPT_BODY } from "../src/views/layout";
import { page, request } from "./helpers";

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
    expect(GTM_SCRIPT_HASH).toBe(`sha256-${await sha256Base64(GTM_SCRIPT_BODY)}`);
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

describe("Google Tag Manager (D-117)", () => {
  it("chỉ gắn khi có GTM_ID hợp lệ, CSP cho phép domain của Google", async () => {
    expect(String(gtmSnippet(undefined))).toBe("");
    expect(String(gtmSnippet("GTM-<x>"))).toBe("");
    const withGtm = await page("/about", { GTM_ID: "GTM-P9JG9HN2" });
    expect(withGtm).toContain(
      '<script async src="https://www.googletagmanager.com/gtm.js?id=GTM-P9JG9HN2"></script>',
    );
    expect(withGtm).toContain(`<script>${GTM_SCRIPT_BODY}</script>`);
    const without = await page("/about");
    expect(without).not.toContain("googletagmanager");
    const res = await request("/about");
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain("https://www.googletagmanager.com");
    expect(csp).toContain(GTM_SCRIPT_HASH);
    expect(csp).toContain("https://static.cloudflareinsights.com");
    expect(await page("/privacy")).toContain("Google Analytics opt-out browser add-on");
  });
});
