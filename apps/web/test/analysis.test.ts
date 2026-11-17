import { beforeEach, describe, expect, it } from "vitest";
import { standard } from "../../../packages/db/test/fixtures";
import { laneGrowth, scheduleGrowth } from "../src/analysis";
import { ordinal, ranking, rankOf, topPercent } from "../src/ranks";
import { page, reset, seed } from "./helpers";

describe("phân tích bảng lương", () => {
  beforeEach(async () => {
    await reset();
  });

  it("mỗi cột: bậc đầu, đỉnh, số bậc, số năm, phần trăm, bước tăng lớn nhất", async () => {
    const { a } = await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(a.scheduleId).toBeGreaterThan(0);
    expect(html).toContain("How pay moves up this schedule");
    expect(html).toContain(
      "In the BA column, pay rises from $50,000 at step 1 to $56,000 at step 5: 4 steps (4 years of experience), an increase of 12%.",
    );
    expect(html).toContain("The largest single raise is $1,500, from step 1 to step 2.");
    // Bảng các cột: MA+30 từ $56,000 lên $62,000.
    expect(html).toMatch(
      /<th scope="row">MA\+30<\/th><td>\$56,000<\/td><td>\$62,000<\/td><td>4<\/td><td>10\.7%<\/td>/,
    );
  });

  it("học khu lân cận ghi khoảng cách theo dặm", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    // 12,5 km ≈ 8 dặm.
    expect(html).toMatch(/Cañon Test[^<]*<\/a> <span class="muted distance">8 mi<\/span>/);
  });

  it("hạng trong bang và toàn quốc ở mức tối đa", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain(
      "The top of the scale ranks 1st of 2 Test State districts and 1st of 2 districts nationally, among districts on this site.",
    );
    const b = await page("/test-state/canon-test");
    // Cañon Test đang xem năm 2024-25 là năm mới nhất: hạng 2/2 ở mức tối đa.
    expect(b).toContain("ranks 2nd of 2 Test State districts");
  });

  it("hàm thuần: ô trống, cột một ô, bảng một bậc", () => {
    const schedule = {
      id: 1,
      districtId: 1,
      schoolYear: "2025-26",
      scheduleType: "teacher",
      title: "",
      contractDays: null,
      payBasis: "annual" as const,
      hoursPerYear: null,
      status: "published" as const,
      confidence: null,
      notes: null,
      source: { url: "https://x.invalid", fetchedAt: "2026-11-12T00:00:00Z", page: null },
      lanes: [
        { id: 1, position: 1, labelRaw: "BA", laneNormalized: "BA" },
        { id: 2, position: 2, labelRaw: "MA", laneNormalized: "MA" },
      ],
      steps: [1, 2, 3].map((n) => ({
        id: n,
        position: n,
        labelRaw: String(n),
        yearsExperience: null,
      })),
      cells: [
        [
          { amountCents: 4_000_000, note: null },
          { amountCents: null, note: "—" },
        ],
        [
          { amountCents: 4_100_000, note: null },
          { amountCents: 5_000_000, note: null },
        ],
        [
          { amountCents: 4_500_000, note: null },
          { amountCents: null, note: "—" },
        ],
      ],
      stipends: [],
    } as unknown as Parameters<typeof laneGrowth>[0];
    const ba = laneGrowth(schedule, 0);
    expect(ba?.stepMoves).toBe(2);
    expect(ba?.years).toBeNull();
    expect(ba?.largestRaise).toEqual({ fromStepIndex: 1, toStepIndex: 2, cents: 400_000 });
    const ma = laneGrowth(schedule, 1);
    expect(ma?.stepMoves).toBe(0);
    expect(ma?.largestRaise).toBeNull();
    expect(scheduleGrowth({ ...schedule, steps: schedule.steps.slice(0, 1) })).toEqual([]);
    expect(standard.lanes.length).toBe(4);
  });

  it("xếp hạng: bằng nhau cùng hạng, thứ tự, phần trăm", () => {
    const entry = (id: number, start: number | null) =>
      ({
        id,
        name: `D${id}`,
        slug: `d${id}`,
        city: null,
        enrollment: null,
        stateCode: "ZZ",
        stateSlug: "z",
        stateName: "Z",
        schoolYear: "2025-26",
        startBaCents: start,
        maStep10Cents: null,
        maxSalaryCents: null,
      }) as const;
    const rows = [entry(1, 500), entry(2, 700), entry(3, 700), entry(4, null), entry(5, 400)];
    expect(rankOf(rows, 1, "start")).toEqual({ rank: 3, total: 4 });
    expect(rankOf(rows, 3, "start")).toEqual({ rank: 1, total: 4 });
    expect(rankOf(rows, 4, "start")).toBeNull();
    expect(ranking(rows, "start").map((r) => [r.entry.id, r.rank])).toEqual([
      [2, 1],
      [3, 1],
      [1, 3],
      [5, 4],
    ]);
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 1001].map(ordinal)).toEqual([
      "1st",
      "2nd",
      "3rd",
      "4th",
      "11th",
      "12th",
      "13th",
      "21st",
      "22nd",
      "101st",
      "1,001st",
    ]);
    expect(topPercent({ rank: 7, total: 100 })).toBe("top 7%");
    expect(topPercent({ rank: 70, total: 100 })).toBeNull();
    expect(topPercent({ rank: 1, total: 10 })).toBeNull();
  });
});
