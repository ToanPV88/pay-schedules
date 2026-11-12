import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { getSchedule } from "../src";
import { FIXTURES, type FixtureSchedule, oddLanes, standard, stepsOnly } from "./fixtures";
import { insertFixture, resetData } from "./insert";

const db = env.DB;

beforeEach(async () => {
  await resetData(db);
});

async function rejects(sql: string, ...params: unknown[]): Promise<string> {
  try {
    await db
      .prepare(sql)
      .bind(...params)
      .run();
  } catch (e) {
    return String(e);
  }
  throw new Error(`Câu lệnh lẽ ra phải bị từ chối: ${sql}`);
}

describe("migration", () => {
  it("tạo đủ các bảng của PLAN Công đoạn 2", async () => {
    const { results } = await db
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
      .all<{ name: string }>();
    const names = results.map((r) => r.name);
    for (const t of [
      "states",
      "districts",
      "district_neighbors",
      "source_documents",
      "schedules",
      "lanes",
      "steps",
      "cells",
      "stipends",
      "extraction_runs",
      "review_queue",
      "district_summary",
      "districts_fts",
    ]) {
      expect(names, t).toContain(t);
    }
  });

  it("chừa sẵn cho Công đoạn 10: employer_type, pay_basis, hours_per_year", async () => {
    const district = await db
      .prepare("PRAGMA table_info(districts)")
      .all<{ name: string; dflt_value: string }>();
    const employer = district.results.find((c) => c.name === "employer_type");
    expect(employer?.dflt_value).toBe("'school_district'");
    const schedule = await db.prepare("PRAGMA table_info(schedules)").all<{ name: string }>();
    const cols = schedule.results.map((c) => c.name);
    expect(cols).toContain("pay_basis");
    expect(cols).toContain("hours_per_year");
  });
});

describe("ba bảng lương mẫu nhập tay", () => {
  function expectRoundTrip(f: FixtureSchedule, s: Awaited<ReturnType<typeof getSchedule>>) {
    expect(s).not.toBeNull();
    if (!s) return;
    expect(s.schoolYear).toBe(f.schoolYear);
    expect(s.title).toBe(f.title);
    expect(s.contractDays).toBe(f.contractDays);
    expect(s.payBasis).toBe("annual");
    expect(s.source.url).toBe(f.document.url);
    expect(s.source.sha256).toBe(f.document.sha256);
    expect(s.source.page).toBe(f.document.page);
    expect(s.lanes.map((l) => [l.labelRaw, l.laneNormalized])).toEqual(
      f.lanes.map((l) => [l.labelRaw, l.normalized]),
    );
    expect(s.steps.map((x) => [x.labelRaw, x.yearsExperience])).toEqual(
      f.steps.map((x) => [x.labelRaw, x.years]),
    );
    // Đọc ra đúng từng ô, kể cả ô trống có ghi chú.
    expect(s.cells.length).toBe(f.cells.length);
    for (const [i, row] of f.cells.entries()) {
      expect(s.cells[i]?.length, `bậc ${i}`).toBe(row.length);
      for (const [j, cell] of row.entries()) {
        const got = s.cells[i]?.[j];
        const want =
          typeof cell === "number"
            ? { amountCents: cell, note: null }
            : { amountCents: null, note: cell.empty };
        expect(got, `ô (${i}, ${j})`).toEqual(want);
      }
    }
    expect(s.stipends.map((x) => [x.name, x.amountCents, x.amountRaw])).toEqual(
      f.stipends.map((x) => [x.name, x.amountCents, x.amountRaw]),
    );
  }

  it("bảng chuẩn", async () => {
    const { scheduleId } = await insertFixture(db, standard);
    expectRoundTrip(standard, await getSchedule(db, scheduleId));
  });

  it("bảng có nhãn lane lạ và ô trống", async () => {
    const { scheduleId } = await insertFixture(db, oddLanes);
    const s = await getSchedule(db, scheduleId);
    expectRoundTrip(oddLanes, s);
    expect(s?.lanes[0]?.laneNormalized).toBeNull();
    expect(s?.cells[0]?.[3]).toEqual({
      amountCents: null,
      note: "No placement on this step for Column D",
    });
  });

  it("bảng chỉ có bậc, không có lane", async () => {
    const { scheduleId } = await insertFixture(db, stepsOnly);
    const s = await getSchedule(db, scheduleId);
    expectRoundTrip(stepsOnly, s);
    expect(s?.lanes).toEqual([]);
    expect(s?.cells.every((row) => row.length === 1)).toBe(true);
  });

  it("bảng không tồn tại trả null", async () => {
    expect(await getSchedule(db, 999_999)).toBeNull();
  });

  it("đủ ba mẫu được nghiệm thu", () => {
    expect(FIXTURES.map((f) => f.key)).toEqual(["standard", "odd-lanes", "steps-only"]);
  });
});

