/** Nghiệm thu Công đoạn 6: các trang render đúng trên dữ liệu GIẢ LẬP. */

import type { Schedule } from "@pay-schedules/db";
import { beforeEach, describe, expect, it } from "vitest";
import { standard } from "../../../packages/db/test/fixtures";
import { formatCents } from "../src/format";
import { resetMenuCache } from "../src/index";
import { type DistrictPageData, stateComparison } from "../src/views/district";
import { db, page, request, reset, seed, tableRows, withoutScripts } from "./helpers";

beforeEach(async () => {
  await reset();
});

describe("tắt JavaScript vẫn đọc được toàn bộ bảng lương (nghiệm thu)", () => {
  it("mọi ô của bảng nằm trong HTML server gửi, đúng hàng và cột", async () => {
    const { a } = await seed();
    const html = withoutScripts(await page("/test-state/test-valley-unified"));
    const rows = tableRows(html, `schedule-${a.scheduleId}`);
    expect(rows).toHaveLength(standard.steps.length);
    for (const [i, row] of rows.entries()) {
      const expected = [
        standard.steps[i]?.labelRaw,
        ...(standard.cells[i] ?? []).map((c) => formatCents(c as number)),
      ];
      expect(row, `bậc ${i + 1}`).toEqual(expected);
    }
    for (const lane of standard.lanes) {
      expect(html).toContain(`<th scope="col">${lane.labelRaw}</th>`);
    }
    // Bảng không bị ẩn chờ JavaScript.
    expect(html).not.toMatch(/<table[^>]*\shidden/);
    expect(html).not.toContain("<noscript");
  });

  it("ô trống hiện dấu gạch và ghi chú nguyên văn", async () => {
    const { b } = await seed();
    const html = withoutScripts(await page("/test-state/canon-test"));
    const rows = tableRows(html, `schedule-${b.scheduleId}`);
    // Ô trống chỉ hiện dấu gạch; ghi chú riêng nằm ở title và chữ cho trình đọc màn hình,
    // không còn danh sách chú thích đánh số dưới bảng.
    expect(rows[0]?.[4]).toBe("—");
    expect(html).toContain('title="No placement on this step for Column D"');
    expect(html).not.toContain('<ol class="notes">');
    expect(html).toContain("A dash means the document shows no amount for that cell.");
  });

  it("máy tính chạy không cần JavaScript: form GET, server tính", async () => {
    const { a } = await seed();
    const html = await page(`/test-state/test-valley-unified?s=${a.scheduleId}&lane=3&step=5`);
    // MA, bậc 5 của bảng chuẩn: 60.000 USD; 185 ngày hợp đồng; bậc cuối.
    expect(html).toContain('<dd data-out="amount">$60,000 per year</dd>');
    expect(html).toContain('<dd data-out="per-day">$324.32 (185 contract days)</dd>');
    expect(html).toContain('<dd data-out="raise">Top step of this schedule</dd>');
    expect(html).toContain('<dd data-out="per-month">$5,000 (12 equal checks)</dd>');
    expect(html).toContain('<dd data-out="top">This is the top of the lane</dd>');
    expect(html).toContain('<form class="calc" method="get"');
  });

  it("máy tính hỏi theo số năm kinh nghiệm khi mọi bậc đều ghi số năm", async () => {
    const { a } = await seed();
    const html = await page(`/test-state/test-valley-unified?s=${a.scheduleId}&lane=1&step=1`);
    // Bảng chuẩn: bậc "1" là 0 năm kinh nghiệm, ... bậc "5" là 4 năm.
    expect(html).toContain(`<label for="step-${a.scheduleId}">Years of experience</label>`);
    expect(html).toContain('<option value="1" selected>0 years (Step 1)</option>');
    expect(html).toContain('<option value="2">1 year (Step 2)</option>');
    // BA, bậc 1: 50.000 USD; đỉnh cột BA là 56.000 USD ở bậc 5.
    expect(html).toContain('<dd data-out="top">$56,000 at Step 5 (4 more steps)</dd>');
    expect(html).toContain('<dd data-out="raise">+$1,500 at the next step</dd>');
  });
});

