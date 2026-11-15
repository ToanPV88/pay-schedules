import { beforeEach, describe, expect, it } from "vitest";
import { page, reset, seed } from "./helpers";

beforeEach(async () => {
  await reset();
});

describe("thẻ chia sẻ mạng xã hội", () => {
  it("trang học khu có Open Graph theo tiêu đề, mô tả và địa chỉ chuẩn của trang", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain('<meta property="og:type" content="website">');
    expect(html).toContain(
      '<meta property="og:url" content="https://example.invalid/test-state/test-valley-unified">',
    );
    expect(html).toContain(
      '<meta property="og:image" content="https://example.invalid/og-image.png">',
    );
    expect(html).toMatch(
      /<meta property="og:title" content="Test Valley Unified School District, ZZ/,
    );
    expect(html).toMatch(
      /<meta property="og:description" content="Test Valley Unified School District \(/,
    );
    expect(html).toContain('<meta name="twitter:card" content="summary_large_image">');
    expect(html).toContain('<meta name="theme-color" content="#9f224e">');
    expect(html).toContain('<link rel="manifest" href="/site.webmanifest">');
  });

  it("trang không có địa chỉ chuẩn thì không có og:url", async () => {
    const html = await page("/search?q=x");
    expect(html).not.toContain('property="og:url"');
    expect(html).toContain('<meta property="og:image"');
  });
});