describe("ràng buộc dữ liệu", () => {
  it("năm học phải dạng YYYY-YY liên tiếp", async () => {
    const { districtId, documentId } = await insertFixture(db, standard, "draft");
    for (const bad of ["2025-27", "2025/26", "25-26", "2025-2026"]) {
      const err = await rejects(
        "INSERT INTO schedules (district_id, school_year, source_document_id) VALUES (?, ?, ?)",
        districtId,
        bad,
        documentId,
      );
      expect(err, bad).toMatch(/CHECK constraint failed/);
    }
    await db
      .prepare(
        "INSERT INTO schedules (district_id, school_year, source_document_id) VALUES (?, '2099-00', ?)",
      )
      .bind(districtId, documentId)
      .run();
  });

  it("ô trống phải có ghi chú; tiền không âm", async () => {
    const { scheduleId } = await insertFixture(db, stepsOnly, "draft");
    const step = await db
      .prepare("SELECT id FROM steps WHERE schedule_id = ? AND position = 1")
      .bind(scheduleId)
      .first<{ id: number }>();
    await db.prepare("DELETE FROM cells WHERE step_id = ?").bind(step?.id).run();
    expect(
      await rejects(
        "INSERT INTO cells (schedule_id, step_id, lane_id, amount_cents, note) VALUES (?, ?, NULL, NULL, NULL)",
        scheduleId,
        step?.id,
      ),
    ).toMatch(/CHECK constraint failed/);
    expect(
      await rejects(
        "INSERT INTO cells (schedule_id, step_id, amount_cents) VALUES (?, ?, -1)",
        scheduleId,
        step?.id,
      ),
    ).toMatch(/CHECK constraint failed/);
  });

  it("bảng không lane: mỗi bậc chỉ một ô", async () => {
    const { scheduleId } = await insertFixture(db, stepsOnly, "draft");
    const step = await db
      .prepare("SELECT id FROM steps WHERE schedule_id = ? AND position = 2")
      .bind(scheduleId)
      .first<{ id: number }>();
    expect(
      await rejects(
        "INSERT INTO cells (schedule_id, step_id, amount_cents) VALUES (?, ?, 1)",
        scheduleId,
        step?.id,
      ),
    ).toMatch(/UNIQUE constraint failed/);
  });

  it("ô không được trỏ tới bậc hay cột của bảng khác", async () => {
    const a = await insertFixture(db, standard, "draft");
    const b = await insertFixture(db, oddLanes, "draft");
    const foreignStep = await db
      .prepare("SELECT id FROM steps WHERE schedule_id = ? LIMIT 1")
      .bind(b.scheduleId)
      .first<{ id: number }>();
    expect(
      await rejects(
        "INSERT INTO cells (schedule_id, step_id, amount_cents) VALUES (?, ?, 1)",
        a.scheduleId,
        foreignStep?.id,
      ),
    ).toMatch(/FOREIGN KEY constraint failed/);
  });

  it("mỗi khóa (học khu, năm, loại, tiêu đề) chỉ có một bảng published; bản nháp thì được thêm", async () => {
    const { districtId, documentId } = await insertFixture(db, standard, "published");
    // Bản trích lại cùng khóa: được lưu ở trạng thái draft.
    await db
      .prepare(
        "INSERT INTO schedules (district_id, school_year, title, source_document_id) VALUES (?, ?, ?, ?)",
      )
      .bind(districtId, standard.schoolYear, standard.title, documentId)
      .run();
    expect(
      await rejects(
        `INSERT INTO schedules (district_id, school_year, title, source_document_id, status, published_at)
         VALUES (?, ?, ?, ?, 'published', '2026-11-12T08:00:00Z')`,
        districtId,
        standard.schoolYear,
        standard.title,
        documentId,
      ),
    ).toMatch(/UNIQUE constraint failed/);
  });

  it("published cần published_at; superseded cần superseded_by", async () => {
    const { districtId, documentId } = await insertFixture(db, stepsOnly, "draft");
    expect(
      await rejects(
        "INSERT INTO schedules (district_id, school_year, source_document_id, status) VALUES (?, '2023-24', ?, 'published')",
        districtId,
        documentId,
      ),
    ).toMatch(/CHECK constraint failed/);
    expect(
      await rejects(
        "INSERT INTO schedules (district_id, school_year, source_document_id, status) VALUES (?, '2023-24', ?, 'superseded')",
        districtId,
        documentId,
      ),
    ).toMatch(/CHECK constraint failed/);
  });

  it("khóa ngoại được kiểm tra: bảng lương phải có tài liệu nguồn", async () => {
    const { districtId } = await insertFixture(db, stepsOnly, "draft");
    expect(
      await rejects(
        "INSERT INTO schedules (district_id, school_year, source_document_id) VALUES (?, '2025-26', 999999)",
        districtId,
      ),
    ).toMatch(/FOREIGN KEY constraint failed/);
  });

  it("schedule_type chỉ nhận mã có trong bảng schedule_types", async () => {
    const { districtId, documentId } = await insertFixture(db, stepsOnly, "draft");
    expect(
      await rejects(
        "INSERT INTO schedules (district_id, school_year, source_document_id, schedule_type) VALUES (?, '2025-26', ?, 'police_officer')",
        districtId,
        documentId,
      ),
    ).toMatch(/FOREIGN KEY constraint failed/);
  });

  it("sha256 phải là 64 ký tự hex thường", async () => {
    expect(
      await rejects(
        "INSERT INTO source_documents (url, fetched_at, sha256) VALUES ('https://x.example.invalid/a.pdf', '2026-11-12T00:00:00Z', 'ABC')",
      ),
    ).toMatch(/CHECK constraint failed/);
  });
});

