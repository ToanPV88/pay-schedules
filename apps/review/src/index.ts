// Trang xem tay nội bộ (PLAN Công đoạn 5, DECISIONS.md D-021).
// Danh sách bảng lương trong review_queue; xem bảng cạnh link tài liệu gốc; sửa ô; duyệt (publish)
// hoặc loại. Bảo vệ bằng HTTP Basic, mật khẩu là secret REVIEW_PASSWORD; thiếu secret thì đóng.
// Worker này cũng xóa cache của website sau khi publish (D-023): hàng chờ cache_purge_queue do
// pipeline và nút "Duyệt" ghi vào; lịch chạy (cron) và nút "Duyệt" gọi POST /internal/purge của
// Worker web qua service binding WEB, kèm secret PURGE_TOKEN.
import { Hono } from "hono";
import { html } from "hono/html";
import type { HtmlEscapedString } from "hono/utils/html";
import { sameOriginPost } from "./origin";
import { SINGLE_SALARY_LANE, TRIAGE_PUBLISHED, TRIAGE_REJECTED, triage } from "./triage";

export type Env = {
  DB: D1Database;
  ENVIRONMENT: string;
  REVIEW_PASSWORD?: string;
  PURGE_TOKEN?: string;
  WEB?: Fetcher;
};

type AppEnv = { Bindings: Env };
type Html = HtmlEscapedString | Promise<HtmlEscapedString>;

const PAGE_SIZE = 100;
const PUBLISHED_RETRY_DAYS = 180;
const REJECTED_RETRY_DAYS = 90;
/** Giới hạn của /internal/purge bên Worker web (MAX_PURGE_DISTRICTS). */
const PURGE_BATCH = 100;
/** Số lô mỗi lần cron chạy: giữ số subrequest của một lần chạy nhỏ. */
const PURGE_BATCHES_PER_RUN = 10;
/** Sau ngần này lần lỗi liên tiếp, dòng nằm lại để người xem (hiện trên trang hàng chờ). */
export const PURGE_MAX_ATTEMPTS = 20;

export type PurgeResult = { purged: number; failed: number; skipped?: string };

/**
 * Gửi các học khu trong cache_purge_queue sang Worker web để xóa cache theo thẻ (D-102, D-023).
 * Thành công thì xóa dòng (chỉ khi queued_at chưa đổi, để lần ghi mới hơn không bị mất); lỗi thì
 * tăng attempts, ghi last_error và dừng, lần chạy sau thử lại.
 */
