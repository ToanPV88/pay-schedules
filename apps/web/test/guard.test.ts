import { beforeEach, describe, expect, it } from "vitest";
import {
  allowedParams,
  canonicalSearch,
  LIMITS,
  limitKind,
  localAllow,
  resetLocalLimits,
} from "../src/guard";
import { request } from "./helpers";

function limiter(success: boolean) {
  const keys: string[] = [];
  return {
    keys,
    binding: {
      limit: async ({ key }: { key: string }) => {
        keys.push(key);
        return { success };
      },
    },
  };
}

describe("chuẩn hoá tham số URL", () => {
  it("giữ tham số trang dùng, bỏ tham số lạ", () => {
    expect(canonicalSearch(new URL("https://x.test/texas?sort=max&dir=desc"))).toBeNull();
    expect(canonicalSearch(new URL("https://x.test/texas?sort=max&utm_source=fb"))).toBe(
      "/texas?sort=max",
    );
    expect(canonicalSearch(new URL("https://x.test/about?x=1"))).toBe("/about");
    expect(canonicalSearch(new URL("https://x.test/texas/austin-isd?s=1&lane=2&fbclid=a"))).toBe(
      "/texas/austin-isd?s=1&lane=2",
    );
    expect(allowedParams("/api/suggest")).toEqual(["q"]);
    expect(allowedParams("/calculator")).toContain("d");
  });

  it("tham số lạ chuyển 301 về địa chỉ sạch, bản chuyển hướng được cache", async () => {
    const res = await request("/about?x=123", { redirect: "manual" });
    expect(res.status).toBe(301);
    expect(res.headers.get("Location")).toBe("/about");
    expect(res.headers.get("Cache-Control")).toContain("s-maxage");
    expect(res.headers.get("Content-Security-Policy")).not.toBeNull();
  });
});

describe("giới hạn tần suất", () => {
  beforeEach(() => resetLocalLimits());

  it("cửa sổ một phút trong isolate: quá ngưỡng thì chặn, sang phút sau thì mở lại", () => {
    const start = 1_000_000;
    for (let i = 0; i < 3; i++) {
      expect(localAllow("api:198.51.100.1", 3, start + i)).toBe(true);
    }
    expect(localAllow("api:198.51.100.1", 3, start + 10)).toBe(false);
    expect(localAllow("api:198.51.100.2", 3, start + 10)).toBe(true);
    expect(localAllow("api:198.51.100.1", 3, start + 60_000)).toBe(true);
  });

  it("vượt ngưỡng file tải trong isolate thì 429 dù binding cho qua", async () => {
    const ok = limiter(true);
    const init = { headers: { "cf-connecting-ip": "198.51.100.9" } };
    for (let i = 0; i < LIMITS.download; i++) {
      localAllow("download:198.51.100.9", LIMITS.download);
    }
    const res = await request("/schedules/999999.csv", init, { DOWNLOAD_LIMITER: ok.binding });
    expect(res.status).toBe(429);
    expect(ok.keys).toEqual([]);
  });

  it("phân loại trang, API, file tải", () => {
    expect(limitKind("GET", "/texas")).toBe("page");
    expect(limitKind("GET", "/api/suggest")).toBe("api");
    expect(limitKind("POST", "/report")).toBe("form");
    expect(limitKind("POST", "/internal/purge")).toBe("api");
    expect(limitKind("GET", "/schedules/12.xlsx")).toBe("download");
  });

  it("vượt ngưỡng thì 429 kèm Retry-After, khóa theo loại và IP", async () => {
    const blocked = limiter(false);
    const res = await request(
      "/about",
      { headers: { "cf-connecting-ip": "203.0.113.7" } },
      { PAGE_LIMITER: blocked.binding },
    );
    expect(res.status).toBe(429);
    expect(res.headers.get("Retry-After")).toBe("60");
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(blocked.keys).toEqual(["page:203.0.113.7"]);
  });

  it("trong ngưỡng, không có IP hoặc binding lỗi thì cho qua", async () => {
    const ok = limiter(true);
    const pass = await request(
      "/about",
      { headers: { "cf-connecting-ip": "203.0.113.8" } },
      { PAGE_LIMITER: ok.binding },
    );
    expect(pass.status).toBe(200);
    const noIp = await request("/about", {}, { PAGE_LIMITER: limiter(false).binding });
    expect(noIp.status).toBe(200);
    const broken = {
      limit: async () => {
        throw new Error("binding down");
      },
    };
    const failOpen = await request(
      "/about",
      { headers: { "cf-connecting-ip": "203.0.113.9" } },
      { PAGE_LIMITER: broken },
    );
    expect(failOpen.status).toBe(200);
  });

  it("lệnh nội bộ và kiểm tra sức khỏe không bị giới hạn", async () => {
    const blocked = limiter(false);
    const res = await request(
      "/healthz",
      { headers: { "cf-connecting-ip": "203.0.113.7" } },
      { PAGE_LIMITER: blocked.binding },
    );
    expect(res.status).not.toBe(429);
    expect(blocked.keys).toEqual([]);
  });
});
