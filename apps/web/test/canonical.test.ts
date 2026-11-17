import { describe, expect, it } from "vitest";
import { canonicalRedirect } from "../src/canonical";
import { request } from "./helpers";

const ORIGIN = "https://payschedules.org";

describe("tên miền chính (D-113)", () => {
  it("www và workers.dev chuyển về tên miền chính, giữ đường dẫn và tham số", () => {
    expect(canonicalRedirect("https://www.payschedules.org/texas?sort=max", "GET", ORIGIN)).toBe(
      "https://payschedules.org/texas?sort=max",
    );
    expect(
      canonicalRedirect("https://pay-schedules.toankhmt.workers.dev/about", "HEAD", ORIGIN),
    ).toBe("https://payschedules.org/about");
  });

  it("không chuyển: đã đúng tên miền, bản xem trước, POST, lệnh nội bộ", () => {
    expect(canonicalRedirect("https://payschedules.org/about", "GET", ORIGIN)).toBeNull();
    expect(canonicalRedirect("https://pr-1-x.workers.dev/about", "GET", undefined)).toBeNull();
    expect(canonicalRedirect("https://www.payschedules.org/report", "POST", ORIGIN)).toBeNull();
    expect(canonicalRedirect("https://web.internal/internal/purge", "GET", ORIGIN)).toBeNull();
    expect(canonicalRedirect("https://x.workers.dev/healthz", "GET", ORIGIN)).toBeNull();
  });

  it("Worker trả 301 khi có CANONICAL_ORIGIN", async () => {
    const res = await request("/about?x=1", {}, { CANONICAL_ORIGIN: ORIGIN });
    expect(res.status).toBe(301);
    expect(res.headers.get("Location")).toBe("https://payschedules.org/about?x=1");
    const same = await request("/about", {}, { CANONICAL_ORIGIN: "https://example.invalid" });
    expect(same.status).toBe(200);
  });
});
