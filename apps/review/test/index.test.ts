import { env, exports } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import {
  alternateCells,
  autoTriage,
  drainPurgeQueue,
  type Env,
  PURGE_MAX_ATTEMPTS,
  parseMoney,
} from "../src/index";
import { sameOriginPost } from "../src/origin";
import { TRIAGE_PUBLISHED, triage } from "../src/triage";

const BASE = "https://review.example.invalid";
const AUTH = `Basic ${btoa("review:test-password")}`;
const db = (env as unknown as { DB: D1Database }).DB;

function req(
  path: string,
  init: RequestInit & { auth?: string | null; origin?: string | null } = {},
) {
  const headers = new Headers(init.headers);
  if (init.auth !== null) headers.set("authorization", init.auth ?? AUTH);
  if (init.origin !== null && init.method === "POST") headers.set("origin", init.origin ?? BASE);
  return exports.default.fetch(
    new Request(`${BASE}${path}`, { ...init, headers, redirect: "manual" }),
  );
}

function form(fields: Record<string, string>): RequestInit {
  return {
    method: "POST",
    body: new URLSearchParams(fields).toString(),
    headers: { "content-type": "application/x-www-form-urlencoded" },
  };
}

async function seed() {
  await db.batch([
    db.prepare("DELETE FROM review_edits"),
    db.prepare("DELETE FROM cache_purge_queue"),
    db.prepare("DELETE FROM review_queue"),
    db.prepare("DELETE FROM district_summary"),
    db.prepare("DELETE FROM cells"),
    db.prepare("DELETE FROM steps"),
    db.prepare("DELETE FROM lanes"),
    db.prepare("DELETE FROM schedules"),
    db.prepare("DELETE FROM extraction_runs"),
    db.prepare("DELETE FROM district_pipeline"),
    db.prepare("DELETE FROM source_documents"),
    db.prepare("DELETE FROM districts"),
    db.prepare("DELETE FROM states"),
  ]);
  const raw = JSON.stringify({
    cells: [
      [40000, 45000],
      [41000, 46500],
    ],
  });
  await db.batch([
    db.prepare("INSERT INTO states (code, name, slug) VALUES ('CA', 'California', 'california')"),
    db.prepare(
      "INSERT INTO districts (id, nces_id, name, slug, state, enrollment) VALUES (1, '0600001', 'Test Unified', 'test-unified', 'CA', 5000)",
    ),
    db
      .prepare(
        "INSERT INTO source_documents (id, district_id, url, fetched_at, sha256, release_tag, asset_name) VALUES (1, 1, 'https://test.example.invalid/s.pdf', '2026-11-12T00:00:00Z', ?, 'docs-test', 'x.pdf')",
      )
      .bind("a".repeat(64)),
    db
      .prepare(
        "INSERT INTO extraction_runs (id, source_document_id, model, raw_output) VALUES (1, 1, 'claude-sonnet-5-5', '{}'), (2, 1, 'claude-haiku-5-5', ?)",
      )
      .bind(raw),
    db.prepare(
      "INSERT INTO schedules (id, district_id, school_year, source_document_id, extraction_run_id, status, source_page) VALUES (10, 1, '2025-26', 1, 1, 'draft', 3)",
    ),
    db.prepare(
      "INSERT INTO lanes (id, schedule_id, position, label_raw, lane_normalized) VALUES (1, 10, 1, 'BA', 'BA'), (2, 10, 2, 'MA', 'MA')",
    ),
    db.prepare(
      "INSERT INTO steps (id, schedule_id, position, label_raw) VALUES (1, 10, 1, '1'), (2, 10, 2, '2')",
    ),
    db.prepare(
      "INSERT INTO cells (id, schedule_id, step_id, lane_id, amount_cents) VALUES (1, 10, 1, 1, 4000000), (2, 10, 1, 2, 4500000), (3, 10, 2, 1, 4100000), (4, 10, 2, 2, 4600000)",
    ),
    db.prepare(
      "INSERT INTO review_queue (schedule_id, reason) VALUES (10, '[double_extraction] 1 ô lệch giữa hai lần trích')",
    ),
    db.prepare(
      "INSERT INTO district_pipeline (district_id, status, last_run_key, last_run_at) VALUES (1, 'review', 'r1', '2026-11-12T00:00:00Z')",
    ),
  ]);
}

beforeEach(seed);