export async function drainPurgeQueue(
  env: Env,
  maxBatches = PURGE_BATCHES_PER_RUN,
): Promise<PurgeResult> {
  if (!env.WEB) return { purged: 0, failed: 0, skipped: "no WEB service binding" };
  if (!env.PURGE_TOKEN) return { purged: 0, failed: 0, skipped: "PURGE_TOKEN is not set" };
  const db = env.DB;
  let purged = 0;
  for (let i = 0; i < maxBatches; i++) {
    const { results } = await db
      .prepare(
        `SELECT district_id, queued_at FROM cache_purge_queue WHERE attempts < ?1
          ORDER BY queued_at, district_id LIMIT ?2`,
      )
      .bind(PURGE_MAX_ATTEMPTS, PURGE_BATCH)
      .all<{ district_id: number; queued_at: string }>();
    if (results.length === 0) break;
    let error: string | null = null;
    try {
      const res = await env.WEB.fetch("https://web.internal/internal/purge", {
        method: "POST",
        headers: {
          authorization: `Bearer ${env.PURGE_TOKEN}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ districtIds: results.map((r) => r.district_id) }),
      });
      if (!res.ok) error = `HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`;
    } catch (e) {
      error = String(e).slice(0, 200);
    }
    if (error !== null) {
      await db.batch(
        results.map((r) =>
          db
            .prepare(
              "UPDATE cache_purge_queue SET attempts = attempts + 1, last_error = ? WHERE district_id = ?",
            )
            .bind(error, r.district_id),
        ),
      );
      return { purged, failed: results.length, skipped: error };
    }
    await db.batch(
      results.map((r) =>
        db
          .prepare("DELETE FROM cache_purge_queue WHERE district_id = ? AND queued_at = ?")
          .bind(r.district_id, r.queued_at),
      ),
    );
    purged += results.length;
    if (results.length < PURGE_BATCH) break;
  }
  return { purged, failed: 0 };
}

export function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function plusDays(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** "$48,899.00" / "48899" -> 4889900; "" -> null; anything else -> undefined (invalid). */
export function parseMoney(text: string): number | null | undefined {
  const t = text.replace(/[$,\s]/g, "");
  if (t === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return undefined;
  return Math.round(Number(t) * 100);
}

function money(cents: number | null): string {
  return cents === null ? "" : (cents / 100).toLocaleString("en-US", { minimumFractionDigits: 0 });
}

async function sameSecret(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  return crypto.subtle.timingSafeEqual(ha, hb);
}

const app = new Hono<AppEnv>();

app.use("*", async (c, next) => {
  c.header("X-Robots-Tag", "noindex, nofollow");
  c.header("Cache-Control", "no-store");
  c.header("X-Frame-Options", "DENY");
  // "same-origin": browsers then send the real Origin on the page's own form posts ("no-referrer"
  // made them send "Origin: null", which the check below refused).
  c.header("Referrer-Policy", "same-origin");
  const expected = c.env.REVIEW_PASSWORD;
  if (!expected) return c.text("Review is not configured.", 503);
  const header = c.req.header("authorization") ?? "";
  let password = "";
  if (header.startsWith("Basic ")) {
    try {
      password = atob(header.slice(6)).split(":").slice(1).join(":");
    } catch {
      password = "";
    }
  }
  if (!password || !(await sameSecret(password, expected))) {
    c.header("WWW-Authenticate", 'Basic realm="pay-schedules review", charset="UTF-8"');
    return c.text("Authentication required.", 401);
  }
  if (
    c.req.method === "POST" &&
    !sameOriginPost(c.req.header("origin"), c.req.header("sec-fetch-site"), c.req.url)
  ) {
    return c.text("Bad origin.", 403);
  }
  await next();
});

app.get("/robots.txt", (c) => c.text("User-agent: *\nDisallow: /\n"));

function page(env: Env, title: string, body: Html) {
  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${title} · review (${env.ENVIRONMENT})</title>
<style>
body{font:14px/1.4 system-ui,sans-serif;margin:16px;color:#111;background:#fff}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 6px;text-align:right}
th{background:#f3f3f3}td.l,th.l{text-align:left}.bad{background:#ffe0e0}.blank{color:#999}
input.cell{width:7em;text-align:right;font:inherit}.reasons{white-space:pre-wrap;background:#fff7e0;padding:8px}
.actions{display:flex;gap:16px;margin:12px 0}nav a{margin-right:12px}
</style>
</head>
<body><nav><a href="/">Hàng chờ</a> <span>${env.ENVIRONMENT}</span></nav>${body}</body>
</html>`;
}

type QueueRow = {
  id: number;
  school_year: string;
  name: string;
  state: string;
  nces_id: string;
  url: string;
  state_file: number;
  n: number;
  reasons: string;
};

app.get("/", async (c) => {
  const state = (c.req.query("state") ?? "").toUpperCase();
  const offset = Math.max(0, Number.parseInt(c.req.query("offset") ?? "0", 10) || 0);
  const filter = /^[A-Z]{2}$/.test(state) ? "AND d.state = ?2" : "AND ?2 = ?2";
  const { results } = await c.env.DB.prepare(
    `SELECT s.id, s.school_year, d.name, d.state, d.nces_id, sd.url,
            (sd.district_id IS NULL) AS state_file, COUNT(r.id) AS n,
            group_concat(r.reason, char(10)) AS reasons
       FROM review_queue r JOIN schedules s ON s.id = r.schedule_id
       JOIN districts d ON d.id = s.district_id
       JOIN source_documents sd ON sd.id = s.source_document_id
      WHERE r.resolved_at IS NULL ${filter}
      GROUP BY s.id ORDER BY d.enrollment IS NULL, d.enrollment DESC, s.id
      LIMIT ${PAGE_SIZE} OFFSET ?1`,
  )
    .bind(offset, state)
    .all<QueueRow>();
  const total = await c.env.DB.prepare(
    "SELECT COUNT(DISTINCT schedule_id) AS n FROM review_queue WHERE resolved_at IS NULL",
  ).first<{ n: number }>();
  const purge = await c.env.DB.prepare(
    "SELECT COUNT(*) AS n, COUNT(last_error) AS errors, MAX(last_error) AS last FROM cache_purge_queue",
  ).first<{ n: number; errors: number; last: string | null }>();
  const rows = results.map(
    (r) => html`<tr><td class="l"><a href="/s/${r.id}">${r.name}</a></td><td>${r.state}</td>
<td>${r.school_year}</td><td class="l">${r.state_file ? "tệp của bang" : "PDF học khu"}</td>
<td class="l">${r.reasons.split("\n")[0]?.slice(0, 160)}${r.n > 1 ? ` (+${r.n - 1})` : ""}</td></tr>`,
  );
  return c.html(
    page(
      c.env,
      "Hàng chờ xem tay",
      html`<h1>Hàng chờ xem tay: ${total?.n ?? 0} bảng</h1>
<form method="get"><label>Bang <input name="state" value="${state}" size="3"></label> <button>Lọc</button></form>
<p>Chờ xóa cache web: ${purge?.n ?? 0} học khu${purge?.errors ? ` (${purge.errors} lỗi; gần nhất: ${purge.last})` : ""}${c.env.WEB && c.env.PURGE_TOKEN ? "" : " · chưa cấu hình xóa cache (WEB hoặc PURGE_TOKEN)"}</p>
<table><tr><th class="l">Học khu</th><th>Bang</th><th>Năm học</th><th class="l">Nguồn</th><th class="l">Lý do</th></tr>${rows}</table>
<p><a href="/?state=${state}&offset=${offset + PAGE_SIZE}">Trang sau</a></p>`,
    ),
  );
});

type ScheduleRow = {
  id: number;
  district_id: number;
  school_year: string;
  schedule_type: string;
  title: string;
  status: string;
  contract_days: number | null;
  notes: string | null;
  source_page: number | null;
  extraction_run_id: number | null;
  source_document_id: number;
  name: string;
  state: string;
  nces_id: string;
  website: string | null;
  url: string;
  release_tag: string | null;
  asset_name: string | null;
};

async function loadSchedule(db: D1Database, id: number) {
  const s = await db
    .prepare(
      `SELECT s.id, s.district_id, s.school_year, s.schedule_type, s.title, s.status,
              s.contract_days, s.notes, s.source_page, s.extraction_run_id, s.source_document_id,
              d.name, d.state, d.nces_id, d.website, sd.url, sd.release_tag, sd.asset_name
         FROM schedules s JOIN districts d ON d.id = s.district_id
         JOIN source_documents sd ON sd.id = s.source_document_id WHERE s.id = ?`,
    )
    .bind(id)
    .first<ScheduleRow>();
  if (!s) return null;
  const [lanes, steps, cells, reasons, runs] = await db.batch([
    db
      .prepare("SELECT id, position, label_raw FROM lanes WHERE schedule_id = ? ORDER BY position")
      .bind(id),
    db
      .prepare("SELECT id, position, label_raw FROM steps WHERE schedule_id = ? ORDER BY position")
      .bind(id),
    db
      .prepare("SELECT id, step_id, lane_id, amount_cents, note FROM cells WHERE schedule_id = ?")
      .bind(id),
    db
      .prepare(
        "SELECT reason, resolved_at, resolution FROM review_queue WHERE schedule_id = ? ORDER BY id",
      )
      .bind(id),
    db
      .prepare(
        "SELECT id, model, raw_output FROM extraction_runs WHERE source_document_id = ? ORDER BY id",
      )
      .bind(s.source_document_id),
  ]);
  return {
    s,
    lanes: (lanes?.results ?? []) as { id: number; position: number; label_raw: string }[],
    steps: (steps?.results ?? []) as { id: number; position: number; label_raw: string }[],
    cells: (cells?.results ?? []) as {
      id: number;
      step_id: number;
      lane_id: number | null;
      amount_cents: number | null;
      note: string | null;
    }[],
    reasons: (reasons?.results ?? []) as {
      reason: string;
      resolved_at: string | null;
      resolution: string | null;
    }[],
    runs: (runs?.results ?? []) as { id: number; model: string; raw_output: string }[],
  };
}

/** Values of the other extraction (if its grid has the same shape), for highlighting. */
export function alternateCells(
  runs: { id: number; model: string; raw_output: string }[],
  primaryRunId: number | null,
  steps: number,
  lanes: number,
): { model: string; cells: (number | null)[][] } | null {
  for (const run of runs) {
    if (run.id === primaryRunId) continue;
    try {
      const data = JSON.parse(run.raw_output) as { cells?: unknown };
      const cells = data.cells;
      if (!Array.isArray(cells) || cells.length !== steps) continue;
      const width = Math.max(lanes, 1);
      if (!cells.every((r) => Array.isArray(r) && r.length === width)) continue;
      return {
        model: run.model,
        cells: (cells as unknown[][]).map((r) =>
          r.map((v) => (typeof v === "number" ? Math.round(v * 100) : null)),
        ),
      };
    } catch {}
  }
  return null;
}

app.get("/s/:id{[0-9]+}", async (c) => {
  const data = await loadSchedule(c.env.DB, Number(c.req.param("id")));
  if (!data) return c.notFound();
  const { s, lanes, steps, cells, reasons, runs } = data;
  const byKey = new Map(cells.map((x) => [`${x.step_id}:${x.lane_id ?? ""}`, x]));
  const alt = alternateCells(runs, s.extraction_run_id, steps.length, lanes.length);
  const editable = s.status === "draft";
  const laneList = lanes.length ? lanes : [{ id: null, position: 1, label_raw: "Amount" }];
  const body = steps.map((st, i) => {
    const tds = laneList.map((ln, j) => {
      const cell = byKey.get(`${st.id}:${ln.id ?? ""}`);
      if (!cell) return html`<td class="bad">thiếu</td>`;
      const other = alt?.cells[i]?.[j];
      const differs = alt !== null && other !== undefined && other !== cell.amount_cents;
      const title = differs
        ? `${alt?.model}: ${money(other ?? null) || "trống"}`
        : (cell.note ?? "");
      const value = money(cell.amount_cents);
      return editable
        ? html`<td class="${differs ? "bad" : ""}" title="${title}"><input class="cell" name="cell-${cell.id}" value="${value}"></td>`
        : html`<td class="${differs ? "bad" : ""}" title="${title}">${value || html`<span class="blank">–</span>`}</td>`;
    });
    return html`<tr><th class="l">${st.label_raw}</th>${tds}</tr>`;
  });
  const grid = html`<table><tr><th class="l">Bậc</th>${laneList.map((l) => html`<th>${l.label_raw}</th>`)}</tr>${body}</table>`;
  const docLink = s.source_page ? `${s.url}#page=${s.source_page}` : s.url;
  const reasonText = reasons
    .map((r) => (r.resolved_at ? `[đã xử lý: ${r.resolution}] ${r.reason}` : r.reason))
    .join("\n");
  return c.html(
    page(
      c.env,
      `${s.name} ${s.school_year}`,
      html`<h1>${s.name} (${s.state}) · ${s.school_year} · ${s.status}</h1>
<p>Tài liệu gốc: <a href="${docLink}" target="_blank" rel="noopener noreferrer">${s.url}</a>${s.source_page ? ` (trang ${s.source_page})` : ""}
· Release: ${s.release_tag ?? "–"} / ${s.asset_name ?? "–"} · NCES ${s.nces_id}
${s.website ? html` · <a href="${s.website}" target="_blank" rel="noopener noreferrer">website học khu</a>` : ""}</p>
<p>Số ngày: ${s.contract_days ?? "–"}${alt ? html` · Ô tô đỏ: bản ${alt.model} khác (rê chuột để xem)` : ""}</p>
<div class="reasons">${reasonText || "Không có lý do xem tay."}</div>
${s.notes ? html`<details><summary>Ghi chú trong tài liệu</summary><pre>${s.notes}</pre></details>` : ""}
${
  editable
    ? html`<form method="post" action="/s/${s.id}/cells">${grid}<p><button>Lưu các ô đã sửa</button></p></form>
<div class="actions">
<form method="post" action="/s/${s.id}/approve"><button>Duyệt và publish</button></form>
<form method="post" action="/s/${s.id}/reject"><input name="reason" placeholder="Lý do loại" required size="40"> <button>Loại</button></form>
</div>`
    : grid
}`,
    ),
  );
});

app.post("/s/:id{[0-9]+}/cells", async (c) => {
  const id = Number(c.req.param("id"));
  const data = await loadSchedule(c.env.DB, id);
  if (!data) return c.notFound();
  if (data.s.status !== "draft") return c.text("Chỉ sửa được bảng draft.", 409);
  const form = await c.req.parseBody();
  const stamp = nowIso();
  const statements: D1PreparedStatement[] = [];
  for (const cell of data.cells) {
    const field = form[`cell-${cell.id}`];
    if (typeof field !== "string") continue;
    const cents = parseMoney(field);
    if (cents === undefined) return c.text(`Số tiền không hợp lệ: ${field}`, 400);
    if (cents === cell.amount_cents) continue;
    const note = cents === null ? "Blank (set by reviewer)" : cell.note;
    statements.push(
      c.env.DB.prepare(
        "UPDATE cells SET amount_cents = ?, note = ? WHERE id = ? AND schedule_id = ?",
      ).bind(cents, note, cell.id, id),
      c.env.DB.prepare(
        `INSERT INTO review_edits (schedule_id, cell_id, old_amount_cents, new_amount_cents,
           old_note, new_note, edited_at) VALUES (?, ?, ?, ?, ?, ?, ?)`,
      ).bind(id, cell.id, cell.amount_cents, cents, cell.note, note, stamp),
    );
  }
  if (statements.length) await c.env.DB.batch(statements);
  return c.redirect(`/s/${id}`, 303);
});

const SUMMARY_CELL = (pos: number, lane: string) =>
  `(SELECT c.amount_cents FROM cells c JOIN steps t ON t.id = c.step_id JOIN lanes l ON l.id = c.lane_id
     WHERE c.schedule_id = s.id AND t.position = ${pos} AND l.lane_normalized = '${lane}')`;

/** Same rules as the pipeline (D-018): first published teacher schedule of each year. */
export function summaryStatements(
  db: D1Database,
  districtId: number,
  stamp: string,
): D1PreparedStatement[] {
  return [
    db.prepare("DELETE FROM district_summary WHERE district_id = ?").bind(districtId),
    db
      .prepare(
        `INSERT INTO district_summary (district_id, school_year, schedule_id, start_ba_cents,
           ma_step10_cents, max_salary_cents, computed_at)
         SELECT s.district_id, s.school_year, s.id, ${SUMMARY_CELL(1, "BA")}, ${SUMMARY_CELL(10, "MA")},
                (SELECT max(amount_cents) FROM cells WHERE schedule_id = s.id), ?2
           FROM schedules s
          WHERE s.district_id = ?1 AND s.status = 'published' AND s.schedule_type = 'teacher'
            AND s.id = (SELECT min(x.id) FROM schedules x WHERE x.district_id = s.district_id
                         AND x.school_year = s.school_year AND x.status = 'published'
                         AND x.schedule_type = 'teacher')`,
      )
      .bind(districtId, stamp),
  ];
}

type DraftKey = {
  id: number;
  district_id: number;
  school_year: string;
  schedule_type: string;
  title: string;
};

/** Publish một bảng draft: dùng chung cho nút "Duyệt" và tự phân loại (D-034). */
function publishStatements(
  db: D1Database,
  s: DraftKey,
  stamp: string,
  resolution: string,
  detail: string,
): D1PreparedStatement[] {
  return [
    db
      .prepare(
        `UPDATE schedules SET status = 'superseded', superseded_by = ?1
          WHERE district_id = ?2 AND school_year = ?3 AND schedule_type = ?4 AND title = ?5
            AND status = 'published' AND id <> ?1`,
      )
      .bind(s.id, s.district_id, s.school_year, s.schedule_type, s.title),
    db
      .prepare(
        "UPDATE schedules SET status = 'published', published_at = ? WHERE id = ? AND status = 'draft'",
      )
      .bind(stamp, s.id),
    db
      .prepare(
        "UPDATE review_queue SET resolved_at = ?, resolution = ? WHERE schedule_id = ? AND resolved_at IS NULL",
      )
      .bind(stamp, resolution, s.id),
    db
      .prepare(
        "UPDATE district_pipeline SET status = 'published', detail = ?, next_run_at = ? WHERE district_id = ?",
      )
      .bind(detail, plusDays(PUBLISHED_RETRY_DAYS), s.district_id),
    ...summaryStatements(db, s.district_id, stamp),
    db
      .prepare(
        `INSERT INTO cache_purge_queue (district_id, queued_at) VALUES (?, ?)
         ON CONFLICT (district_id) DO UPDATE SET queued_at = excluded.queued_at`,
      )
      .bind(s.district_id, stamp),
  ];
}

function rejectStatements(
  db: D1Database,
  scheduleId: number,
  districtId: number,
  stamp: string,
  resolution: string,
  detail: string,
): D1PreparedStatement[] {
  return [
    db
      .prepare(
        "UPDATE review_queue SET resolved_at = ?, resolution = ? WHERE schedule_id = ? AND resolved_at IS NULL",
      )
      .bind(stamp, resolution, scheduleId),
    db
      .prepare(
        "UPDATE district_pipeline SET status = 'no_schedule', detail = ?, next_run_at = ? WHERE district_id = ?",
      )
      .bind(detail, plusDays(REJECTED_RETRY_DAYS), districtId),
  ];
}

/** Bảng draft xử lý mỗi lần cron chạy: giữ mỗi lần chạy nhỏ. */
const TRIAGE_PER_RUN = 50;

export type TriageResult = { published: number; rejected: number; kept: number; released: number };

/**
 * Tự phân loại hàng chờ (D-034): publish như nguồn hoặc loại các bảng chỉ vướng lý do an toàn;
 * còn lại để người xem. Cũng trả về hàng chờ của pipeline các học khu kẹt ở trạng thái review mà
 * không có bảng draft nào (không đọc được năm học): tìm lại sau 90 ngày.
 */
export async function autoTriage(db: D1Database, today = new Date()): Promise<TriageResult> {
  const { results } = await db
    .prepare(
      `SELECT s.id, s.district_id, s.school_year, s.schedule_type, s.title,
              json_group_array(r.reason) AS reasons
         FROM schedules s
         JOIN review_queue r ON r.schedule_id = s.id AND r.resolved_at IS NULL
        WHERE s.status = 'draft'
          AND NOT EXISTS (SELECT 1 FROM review_queue x WHERE x.schedule_id = s.id
                           AND x.resolution LIKE 'rejected%')
          -- Chỉ lấy bảng mà mọi lý do còn mở đều thuộc nhóm tự xử lý được; triage() kiểm lại.
          AND NOT EXISTS (SELECT 1 FROM review_queue o WHERE o.schedule_id = s.id
                           AND o.resolved_at IS NULL
                           AND o.reason NOT LIKE '[step_start]%'
                           AND o.reason NOT LIKE '[school_year] Bảng năm %đã cũ%'
                           AND o.reason <> ?2)
        GROUP BY s.id
        ORDER BY s.id
        LIMIT ?1`,
    )
    .bind(TRIAGE_PER_RUN, SINGLE_SALARY_LANE)
    .all<DraftKey & { reasons: string }>();
  const stamp = nowIso();
  const statements: D1PreparedStatement[] = [];
  const out: TriageResult = { published: 0, rejected: 0, kept: 0, released: 0 };
  for (const row of results) {
    const decision = triage(JSON.parse(row.reasons) as string[], today);
    if (decision.kind === "publish") {
      const detail = `Tự publish như nguồn ${row.school_year}`;
      statements.push(...publishStatements(db, row, stamp, TRIAGE_PUBLISHED, detail));
      out.published++;
    } else if (decision.kind === "reject") {
      const resolution = `${TRIAGE_REJECTED}: ${decision.reason}`;
      const detail = `Tự loại: ${decision.reason}`;
      statements.push(...rejectStatements(db, row.id, row.district_id, stamp, resolution, detail));
      out.rejected++;
    } else {
      out.kept++;
    }
  }
  statements.push(
    db
      .prepare(
        `UPDATE district_pipeline SET status = 'no_schedule', next_run_at = ?
          WHERE status = 'review' AND next_run_at IS NULL
            AND NOT EXISTS (SELECT 1 FROM schedules s WHERE s.district_id = district_pipeline.district_id
                             AND s.status = 'draft')`,
      )
      .bind(plusDays(REJECTED_RETRY_DAYS)),
  );
  const done = await db.batch(statements);
  out.released = done[done.length - 1]?.meta.changes ?? 0;
  return out;
}

app.post("/s/:id{[0-9]+}/approve", async (c) => {
  const id = Number(c.req.param("id"));
  const data = await loadSchedule(c.env.DB, id);
  if (!data) return c.notFound();
  const { s } = data;
  if (s.status !== "draft") return c.text("Chỉ duyệt được bảng draft.", 409);
  const stamp = nowIso();
  const edits = await c.env.DB.prepare(
    "SELECT COUNT(*) AS n FROM review_edits WHERE schedule_id = ?",
  )
    .bind(id)
    .first<{ n: number }>();
  await c.env.DB.batch(
    publishStatements(
      c.env.DB,
      { ...s, id },
      stamp,
      `approved (${edits?.n ?? 0} cell edits)`,
      `Duyệt tay ${s.school_year}`,
    ),
  );
  c.executionCtx.waitUntil(drainPurgeQueue(c.env, 1));
  return c.redirect(`/s/${id}`, 303);
});

app.post("/s/:id{[0-9]+}/reject", async (c) => {
  const id = Number(c.req.param("id"));
  const data = await loadSchedule(c.env.DB, id);
  if (!data) return c.notFound();
  if (data.s.status !== "draft") return c.text("Chỉ loại được bảng draft.", 409);
  const form = await c.req.parseBody();
  const reason = typeof form.reason === "string" ? form.reason.trim().slice(0, 500) : "";
  if (!reason) return c.text("Cần lý do.", 400);
  const stamp = nowIso();
  await c.env.DB.batch(
    rejectStatements(
      c.env.DB,
      id,
      data.s.district_id,
      stamp,
      `rejected: ${reason}`,
      `Loại khi xem tay: ${reason}`,
    ),
  );
  return c.redirect("/", 303);
});

export default {
  fetch: app.fetch,
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(
      autoTriage(env.DB)
        .then((t) => {
          if (t.published || t.rejected || t.released) {
            console.log("auto-triage", JSON.stringify(t));
          }
        })
        .catch((e) => console.error("auto-triage", e))
        .then(() => drainPurgeQueue(env))
        .then((r) => {
          if (r.skipped || r.failed) console.warn("cache purge", JSON.stringify(r));
        }),
    );
  },
} satisfies ExportedHandler<Env>;