describe("tìm kiếm FTS5", () => {
  it("tìm theo tên, thành phố, quận và bỏ dấu", async () => {
    await insertFixture(db, oddLanes);
    await insertFixture(db, stepsOnly);
    const search = async (q: string) =>
      (
        await db
          .prepare(
            "SELECT d.slug FROM districts_fts f JOIN districts d ON d.id = f.rowid WHERE districts_fts MATCH ? ORDER BY rank",
          )
          .bind(q)
          .all<{ slug: string }>()
      ).results.map((r) => r.slug);
    expect(await search("canon")).toContain("canon-test"); // "Cañon" không dấu
    expect(await search("ridge")).toContain("test-ridge");
    expect(await search("fremont")).toContain("canon-test"); // theo quận
  });

  it("đổi tên học khu thì chỉ mục cập nhật theo", async () => {
    const { districtId } = await insertFixture(db, stepsOnly);
    await db
      .prepare("UPDATE districts SET name = 'Renamed Test Academy' WHERE id = ?")
      .bind(districtId)
      .run();
    const hits = await db
      .prepare("SELECT rowid FROM districts_fts WHERE districts_fts MATCH 'renamed'")
      .all<{ rowid: number }>();
    expect(hits.results.map((r) => r.rowid)).toContain(districtId);
  });
});