describe("sitemap chỉ gồm trang có bảng published (nghiệm thu)", () => {
  it("không có học khu chỉ có bảng draft, không có trang bang hay trang công cụ", async () => {
    await seed();
    const res = await request("/sitemap.xml");
    expect(res.headers.get("content-type")).toContain("application/xml");
    const xml = await res.text();
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    expect(locs).toEqual([
      "https://example.invalid/test-state/canon-test",
      "https://example.invalid/test-state/test-valley-unified",
    ]);
  });

  it("năm cũ có URL riêng; bảng superseded không có", async () => {
    const { a } = await seed();
    await db
      .prepare(
        `INSERT INTO schedules (district_id, school_year, title, contract_days, source_document_id,
                                source_page, status, published_at)
         SELECT district_id, '2024-25', title, contract_days, source_document_id, 2, 'published',
                '2025-08-02T00:00:00Z' FROM schedules WHERE id = ?`,
      )
      .bind(a.scheduleId)
      .run();
    const xml = await (await request("/sitemap.xml")).text();
    expect(xml).toContain("<loc>https://example.invalid/test-state/test-valley-unified</loc>");
    expect(xml).toContain(
      "<loc>https://example.invalid/test-state/test-valley-unified/2024-25</loc>",
    );
    expect(xml).not.toContain("test-ridge");
  });

  it("CSDL trống vẫn trả sitemap hợp lệ", async () => {
    const xml = await (await request("/sitemap.xml")).text();
    expect(xml).toContain('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');
    expect(xml).not.toContain("<url>");
  });
});

describe("trang học khu", () => {
  it("đủ các phần theo thứ tự của PLAN", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    const order = [
      "<h1>Test Valley Unified School District Teacher Salary Schedule 2025–26</h1>",
      "Lowest salary on schedule",
      '<table class="schedule"',
      ">Salary calculator</h3>",
      '<h2 id="nearby-heading">Nearby districts</h2>',
      '<h2 id="notes-heading">Stipends and notes</h2>',
      '<h2 id="source-heading">Source</h2>',
      '<h2 id="years-heading">Other school years</h2>',
      '<h2 id="faq-heading">Questions people ask</h2>',
    ];
    let last = -1;
    for (const marker of order) {
      const at = html.indexOf(marker);
      expect(at, marker).toBeGreaterThan(last);
      last = at;
    }
    expect(html).toContain("https://test-valley.example.invalid/hr/salary-2025-26.pdf");
    expect(html).toContain("Page 3");
    expect(html).toContain('<a href="/test-state/canon-test">Cañon Test School District</a>');
  });

  it("học khu chưa có bảng published: 'schedule not found' và noindex", async () => {
    await seed();
    const html = await page("/test-state/test-ridge", { INDEXABLE: "true" });
    expect(html).toContain("Schedule not found.");
    expect(html).toContain('<meta name="robots" content="noindex, follow">');
    expect(html).not.toContain('<table class="schedule"');
  });

  it("khi mở index: trang có bảng và có so sánh lân cận thì cho index", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified", { INDEXABLE: "true" });
    expect(html).toContain('<meta name="robots" content="index, follow">');
    const withQuery = await page("/test-state/test-valley-unified?step=2", { INDEXABLE: "true" });
    expect(withQuery).toContain('<meta name="robots" content="noindex, follow">');
  });

  it("URL năm mới nhất chuyển về URL chính; năm không có thì 404", async () => {
    await seed();
    const latest = await request("/test-state/test-valley-unified/2025-26", {
      redirect: "manual",
    });
    expect(latest.status).toBe(301);
    expect(latest.headers.get("location")).toBe("/test-state/test-valley-unified");
    expect((await request("/test-state/test-valley-unified/2019-20")).status).toBe(404);
    expect((await request("/test-state/test-valley-unified/abc")).status).toBe(404);
    expect((await request("/test-state/khong-co")).status).toBe(404);
  });

  it("có header cache và thẻ để xóa cache khi publish", async () => {
    const { a } = await seed();
    const res = await request("/test-state/test-valley-unified");
    expect(res.headers.get("cache-control")).toContain("s-maxage=");
    expect(res.headers.get("cache-tag")).toBe(`pages,district-${a.districtId},state-zz`);
  });

  it("dữ liệu được escape: không chèn được HTML hay javascript:", async () => {
    const { a, c } = await seed();
    const update = "UPDATE districts SET name = ?, website = ? WHERE id = ?";
    const name = '<script>alert("x")</script> Test';
    await db.prepare(update).bind(name, "javascript:alert(1)", a.districtId).run();
    await db.prepare(update).bind(name, "javascript:alert(1)", c.districtId).run();
    for (const path of ["/test-state/test-valley-unified", "/test-state/test-ridge"]) {
      const html = await page(path);
      expect(html, path).not.toContain('<script>alert("x")</script>');
      expect(html, path).toContain("&lt;script&gt;");
      expect(html, path).not.toContain("javascript:alert");
    }
    const site = "https://ridge.example.invalid/";
    await db.prepare(update).bind("Test Ridge", site, c.districtId).run();
    expect(await page("/test-state/test-ridge")).toContain(
      '<a href="https://ridge.example.invalid/" rel="nofollow noopener">',
    );
  });
});

