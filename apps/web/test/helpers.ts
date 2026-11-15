/** Dữ liệu giả lập và hàm gọi Worker cho test của web (AGENTS.md §2.6: dữ liệu GIẢ LẬP). */
import { env } from "cloudflare:workers";
import { oddLanes, standard, stepsOnly } from "../../../packages/db/test/fixtures";
import { insertFixture, resetData } from "../../../packages/db/test/insert";
import { app } from "../src/index";

export const db = env.DB;
export const BASE = "https://example.invalid";

const SUMMARY = `INSERT INTO district_summary (district_id, school_year, schedule_id, start_ba_cents,
                   ma_step10_cents, max_salary_cents, computed_at)
                 VALUES (?, ?, ?, ?, ?, ?, '2026-11-12T08:00:00Z')`;

export async function reset(): Promise<void> {
  await db.prepare("DELETE FROM error_reports").run();
  await resetData(db);
}

/**
 * a: Test Valley Unified (published 2025-26, có lân cận b);
 * b: Cañon Test (published 2024-25, ô trống có ghi chú, có lân cận a);
 * c: Test Ridge (chỉ có bảng draft).
 */
export async function seed() {
  const a = await insertFixture(db, standard);
  const b = await insertFixture(db, oddLanes);
  const c = await insertFixture(db, stepsOnly, "draft");
  const summary = db.prepare(SUMMARY);
  await summary.bind(a.districtId, "2025-26", a.scheduleId, 5_000_000, null, 6_200_000).run();
  await summary.bind(b.districtId, "2024-25", b.scheduleId, null, null, 5_700_000).run();
  await db
    .prepare("INSERT INTO district_neighbors VALUES (?, ?, 12.5), (?, ?, 12.5)")
    .bind(a.districtId, b.districtId, b.districtId, a.districtId)
    .run();
  return { a, b, c };
}

export type EnvOverrides = Partial<Record<string, string>>;

/** Gọi Worker với env thật của test, ghi đè vài biến khi cần. */
export function request(
  path: string,
  init: RequestInit = {},
  overrides: EnvOverrides = {},
  ctx?: ExecutionContext,
): Promise<Response> {
  return Promise.resolve(app.request(`${BASE}${path}`, init, { ...env, ...overrides }, ctx));
}

export async function page(path: string, overrides: EnvOverrides = {}): Promise<string> {
  const res = await request(path, {}, overrides);
  return await res.text();
}

export function form(fields: Record<string, string>): RequestInit {
  const body = new FormData();
  for (const [name, value] of Object.entries(fields)) {
    body.append(name, value);
  }
  return { method: "POST", body };
}

/** Bỏ mọi thẻ <script>, như trình duyệt tắt JavaScript chỉ còn HTML server gửi. */
export function withoutScripts(html: string): string {
  return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
}

/** Nội dung các ô (th và td) theo từng hàng của <tbody> trong bảng có id cho trước. */
export function tableRows(html: string, id: string): string[][] {
  const start = html.indexOf(`<table class="schedule" id="${id}"`);
  if (start < 0) {
    return [];
  }
  const end = html.indexOf("</table>", start);
  const table = html.slice(start, end);
  const body = table.slice(table.indexOf("<tbody>"), table.indexOf("</tbody>"));
  return [...body.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map((row) =>
    [...(row[1] ?? "").matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((cell) =>
      (cell[1] ?? "")
        .replace(/<span class="visually-hidden">[\s\S]*?<\/span>/g, "")
        .replace(/<[^>]+>/g, "")
        .trim(),
    ),
  );
}
