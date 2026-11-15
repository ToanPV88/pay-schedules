import { describe, expect, it } from "vitest";
import { extremesOf } from "../src/views/tools";

describe("so sánh: cao nhất và thấp nhất", () => {
  it("chỉ đánh dấu khi có ít nhất hai số khác nhau", () => {
    expect(extremesOf([5_000_000, null, 6_000_000, 5_500_000])).toEqual({
      maxCents: 6_000_000,
      minCents: 5_000_000,
    });
    expect(extremesOf([5_000_000, null])).toBeNull();
    expect(extremesOf([5_000_000, 5_000_000])).toBeNull();
  });
});