describe("bảng của tệp nguồn của bang (D-028)", () => {
  it("bảng publish như nguồn: ghi rõ kiểm tra đã báo, không còn câu 'passed'", async () => {
    const { a } = await seed();
    await db
      .prepare(
        `INSERT INTO review_queue (schedule_id, reason, created_at, resolved_at, resolution)
         VALUES (?, '[monotonic_step] Lương giảm khi tăng bậc', '2026-11-13T00:00:00Z',
                 '2026-11-13T00:00:00Z', 'as reported: published from the state file')`,
      )
      .bind(a.scheduleId)
      .run();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain("Shown as the source published it");
    expect(html).toContain("pay goes down from one step to the next");
    expect(html).not.toContain("Passed automated checks");
  });

  it("tệp .exe của bang: link tới trang dữ liệu chính thức, không tới tệp", async () => {
    const { a } = await seed();
    const exe = "https://www3.cde.ca.gov/ds-downloads/fd/cs/j902425.exe";
    await db
      .prepare(
        "UPDATE source_documents SET url = ? WHERE id = (SELECT source_document_id FROM schedules WHERE id = ?)",
      )
      .bind(exe, a.scheduleId)
      .run();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain('href="https://www.cde.ca.gov/ds/fd/cs/"');
    expect(html).toContain("Form J-90 data (j902425.exe)");
    expect(html).not.toContain(`href="${exe}"`);
    expect(html).toContain("Passed automated checks");
  });
});

describe("trang bang, tìm kiếm, so sánh, máy tính", () => {
  it("trang bang liệt kê học khu và sắp xếp phía server", async () => {
    await seed();
    const html = await page("/test-state");
    expect(html).toContain("2 of 3 districts in Test State");
    expect(html).toContain("No schedule yet");
    const sorted = await page("/test-state?sort=max&dir=desc");
    const valley = sorted.indexOf("Test Valley Unified School District</a>");
    const canon = sorted.indexOf("Cañon Test School District</a>");
    expect(valley).toBeGreaterThan(0);
    expect(canon).toBeGreaterThan(valley);
    expect((await request("/khong-co-bang")).status).toBe(404);
  });

  it("trang bang có tóm tắt lương của bang, ô lọc và học khu mới cập nhật", async () => {
    await seed();
    const html = await page("/test-state");
    expect(html).toContain("Teacher pay in Test State");
    expect(html).toContain("Recently updated in Test State");
    // ô lọc ẩn khi không có JavaScript
    expect(html).toMatch(/<div class="table-filter" hidden>/);
    expect(html).toContain('data-filter-table="districts-table"');
    expect(html).toContain('id="districts-table"');
  });

  it("tìm kiếm theo tên, không dấu; escape chuỗi người dùng gõ", async () => {
    await seed();
    expect(await page("/search?q=canon")).toContain('href="/test-state/canon-test"');
    const html = await page("/search?q=%3Cb%3Ex");
    expect(html).toContain("&lt;b&gt;x");
    expect(html).not.toContain("<b>x");
  });

  it("so sánh hai học khu ở cùng lane và bậc", async () => {
    await seed();
    const html = await page(
      "/compare?d=test-state/test-valley-unified,test-state/canon-test&lane=MA&step=2",
    );
    // Mức cao nhất có nhãn "Highest"; mức thấp hơn ghi khoảng cách và thanh theo tỉ lệ.
    expect(html).toContain(
      '<td>MA</td><td>2</td><td class="amount-cell"><span class="amount">$55,500</span> <span class="badge badge-top">Highest</span><span class="bar" style="width: 100%"></span></td>',
    );
    expect(html).toContain(
      '<td>Class III (MA)</td><td>Step B</td><td class="amount-cell"><span class="amount">$53,000</span> <span class="badge">Lowest</span><span class="bar" style="width: 95%"></span><span class="gap">$2,500 below the highest</span></td>',
    );
    expect(html).toContain('<tr class="top-row">');
  });

  it("trang /calculator chọn học khu rồi tính", async () => {
    const { a } = await seed();
    expect(await page("/calculator?q=valley")).toContain(
      'href="/calculator?d=test-state/test-valley-unified"',
    );
    const html = await page(
      `/calculator?d=test-state/test-valley-unified&s=${a.scheduleId}&lane=2&step=3`,
    );
    expect(html).toContain('<dd data-out="amount">$54,500 per year</dd>');
  });

  it("trang nội dung có đủ", async () => {
    for (const path of ["/about", "/methodology", "/privacy", "/terms", "/contact"]) {
      expect((await request(path)).status, path).toBe(200);
    }
  });

  it("trang mẫu /demo có ở bản xem trước", async () => {
    const html = await page("/demo", { ENVIRONMENT: "preview" });
    expect(html).toContain("Demo page with made-up data");
    expect(html).toContain('<table class="schedule"');
  });

  it("khung quảng cáo chỉ có khi bật AD_SLOTS", async () => {
    await seed();
    expect(await page("/test-state/test-valley-unified")).not.toContain("ad-slot");
    const html = await page("/test-state/test-valley-unified", { AD_SLOTS: "true" });
    expect(html).toContain('data-ad-slot="below-summary"');
  });
});

