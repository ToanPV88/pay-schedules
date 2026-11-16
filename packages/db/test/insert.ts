/** Ghi một bảng lương mẫu vào D1 bằng SQL thẳng, như người nhập tay. Chỉ dùng trong test. */
import type { FixtureSchedule } from "./fixtures";

async function insertId(db: D1Database, sql: string, ...params: unknown[]): Promise<number> {
  const result = await db
    .prepare(sql)
    .bind(...params)
    .run();
  return Number(result.meta.last_row_id);
}

export async function ensureTestState(db: D1Database): Promise<void> {
  await db
    .prepare(
      "INSERT OR IGNORE INTO states (code, name, slug) VALUES ('ZZ', 'Test State', 'test-state')",
    )
    .run();
}

export async function insertFixture(
  db: D1Database,
  f: FixtureSchedule,
  status: "draft" | "published" = "published",
): Promise<{ scheduleId: number; districtId: number; documentId: number }> {
  await ensureTestState(db);
  const districtId = await insertId(
    db,
    "INSERT INTO districts (name, slug, state, city, county) VALUES (?, ?, 'ZZ', ?, ?)",
    f.district.name,
    f.district.slug,
    f.district.city,
    f.district.county,
  );
  const documentId = await insertId(
    db,
    "INSERT INTO source_documents (district_id, url, fetched_at, sha256, mime, page_count) VALUES (?, ?, ?, ?, 'application/pdf', ?)",
    districtId,
    f.document.url,
    "2026-11-12T07:00:00Z",
    f.document.sha256,
    f.document.page,
  );
  const scheduleId = await insertId(
    db,
    `INSERT INTO schedules (district_id, school_year, title, contract_days, source_document_id,
                            source_page, status, published_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    districtId,
    f.schoolYear,
    f.title,
    f.contractDays,
    documentId,
    f.document.page,
    status,
    status === "published" ? "2026-11-12T07:05:00Z" : null,
  );

  const laneIds: number[] = [];
  for (const [j, lane] of f.lanes.entries()) {
    laneIds.push(
      await insertId(
        db,
        "INSERT INTO lanes (schedule_id, position, label_raw, lane_normalized) VALUES (?, ?, ?, ?)",
        scheduleId,
        j + 1,
        lane.labelRaw,
        lane.normalized,
      ),
    );
  }
  const stepIds: number[] = [];
  for (const [i, step] of f.steps.entries()) {
    stepIds.push(
      await insertId(
        db,
        "INSERT INTO steps (schedule_id, position, label_raw, years_experience) VALUES (?, ?, ?, ?)",
        scheduleId,
        i + 1,
        step.labelRaw,
        step.years,
      ),
    );
  }
  for (const [i, row] of f.cells.entries()) {
    for (const [j, cell] of row.entries()) {
      const amount = typeof cell === "number" ? cell : null;
      const note = typeof cell === "number" ? null : cell.empty;
      await db
        .prepare(
          "INSERT INTO cells (schedule_id, step_id, lane_id, amount_cents, note) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(scheduleId, stepIds[i], f.lanes.length ? laneIds[j] : null, amount, note)
        .run();
    }
  }
  for (const s of f.stipends) {
    await db
      .prepare(
        "INSERT INTO stipends (schedule_id, name, amount_cents, amount_raw) VALUES (?, ?, ?, ?)",
      )
      .bind(scheduleId, s.name, s.amountCents, s.amountRaw)
      .run();
  }
  return { scheduleId, districtId, documentId };
}

/** Xóa sạch dữ liệu giữa các test (D1 cục bộ dùng chung trong một tệp test). Chỉ dùng trong test. */
export async function resetData(db: D1Database): Promise<void> {
  await db.batch(
    [
      "pay_cells",
      "pay_tables",
      "district_summary",
      "review_queue",
      "cells",
      "stipends",
      "lanes",
      "steps",
      "schedules",
      "extraction_runs",
      "source_documents",
      "district_neighbors",
      "districts",
      "states",
    ].map((t) => db.prepare(`DELETE FROM ${t}`)),
  );
}