describe("bảo vệ", () => {
  it("không có hoặc sai mật khẩu thì 401, không lập chỉ mục", async () => {
    for (const auth of [null, `Basic ${btoa("review:wrong")}`, "Bearer x"]) {
      const res = await req("/", { auth });
      expect(res.status).toBe(401);
      expect(res.headers.get("www-authenticate")).toContain("Basic");
      expect(res.headers.get("x-robots-tag")).toBe("noindex, nofollow");
    }
  });

  it("POST cùng site không có Origin dùng được nhờ Sec-Fetch-Site", async () => {
    const blocked = await req("/s/10/approve", { method: "POST", origin: "null" });
    expect(blocked.status).toBe(403);
    const crossSite = await req("/s/10/approve", {
      method: "POST",
      origin: null,
      headers: { "sec-fetch-site": "cross-site" },
    });
    expect(crossSite.status).toBe(403);
    const res = await req("/", { auth: undefined });
    expect(res.headers.get("referrer-policy")).toBe("same-origin");
    const url = `${BASE}/s/10/approve`;
    expect(sameOriginPost(undefined, "same-origin", url)).toBe(true);
    expect(sameOriginPost("null", "same-origin", url)).toBe(true);
    expect(sameOriginPost(BASE, undefined, url)).toBe(true);
    expect(sameOriginPost("null", undefined, url)).toBe(false);
    expect(sameOriginPost("https://evil.example.invalid", "same-origin", url)).toBe(false);
  });

  it("POST từ origin khác bị chặn", async () => {
    const res = await req("/s/10/approve", {
      method: "POST",
      origin: "https://evil.example.invalid",
    });
    expect(res.status).toBe(403);
    const row = await db
      .prepare("SELECT status FROM schedules WHERE id = 10")
      .first<{ status: string }>();
    expect(row?.status).toBe("draft");
  });
});