describe("trang chủ và trang mới cập nhật", () => {
  it("trang chủ có độ phủ, trung vị lương, học khu mới cập nhật", async () => {
    await seed();
    resetMenuCache();
    const html = await page("/");
    expect(html).toContain("Salary schedules of 2 school districts in 1 state");
    expect(html).toContain("Teacher pay across the site");
    // trung vị khởi điểm chỉ có một học khu (Cañon Test không có BA bậc 1): $50,000
    expect(html).toContain("<dd>$50,000</dd>");
    // trung vị tối đa của $62,000 và $57,000
    expect(html).toContain("<dd>$59,500</dd>");
    expect(html).toContain('href="/recently-updated"');
    expect(html).toContain('<details class="states-menu">');
    // Menu States lấy bang đã có dữ liệu từ D1.
    expect(html).toContain('<li><a href="/test-state">Test State</a></li>');
    expect(html).toContain('href="/test-state/test-valley-unified"');
  });

  it("CSDL trống: trang chủ vẫn hiện, không có số liệu", async () => {
    const html = await page("/");
    expect(html).not.toContain("Teacher pay across the site");
    expect(html).toContain("Browse by state");
  });

  it("/recently-updated liệt kê học khu có bảng published, trang thừa thì 404", async () => {
    await seed();
    const res = await request("/recently-updated");
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Tag")).toContain("home");
    const html = await res.text();
    expect(html).toContain("Test Valley Unified School District</a>");
    expect(html).toContain("Cañon Test School District</a>");
    expect(html).not.toContain("Test Ridge");
    expect(html).toContain("updated November 12, 2026");
    expect((await request("/recently-updated?page=2")).status).toBe(404);
    expect((await request("/recently-updated?page=abc")).status).toBe(404);
  });
});

