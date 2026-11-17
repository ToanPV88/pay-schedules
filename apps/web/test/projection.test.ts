import { beforeEach, describe, expect, it } from "vitest";
import { page, reset, seed } from "./helpers";

describe("máy tính: bậc kế tiếp và dự báo (D-119)", () => {
  let scheduleId = 0;
  beforeEach(async () => {
    await reset();
    scheduleId = (await seed()).a.scheduleId;
  });

  it("bậc đầu cột BA: bốn bậc kế tiếp, tổng 10 năm giữ lương đỉnh khi hết bậc", async () => {
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain(
      '<dd data-out="next">Step 2 $51,500 · Step 3 $53,000 · Step 4 $54,500 · Step 5 $56,000</dd>',
    );
    // 50,000 + 51,500 + 53,000 + 54,500 + 56,000 × 6
    expect(html).toContain('<span data-out="projection">$545,000 over 10 years</span>');
  });

  it("đang ở đỉnh: báo đỉnh; tổng là lương đỉnh × 10", async () => {
    const html = await page(`/test-state/test-valley-unified?s=${scheduleId}&lane=4&step=5`);
    expect(html).toContain("This is the top of the lane");
    expect(html).toContain("$620,000 over 10 years");
  });
});