describe("xem và duyệt", () => {
  it("hàng chờ và trang bảng", async () => {
    const list = await (await req("/")).text();
    expect(list).toContain("Hàng chờ xem tay: 1 bảng");
    expect(list).toContain("Test Unified");
    const detail = await (await req("/s/10")).text();
    expect(detail).toContain("https://test.example.invalid/s.pdf#page=3");
    expect(detail).toContain('name="cell-4" value="46,000"');
    expect(detail).toContain("claude-haiku-5-5: 46,500"); // ô khác giữa hai lần trích
  });

  it("sửa ô, duyệt: publish, đóng hàng chờ, tính lại tóm tắt", async () => {
    let res = await req("/s/10/cells", form({ "cell-4": "$46,500", "cell-1": "40,000" }));
    expect(res.status).toBe(303);
    const cell = await db
      .prepare("SELECT amount_cents FROM cells WHERE id = 4")
      .first<{ amount_cents: number }>();
    expect(cell?.amount_cents).toBe(4650000);
    const edits = await db.prepare("SELECT COUNT(*) AS n FROM review_edits").first<{ n: number }>();
    expect(edits?.n).toBe(1);
    res = await req("/s/10/cells", form({ "cell-4": "abc" }));
    expect(res.status).toBe(400);

    res = await req("/s/10/approve", { method: "POST" });
    expect(res.status).toBe(303);
    const s = await db.prepare("SELECT status, published_at FROM schedules WHERE id = 10").first<{
      status: string;
      published_at: string;
    }>();
    expect(s?.status).toBe("published");
    expect(s?.published_at).toMatch(/^2\d{3}-/);
    const q = await db
      .prepare("SELECT resolution FROM review_queue WHERE schedule_id = 10")
      .first<{ resolution: string }>();
    expect(q?.resolution).toBe("approved (1 cell edits)");
    const sum = await db
      .prepare(
        "SELECT start_ba_cents, max_salary_cents FROM district_summary WHERE district_id = 1",
      )
      .first<{ start_ba_cents: number; max_salary_cents: number }>();
    expect(sum).toEqual({ start_ba_cents: 4000000, max_salary_cents: 4650000 });
    const p = await db
      .prepare("SELECT status FROM district_pipeline WHERE district_id = 1")
      .first<{ status: string }>();
    expect(p?.status).toBe("published");
    // học khu vào hàng chờ xóa cache (Worker web giả trong test luôn lỗi nên dòng còn đó)
    const queued = await db
      .prepare("SELECT district_id FROM cache_purge_queue")
      .all<{ district_id: number }>();
    expect(queued.results).toEqual([{ district_id: 1 }]);
    res = await req("/s/10/approve", { method: "POST" });
    expect(res.status).toBe(409);
  });

  it("duyệt hết: publish mọi bảng draft còn chờ, theo bang nếu có", async () => {
    let list = await (await req("/")).text();
    expect(list).toContain('action="/approve-all"');
    expect(
      (await req("/approve-all", { method: "POST", origin: "https://evil.example.invalid" }))
        .status,
    ).toBe(403);
    let res = await req("/approve-all", form({ state: "TX" }));
    expect(await res.text()).toContain("Đã duyệt và publish 0 bảng (TX)");
    let s = await db
      .prepare("SELECT status FROM schedules WHERE id = 10")
      .first<{ status: string }>();
    expect(s?.status).toBe("draft");
    res = await req("/approve-all", form({ state: "" }));
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("Đã duyệt và publish 1 bảng");
    s = await db.prepare("SELECT status FROM schedules WHERE id = 10").first<{ status: string }>();
    expect(s?.status).toBe("published");
    const q = await db
      .prepare("SELECT resolution FROM review_queue WHERE schedule_id = 10")
      .first<{ resolution: string }>();
    expect(q?.resolution).toBe("approved in bulk (0 cell edits)");
    const sum = await db
      .prepare("SELECT start_ba_cents FROM district_summary WHERE district_id = 1")
      .first<{ start_ba_cents: number }>();
    expect(sum?.start_ba_cents).toBe(4000000);
    list = await (await req("/")).text();
    expect(list).toContain("Hàng chờ xem tay: 0 bảng");
    expect(list).not.toContain('action="/approve-all"');
  });

  it("duyệt hết bỏ qua bảng đã bị loại", async () => {
    await req("/s/10/reject", form({ reason: "Sai học khu" }));
    const res = await req("/approve-all", form({ state: "" }));
    expect(await res.text()).toContain("Đã duyệt và publish 0 bảng");
    const s = await db
      .prepare("SELECT status FROM schedules WHERE id = 10")
      .first<{ status: string }>();
    expect(s?.status).toBe("draft");
  });

  it("gỡ bảng đã publish theo mã NCES", async () => {
    await req("/s/10/approve", { method: "POST" });
    expect((await req("/unpublish", form({ nces_id: "123", reason: "x" }))).status).toBe(400);
    expect((await req("/unpublish", form({ nces_id: "0600001", reason: " " }))).status).toBe(400);
    const res = await req(
      "/unpublish",
      form({ nces_id: "0600001", reason: "Website của học khu khác" }),
    );
    expect(await res.text()).toContain("Đã gỡ 1 bảng");
    const s = await db
      .prepare("SELECT status, published_at FROM schedules WHERE id = 10")
      .first<{ status: string; published_at: string | null }>();
    expect(s).toEqual({ status: "draft", published_at: null });
    const p = await db
      .prepare("SELECT status, detail FROM district_pipeline WHERE district_id = 1")
      .first<{ status: string; detail: string }>();
    expect(p).toEqual({ status: "no_schedule", detail: "Gỡ khỏi site: Website của học khu khác" });
    const sum = await db
      .prepare("SELECT COUNT(*) AS n FROM district_summary WHERE district_id = 1")
      .first<{ n: number }>();
    expect(sum?.n).toBe(0);
    // không vào lại hàng chờ, nên "Duyệt hết" không publish lại
    expect(await (await req("/approve-all", form({ state: "" }))).text()).toContain(
      "Đã duyệt và publish 0 bảng",
    );
  });

  it("loại cần lý do", async () => {
    expect((await req("/s/10/reject", form({ reason: " " }))).status).toBe(400);
    expect((await req("/s/10/reject", form({ reason: "Không phải bảng giáo viên" }))).status).toBe(
      303,
    );
    const q = await db
      .prepare("SELECT resolution FROM review_queue WHERE schedule_id = 10")
      .first<{ resolution: string }>();
    expect(q?.resolution).toBe("rejected: Không phải bảng giáo viên");
    const p = await db
      .prepare("SELECT status FROM district_pipeline WHERE district_id = 1")
      .first<{ status: string }>();
    expect(p?.status).toBe("no_schedule");
  });
});