describe("tải CSV và câu hỏi thường gặp", () => {
  it("bảng published tải được CSV đúng ô; bảng draft hay mã lạ thì 404", async () => {
    const { a, c } = await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain(`href="/schedules/${a.scheduleId}.csv"`);
    const res = await request(`/schedules/${a.scheduleId}.csv`);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("text/csv");
    expect(res.headers.get("Content-Disposition")).toContain(
      `test-valley-unified-2025-26-salary-schedule-${a.scheduleId}.csv`,
    );
    expect(res.headers.get("X-Robots-Tag")).toContain("noindex");
    expect(res.headers.get("Cache-Tag")).toContain(`district-${a.districtId}`);
    const lines = (await res.text()).split("\r\n");
    const header = [
      "Step",
      ...standard.lanes.map((l) => (/[",]/.test(l.labelRaw) ? `"${l.labelRaw}"` : l.labelRaw)),
    ];
    expect(lines[0]).toBe(header.join(","));
    // bậc đầu, lane đầu của bảng mẫu: 5_000_000 cent
    expect(lines[1]?.split(",")[1]).toBe("50000");
    expect(lines.some((l) => l.includes("Source: https://test-valley.example.invalid/"))).toBe(
      true,
    );
    // Ghi nguồn (D-109): ngày tải tài liệu và trang của site đã tổng hợp bảng.
    expect(lines.some((l) => l.includes("(retrieved 2026-11-12)"))).toBe(true);
    expect(lines).toContain(
      "Compiled by Pay Schedules: https://example.invalid/test-state/test-valley-unified",
    );
    expect((await request(`/schedules/${c.scheduleId}.csv`)).status).toBe(404);
    expect((await request("/schedules/abc.csv")).status).toBe(404);
    expect((await request("/schedules/999999.csv")).status).toBe(404);
  });

  it("tải bảng dạng Excel (.xlsx): tệp zip có trang tính với số tiền và nguồn", async () => {
    const { a, c } = await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain(`href="/schedules/${a.scheduleId}.xlsx"`);
    const res = await request(`/schedules/${a.scheduleId}.xlsx`);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    expect(res.headers.get("Content-Disposition")).toContain(
      `test-valley-unified-2025-26-salary-schedule-${a.scheduleId}.xlsx`,
    );
    expect(res.headers.get("X-Robots-Tag")).toContain("noindex");
    const bytes = new Uint8Array(await res.arrayBuffer());
    // Chữ ký zip "PK\x03\x04"; tệp không nén nên đọc được XML bên trong.
    expect([...bytes.slice(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04]);
    const text = new TextDecoder().decode(bytes);
    expect(text).toContain("xl/worksheets/sheet1.xml");
    expect(text).toContain('<c r="A1" t="inlineStr" s="1"><is><t xml:space="preserve">Step</t>');
    // bậc đầu, lane đầu của bảng mẫu: 50.000 USD, định dạng tiền chẵn đô (kiểu 2)
    expect(text).toContain('<c r="B2" s="2"><v>50000</v></c>');
    expect(text).toContain("Source: https://test-valley.example.invalid/");
    expect(text).toContain(
      "Compiled by Pay Schedules: https://example.invalid/test-state/test-valley-unified",
    );
    // Thuộc tính tệp: người tạo và trang gốc.
    expect(text).toContain("docProps/core.xml");
    expect(text).toContain("<dc:creator>Pay Schedules</dc:creator>");
    expect(text).toContain(
      "<dc:identifier>https://example.invalid/test-state/test-valley-unified</dc:identifier>",
    );
    expect((await request(`/schedules/${c.scheduleId}.xlsx`)).status).toBe(404);
    expect((await request("/schedules/1.xls")).status).toBe(404);
  });

  it("câu hỏi sinh từ dữ liệu, có JSON-LD hợp lệ và không mở được thẻ script", async () => {
    await seed();
    const html = await page("/test-state/test-valley-unified");
    expect(html).toContain(
      "What is the starting teacher salary in Test Valley Unified School District?",
    );
    expect(html).toContain("earns $50,000 per year");
    const ld = /<script type="application\/ld\+json">(.*?)<\/script>/s.exec(html)?.[1] ?? "";
    expect(ld).not.toContain("<");
    const data = JSON.parse(ld) as { "@graph": { "@type": string }[] };
    expect(data["@graph"].map((g) => g["@type"])).toEqual(["FAQPage", "BreadcrumbList", "Dataset"]);
    const dataset = data["@graph"][2] as unknown as Record<string, unknown>;
    expect(dataset.temporalCoverage).toBe("2025-07-01/2026-06-30");
    expect(JSON.stringify(dataset.distribution)).toMatch(/\/schedules\/\d+\.csv/);
  });
});

describe("SEO (Công đoạn 7)", () => {
  it("title có mã bang; trùng tên trong bang thì thêm thành phố", async () => {
    const { a, b } = await seed();
    let html = await page("/test-state/test-valley-unified");
    expect(html).toContain(
      "<title>Test Valley Unified School District, ZZ Teacher Salary Schedule 2025–26 · ",
    );
    await db
      .prepare("UPDATE districts SET name = (SELECT name FROM districts WHERE id = ?) WHERE id = ?")
      .bind(a.districtId, b.districtId)
      .run();
    html = await page("/test-state/test-valley-unified");
    expect(html).toContain("<title>Test Valley Unified School District (Testville), ZZ Teacher");
  });

  it("câu so sánh với trung vị của bang khi bang đủ học khu", () => {
    const pay = {
      start: { cents: 4_800_000, districts: 12 },
      maStep10: { cents: null, districts: 0 },
      max: { cents: 6_500_000, districts: 12 },
      lowestStart: null,
      highestStart: null,
      highestMax: null,
    };
    const schedule = { payBasis: "annual" } as Schedule;
    const base = {
      district: { name: "X", state: { name: "Test State", slug: "test-state", code: "ZZ" } },
      year: "2025-26",
      schedules: [schedule],
      summary: {
        schoolYear: "2025-26",
        startBaCents: 5_000_000,
        maStep10Cents: null,
        maxSalaryCents: 6_200_000,
      },
      statePay: pay,
    } as unknown as DistrictPageData;
    expect(stateComparison(base)).toBe(
      "Starting pay for a teacher with a bachelor’s degree is $50,000, $2,000 above the Test State median of $48,000; the top of the scale is $62,000, $3,000 below the state median of $65,000 (medians of 12 Test State districts on this site).",
    );
    const few = {
      ...pay,
      start: { cents: 4_800_000, districts: 3 },
      max: { cents: 1, districts: 3 },
    };
    expect(stateComparison({ ...base, statePay: few })).toBeNull();
    expect(stateComparison({ ...base, year: "2024-25" })).toBeNull();
  });
});
