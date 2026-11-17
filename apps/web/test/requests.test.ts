import { countDistrictRequests, listTopRequested, REQUESTS_PER_DAY_CAP } from "@pay-schedules/db";
import { beforeEach, describe, expect, it } from "vitest";
import { limitKind } from "../src/guard";
import { db, page, request, reset, seed } from "./helpers";

const RIDGE = "/test-state/test-ridge";

describe("Request this district (D-121)", () => {
  let ids: Awaited<ReturnType<typeof seed>>;
  beforeEach(async () => {
    await reset();
    ids = await seed();
  });

  it("trang chưa có bảng có nút yêu cầu; trang có bảng thì không", async () => {
    const html = await page(RIDGE);
    expect(html).toContain(`<form method="post" action="${RIDGE}/request">`);
    expect(html).toContain("Request this district");
    expect(html).not.toContain("so far.");
    expect(await page("/test-state/test-valley-unified")).not.toContain("Request this district");
  });

  it("gửi yêu cầu: đếm theo ngày, trang cảm ơn noindex, không lưu gì về người gửi", async () => {
    const res = await request(`${RIDGE}/request`, { method: "POST" });
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    const html = await res.text();
    expect(html).toContain("Thanks, your request is recorded");
    expect(html).toContain('content="noindex');
    await request(`${RIDGE}/request`, { method: "POST" });
    expect(await countDistrictRequests(db, ids.c.districtId)).toBe(2);
    expect(await page(RIDGE)).toContain("Requested 2 times so far.");
    const cols = await db.prepare("PRAGMA table_info(district_requests)").all<{ name: string }>();
    expect(cols.results.map((c) => c.name)).toEqual(["district_id", "day", "requests"]);
    const top = await listTopRequested(db, 5);
    expect(top.map((t) => [t.id, t.requests])).toEqual([[ids.c.districtId, 2]]);
  });

  it("tối đa mỗi ngày; học khu đã có bảng thì chuyển về trang học khu; học khu lạ 404", async () => {
    for (let i = 0; i < REQUESTS_PER_DAY_CAP + 3; i++) {
      await request(`${RIDGE}/request`, { method: "POST" });
    }
    expect(await countDistrictRequests(db, ids.c.districtId)).toBe(REQUESTS_PER_DAY_CAP);
    const has = await request("/test-state/test-valley-unified/request", { method: "POST" });
    expect(has.status).toBe(303);
    expect(await countDistrictRequests(db, ids.a.districtId)).toBe(0);
    expect((await request("/test-state/nowhere/request", { method: "POST" })).status).toBe(404);
    expect(limitKind("POST", `${RIDGE}/request`)).toBe("form");
  });
});