describe("xóa cache website (D-023)", () => {
  type Call = { auth: string | null; ids: number[] };

  function fakeEnv(status: number, calls: Call[], extra: Partial<Env> = {}): Env {
    const web = {
      fetch: async (url: string, init: RequestInit) => {
        expect(new URL(url).pathname).toBe("/internal/purge");
        const body = JSON.parse(String(init.body)) as { districtIds: number[] };
        calls.push({
          auth: new Headers(init.headers).get("authorization"),
          ids: body.districtIds,
        });
        return new Response(status === 200 ? "{}" : "nope", { status });
      },
    } as unknown as Fetcher;
    return { DB: db, ENVIRONMENT: "test", PURGE_TOKEN: "tok", WEB: web, ...extra };
  }

  async function queue(n: number) {
    await db.prepare("DELETE FROM cache_purge_queue").run();
    await db.prepare("DELETE FROM districts WHERE id >= 1000").run();
    const ids = Array.from({ length: n }, (_, i) => 1000 + i);
    await db.batch(
      ids.flatMap((id) => [
        db
          .prepare(
            "INSERT INTO districts (id, nces_id, name, slug, state) VALUES (?, ?, 'X', ?, 'CA')",
          )
          .bind(id, String(id).padStart(7, "9"), `x-${id}`),
        db
          .prepare("INSERT INTO cache_purge_queue (district_id, queued_at) VALUES (?, ?)")
          .bind(id, "2026-11-12T00:00:00Z"),
      ]),
    );
  }

  async function left() {
    return (await db.prepare("SELECT COUNT(*) AS n FROM cache_purge_queue").first<{ n: number }>())
      ?.n;
  }

  it("gửi theo lô 100, có token, xóa dòng đã xong", async () => {
    await queue(250);
    const calls: Call[] = [];
    const r = await drainPurgeQueue(fakeEnv(200, calls));
    expect(r).toEqual({ purged: 250, failed: 0 });
    expect(calls.map((c) => c.ids.length)).toEqual([100, 100, 50]);
    expect(calls.every((c) => c.auth === "Bearer tok")).toBe(true);
    expect(await left()).toBe(0);
  });

  it("lỗi: giữ dòng, tăng attempts, dừng; thiếu cấu hình thì không gửi", async () => {
    await queue(3);
    const calls: Call[] = [];
    const r = await drainPurgeQueue(fakeEnv(500, calls));
    expect(r.failed).toBe(3);
    expect(calls).toHaveLength(1);
    const row = await db
      .prepare("SELECT attempts, last_error FROM cache_purge_queue WHERE district_id = 1000")
      .first<{ attempts: number; last_error: string }>();
    expect(row).toEqual({ attempts: 1, last_error: "HTTP 500: nope" });
    expect((await drainPurgeQueue(fakeEnv(200, calls, { PURGE_TOKEN: undefined }))).skipped).toBe(
      "PURGE_TOKEN is not set",
    );
    await db.prepare("UPDATE cache_purge_queue SET attempts = ?").bind(PURGE_MAX_ATTEMPTS).run();
    expect(await drainPurgeQueue(fakeEnv(200, calls))).toEqual({ purged: 0, failed: 0 });
    expect(calls).toHaveLength(1);
    expect(await left()).toBe(3);
  });
});

describe("hàm phụ", () => {
  it("parseMoney", () => {
    expect(parseMoney("$48,899.00")).toBe(4889900);
    expect(parseMoney(" ")).toBeNull();
    expect(parseMoney("12a")).toBeUndefined();
  });

  it("alternateCells bỏ qua bản chính và lưới khác kích thước", () => {
    const runs = [
      { id: 1, model: "a", raw_output: JSON.stringify({ cells: [[1, 2]] }) },
      { id: 2, model: "b", raw_output: JSON.stringify({ cells: [[1, 2, 3]] }) },
      { id: 3, model: "c", raw_output: JSON.stringify({ cells: [[1.5, null]] }) },
    ];
    expect(alternateCells(runs, 1, 1, 2)).toEqual({ model: "c", cells: [[150, null]] });
  });
});

