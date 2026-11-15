import { beforeEach, describe, expect, it } from "vitest";
import { locationFromCf, milesBetween, resetNearbyCache } from "../src/nearby";
import { db, page, request, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
  resetNearbyCache();
});

interface NearbyBody {
  basis: string;
  label?: string;
  hits: { name: string; key: string; href: string; place: string; miles: number }[];
}

async function placeDistricts(aId: number, bId: number): Promise<void> {
  // Test Valley ở Austin, Cañon Test ở Dallas (toạ độ giả lập).
  await db
    .prepare(
      "UPDATE districts SET lat = CASE id WHEN ? THEN 30.27 WHEN ? THEN 32.78 END, lng = CASE id WHEN ? THEN -97.74 WHEN ? THEN -96.8 END WHERE id IN (?, ?)",
    )
    .bind(aId, bId, aId, bId, aId, bId)
    .run();
}

describe("học khu gần người xem", () => {
  it("vị trí chỉ lấy khi người xem ở Mỹ và có toạ độ", () => {
    expect(locationFromCf(undefined)).toBeNull();
    expect(locationFromCf({ country: "VN", latitude: "21.03", longitude: "105.85" })).toBeNull();
    expect(locationFromCf({ country: "US", region: "Texas" })).toBeNull();
    expect(
      locationFromCf({
        country: "US",
        city: "Austin",
        region: "Texas",
        latitude: "30.27",
        longitude: "-97.74",
      }),
    ).toEqual({ lat: 30.27, lng: -97.74, label: "Austin, Texas" });
  });

  it("khoảng cách theo dặm", () => {
    const miles = milesBetween({ lat: 30.27, lng: -97.74 }, { lat: 32.78, lng: -96.8 });
    expect(Math.round(miles)).toBeGreaterThan(175);
    expect(Math.round(miles)).toBeLessThan(190);
  });

  it("không biết vị trí (không có request.cf) thì không gợi ý", async () => {
    await seed();
    const body = (await (await request("/api/nearby")).json()) as NearbyBody;
    expect(body).toEqual({ basis: "none", hits: [] });
  });

  it("bản preview thử được bằng ?near=: học khu có bảng, gần nhất trước", async () => {
    const { a, b } = await seed();
    await placeDistricts(a.districtId, b.districtId);
    const res = await request("/api/nearby?near=30.3,-97.7", {}, { ENVIRONMENT: "preview" });
    expect(res.headers.get("Cache-Control")).toBe("private, max-age=600");
    const body = (await res.json()) as NearbyBody;
    expect(body.basis).toBe("location");
    expect(body.hits.map((h) => h.key)).toEqual([
      "test-state/test-valley-unified",
      "test-state/canon-test",
    ]);
    expect(body.hits[0]?.miles).toBeLessThan(10);
    expect(body.hits[0]?.place).toBe("Testville, ZZ");
    const byState = (await (
      await request("/api/nearby?near=ZZ", {}, { ENVIRONMENT: "preview" })
    ).json()) as NearbyBody;
    expect(byState.label).toBe("Test State");
    expect(byState.hits.length).toBe(2);
  });

  it("bản production bỏ qua ?near=", async () => {
    const { a, b } = await seed();
    await placeDistricts(a.districtId, b.districtId);
    const res = await request("/api/nearby?near=ZZ", {}, { ENVIRONMENT: "production" });
    expect(((await res.json()) as NearbyBody).basis).toBe("none");
  });

  it("/calculator và /compare có khối để site.js thay bằng học khu gần", async () => {
    const { a } = await seed();
    await db
      .prepare("UPDATE districts SET enrollment = 1000 WHERE id = ?")
      .bind(a.districtId)
      .run();
    expect(await page("/calculator")).toContain('data-nearby="/calculator?d={key}"');
    expect(await page("/compare")).toContain('data-nearby="/compare?d={key}"');
  });
});
