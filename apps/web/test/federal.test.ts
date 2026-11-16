/** Trang bảng lương liên bang (D-065) trên dữ liệu GIẢ LẬP. */
import { beforeEach, describe, expect, it } from "vitest";
import { db, page, request, reset, tableRows, withoutScripts } from "./helpers";

const SHA = "a".repeat(64);

async function insertTable(
  family: string,
  slug: string,
  name: string,
  rows: string[],
  base: number,
  extra: { group?: string; state?: string } = {},
): Promise<number> {
  const res = await db
    .prepare(
      `INSERT INTO pay_tables (family, code, slug, group_slug, name, area, state, year,
         effective_date, title, notes, source_url, source_sha256, fetched_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, 2026, '2026-01-11', ?, ?, ?, ?, '2026-11-16T00:00:00Z')`,
    )
    .bind(
      family,
      slug.toUpperCase(),
      slug,
      extra.group ?? null,
      name,
      name,
      extra.state ?? null,
      `Salary Table 2026-${slug.toUpperCase()}`,
      family === "va_nurse"
        ? null
        : "* Rate limited to the rate for level IV of the Executive Schedule",
      "https://www.opm.gov/table.aspx",
      SHA,
    )
    .run();
  const id = Number(res.meta.last_row_id);
  const insert = db.prepare(
    "INSERT INTO pay_cells (table_id, row_pos, row_label, col_pos, col_label, amount_cents, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
  );
  const stmts = [];
  for (const [i, label] of rows.entries()) {
    for (let j = 0; j < 3; j++) {
      const top = i === rows.length - 1 && j === 2;
      stmts.push(
        insert.bind(
          id,
          i + 1,
          label,
          j + 1,
          `Step ${j + 1}`,
          base + i * 1_000_000 + j * 100_000,
          top ? "*" : null,
        ),
      );
    }
  }
  await db.batch(stmts);
  return id;
}

async function seedFederal() {
  await db
    .prepare("INSERT INTO states (code, name, slug) VALUES ('TN', 'Test State', 'test-state')")
    .run();
  await insertTable("gs", "base", "General Schedule (base)", ["GS-1", "GS-2"], 2_258_400);
  await insertTable("gs_locality", "test-city", "Test City, TS", ["GS-1", "GS-2"], 2_795_700);
  await insertTable("gs_locality", "other-area", "Other Area", ["GS-1", "GS-2"], 2_700_000);
  const va = await insertTable(
    "va_nurse",
    "station-626-n001",
    "VA station 626 (Test City, TN)",
    ["Nurse I", "Nurse II"],
    8_776_900,
    {
      group: "station-626",
      state: "TN",
    },
  );
  return { va };
}

beforeEach(async () => {
  await reset();
});

describe("bảng lương liên bang", () => {
  it("trang tổng có bảng GS cơ bản và danh sách vùng", async () => {
    await seedFederal();
    const html = withoutScripts(await page("/federal-pay"));
    expect(html).toContain("2026 General Schedule base pay");
    expect(html).toContain('href="/federal-pay/gs/test-city"');
    expect(html).toContain('href="/va-nurse-pay"');
    expect(html).toContain("$22,584");
  });

  it("trang một vùng GS: đủ ô, chú thích trần lương, link nguồn", async () => {
    await seedFederal();
    const html = withoutScripts(await page("/federal-pay/gs/test-city"));
    expect(html).toContain("<h1>2026 GS pay: Test City, TS</h1>");
    expect(html).toContain("$27,957");
    expect(html).toContain("<sup");
    expect(html).toContain('href="https://www.opm.gov/table.aspx"');
    expect(html).toContain('href="/federal-pay/gs/other-area"');
  });

  it("y tá VA: danh sách cơ sở và trang cơ sở", async () => {
    const { va } = await seedFederal();
    const list = await page("/va-nurse-pay");
    expect(list).toContain('href="/va-nurse-pay/station-626"');
    expect(list).toContain("Test State");
    const html = withoutScripts(await page("/va-nurse-pay/station-626"));
    const rows = tableRows(html, `pay-${va}`);
    expect(rows[0]).toEqual(["Nurse I", "$87,769", "$88,769", "$89,769"]);
  });

  it("không có dữ liệu hoặc slug sai thì 404", async () => {
    expect((await request("/federal-pay")).status).toBe(404);
    await seedFederal();
    expect((await request("/federal-pay/gs/nowhere")).status).toBe(404);
    expect((await request("/va-nurse-pay/station-999")).status).toBe(404);
  });

  it("sitemap có trang liên bang", async () => {
    await seedFederal();
    const xml = await page("/sitemap.xml");
    expect(xml).toContain("/federal-pay/gs/test-city</loc>");
    expect(xml).toContain("/va-nurse-pay/station-626</loc>");
  });
});