describe("tự phân loại hàng chờ (D-034)", () => {
  const today = new Date("2026-11-13T00:00:00Z");
  const kind = (...reasons: string[]) => triage(reasons, today).kind;
  const oldYear = (year: string) => `[school_year] Bảng năm ${year} đã cũ: có thể có bảng mới hơn`;
  const status = async (sql: string) => {
    const row = await db.prepare(sql).first<{ status: string }>();
    return row?.status;
  };
  const setReason = (reason: string) =>
    db.batch([
      db.prepare("DELETE FROM review_queue"),
      db.prepare("INSERT INTO review_queue (schedule_id, reason) VALUES (10, ?)").bind(reason),
    ]);

  it("quy tắc: bậc đầu cao, bảng cũ gần đây thì publish; quá cũ thì loại; còn lại giữ", () => {
    expect(kind("[step_start] Bảng bắt đầu ở bậc 4: có thể thiếu hàng đầu")).toBe("publish");
    expect(kind(oldYear("2023-24"))).toBe("publish");
    expect(triage([oldYear("2019-20")], today)).toEqual({
      kind: "reject",
      reason: "chỉ tìm thấy bảng năm 2019-20, quá cũ",
    });
    // Cùng mã school_year nhưng là kiểm tra "cũ hơn bảng đang published": để người xem.
    expect(kind("[school_year] Năm học 2024-25 cũ hơn bảng đang published (2025-26)")).toBe("keep");
    expect(kind("[step_start] Bảng bắt đầu ở bậc 3", "[double_extraction] Lệch")).toBe("keep");
    expect(kind("[lane_label] Nhãn lane thiếu tên: 'salary'")).toBe("publish");
    expect(kind("[lane_label] Nhiều lane cùng nhãn 'ba': thiếu tiêu đề cột")).toBe("keep");
    expect(kind("Không mã")).toBe("keep");
    expect(kind()).toBe("keep");
  });

  it("cron: publish như nguồn, resolution 'as reported', xếp xóa cache", async () => {
    await setReason("[step_start] Bảng bắt đầu ở bậc 4: có thể thiếu hàng đầu");
    expect(await autoTriage(db, today)).toMatchObject({ published: 1, rejected: 0 });
    expect(await status("SELECT status FROM schedules WHERE id = 10")).toBe("published");
    const q = await db
      .prepare("SELECT resolution FROM review_queue WHERE schedule_id = 10")
      .first<{ resolution: string }>();
    expect(q?.resolution).toBe(TRIAGE_PUBLISHED);
    expect(q?.resolution.startsWith("as reported")).toBe(true);
    const p = await db
      .prepare("SELECT status, next_run_at FROM district_pipeline WHERE district_id = 1")
      .first<{ status: string; next_run_at: string | null }>();
    expect(p?.status).toBe("published");
    expect(p?.next_run_at).not.toBeNull();
    const purge = await db
      .prepare("SELECT COUNT(*) AS n FROM cache_purge_queue")
      .first<{ n: number }>();
    expect(purge?.n).toBe(1);
  });

  it("cron: bảng quá cũ bị loại, học khu được tìm lại sau", async () => {
    await setReason(oldYear("2018-19"));
    expect(await autoTriage(db, today)).toMatchObject({ published: 0, rejected: 1 });
    expect(await status("SELECT status FROM schedules WHERE id = 10")).toBe("draft");
    const q = await db
      .prepare("SELECT resolution FROM review_queue WHERE schedule_id = 10")
      .first<{ resolution: string }>();
    expect(q?.resolution).toMatch(/^rejected: auto-triage/);
    const p = "SELECT status FROM district_pipeline WHERE district_id = 1";
    expect(await status(p)).toBe("no_schedule");
    // Lần chạy sau không đụng lại bảng đã loại.
    expect(await autoTriage(db, today)).toMatchObject({ published: 0, rejected: 0 });
  });

  it("cron: lý do ngoài nhóm an toàn thì giữ; học khu kẹt 'review' không có draft được thả", async () => {
    expect(await autoTriage(db, today)).toMatchObject({ published: 0, rejected: 0, released: 0 });
    expect(await status("SELECT status FROM schedules WHERE id = 10")).toBe("draft");
    await db.batch([
      db.prepare(
        "INSERT INTO districts (id, nces_id, name, slug, state) VALUES (2, '0600002', 'No Year', 'no-year', 'CA')",
      ),
      db.prepare(
        "INSERT INTO district_pipeline (district_id, status, last_run_key, last_run_at) VALUES (2, 'review', 'r1', '2026-11-12T00:00:00Z')",
      ),
    ]);
    expect(await autoTriage(db, today)).toMatchObject({ released: 1 });
    const pipeline = "SELECT status FROM district_pipeline WHERE district_id = ";
    expect(await status(`${pipeline}2`)).toBe("no_schedule");
    expect(await status(`${pipeline}1`)).toBe("review");
  });
});
