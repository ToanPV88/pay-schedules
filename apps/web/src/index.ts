/**
 * Worker web (Công đoạn 6). Mọi trang render phía server từ D1 (DECISIONS.md D-004); JavaScript
 * phía client chỉ dùng cho máy tính lương và sắp xếp bảng (`public/site.js`).
 */
import {
  countDistrictsOfState,
  countSameNameInState,
  DISTRICT_SORTS,
  type District,
  type DistrictSort,
  deleteOldErrorReports,
  findPayTable,
  getCoverage,
  getDistrictById,
  getDistrictBySlug,
  getLatestSummary,
  getPayOverview,
  getPayTable,
  getPublishedScheduleDistrict,
  getSchedule,
  getStateBySlug,
  insertErrorReport,
  latestPayYear,
  listAsReportedChecks,
  listDistrictsOfState,
  listLargestDistricts,
  listMenuStates,
  listNeighbors,
  listPayTables,
  listPayTablesOfGroup,
  listPublishedSchedules,
  listRecentlyUpdated,
  listSitemapRows,
  listStates,
  listVaStations,
  listYearHistory,
  type PayOverview,
  REPORT_MAX_LENGTH,
  REPORT_MIN_LENGTH,
  REPORT_RETENTION_DAYS,
  type Schedule,
  type SearchHit,
  type SortDirection,
  type SummaryEntry,
  searchDistricts,
} from "@pay-schedules/db";
import { type Context, Hono } from "hono";
import { html } from "hono/html";
import {
  cachePurger,
  cacheTags,
  districtTag,
  MAX_PURGE_DISTRICTS,
  NO_STORE,
  PAGE_CACHE,
  purgeTags,
  STATIC_PAGE_CACHE,
  stateTag,
  TAG_COMPARE,
  TAG_HOME,
  TAG_SITEMAP,
  tokensMatch,
} from "./cache";
import { laneCount, positionToIndex } from "./calc";
import { canonicalRedirect } from "./canonical";
import {
  type CompareEntry,
  laneOptions,
  MAX_COMPARE,
  maxSteps,
  parseDistrictKey,
  parseDistrictKeys,
} from "./compare";
import { csvFileName, scheduleCsv } from "./csv";
import { DEMO_DISTRICT, DEMO_HISTORY, DEMO_NEIGHBORS, DEMO_SCHEDULE, DEMO_SUMMARY } from "./demo";
import { type AppEnv, type Env, isIndexable, isProduction, reportsEnabled, SITE_NAME } from "./env";
import { escapeXml, isSchoolYear } from "./format";
import { guard } from "./guard";
import {
  type ApproxLocation,
  type CfLocation,
  locationFromCf,
  locationFromParam,
  nearbyHits,
} from "./nearby";
import {
  featuredPairs,
  findEntry,
  isCanonicalOrder,
  isFeatured,
  pairPath,
  parsePair,
} from "./pairs";
import { latestSummaries, rankOf } from "./ranks";
import { SECURITY_HEADERS } from "./security";
import { verifyTurnstile } from "./turnstile";
import { CONTENT_PAGES } from "./views/content";
import {
  type DistrictPageData,
  type DistrictRanks,
  districtDescription,
  districtDocumentTitle,
  districtPage,
  districtTitle,
  missingSchedulePage,
  type Selection,
} from "./views/district";
import {
  FEDERAL_PATH,
  federalIndexPage,
  gsLocalityPage,
  gsPath,
  VA_NURSE_PATH,
  vaIndexPage,
  vaStationPage,
  vaStationPath,
} from "./views/federal";
import { type Html, type PageMeta, pageTitle, renderPage, type Site } from "./views/layout";
import { RECENT_PAGE_SIZE, recentPage, recentPath } from "./views/overview";
import {
  errorPage,
  HOME_LARGEST,
  HOME_RECENT,
  homePage,
  notFoundPage,
  SEARCH_LIMIT,
  STATE_PAGE_SIZE,
  STATE_RECENT,
  searchPage,
  statePage,
  TOP_LIMIT,
} from "./views/pages";
import { headToHead, pairSummary } from "./views/pair";
import { districtPath, placeLine } from "./views/parts";
import {
  MILESTONE_INFO,
  MIN_INDEXED_STATE,
  milestoneBySlug,
  NATIONAL_LIMIT,
  rankingPage,
  rankingPath,
  rankingsOverviewPage,
} from "./views/rankings";
import { calculatorPage, comparePage, type ReportError, reportPage } from "./views/tools";
import { scheduleXlsx, XLSX_TYPE, xlsxFileName } from "./xlsx";

export type { Env } from "./env";

/** Số migration đã áp lên CSDL, đọc từ bảng `d1_migrations` do wrangler tạo. */
export async function appliedMigrations(db: D1Database): Promise<number | null> {
  try {
    const row = await db.prepare("SELECT COUNT(*) AS n FROM d1_migrations").first<{ n: number }>();
    return row?.n ?? 0;
  } catch {
    // Bảng chưa tồn tại: chưa áp migration nào. Không lộ chi tiết lỗi ra ngoài.
    return null;
  }
}

const NEIGHBOR_LIMIT = 10;

export const app = new Hono<AppEnv>();

app.use("*", async (c, next) => {
  // Một tên miền chính (canonical.ts, D-113); chạy trước mọi việc khác.
  const target = canonicalRedirect(c.req.url, c.req.method, c.env.CANONICAL_ORIGIN);
  if (target !== null) {
    c.header("Cache-Control", "public, max-age=86400");
    return c.redirect(target, 301);
  }
  await next();
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    c.header(name, value);
  }
  if (!isIndexable(c.env)) {
    c.header("X-Robots-Tag", "noindex, nofollow");
  }
});

// Giới hạn tần suất và chuẩn hoá tham số (src/guard.ts). Đặt sau middleware header để phản hồi 429
// và 301 cũng có header bảo mật.
app.use("*", guard);

function site(c: Context<AppEnv>): Site {
  return { env: c.env, origin: new URL(c.req.url).origin };
}

interface Caching {
  control: string;
  tags?: string[];
}

/** Số bang trong menu "States" ở header. */
const MENU_STATE_LIMIT = 8;
const MENU_TTL_MS = 10 * 60 * 1000;
let menuCache: { at: number; value: Promise<{ name: string; slug: string }[]> } | null = null;

/**
 * Bang cho menu "States": đọc D1 một lần mỗi 10 phút trong isolate (header có ở mọi trang, không
 * nên thêm một truy vấn cho mỗi lần dựng trang). Lỗi truy vấn thì trả rỗng để dùng danh sách sẵn.
 */
function menuStates(db: D1Database): Promise<{ name: string; slug: string }[]> {
  const now = Date.now();
  if (!menuCache || now - menuCache.at > MENU_TTL_MS) {
    const value = listMenuStates(db, MENU_STATE_LIMIT).catch(() => []);
    menuCache = { at: now, value };
  }
  return menuCache.value;
}

/** Chỉ dùng trong test: bỏ danh sách bang đã nhớ để đọc lại từ D1. */
export function resetMenuCache(): void {
  menuCache = null;
}

async function page(
  c: Context<AppEnv>,
  meta: PageMeta,
  body: Html,
  caching: Caching,
  status: 200 | 400 | 404 | 500 = 200,
) {
  c.header("Cache-Control", caching.control);
  if (caching.tags) {
    c.header("Cache-Tag", cacheTags(...caching.tags));
  }
  const states = await menuStates(c.env.DB);
  return c.html(renderPage({ ...site(c), menuStates: states }, meta, body), status);
}

function notFound(c: Context<AppEnv>) {
  const meta = { title: pageTitle("Page not found"), noindex: true, script: true };
  return page(c, meta, notFoundPage(), { control: NO_STORE }, 404);
}

/** Trang có tham số (máy tính, tìm kiếm) không nên được lập chỉ mục riêng. */
function hasQuery(c: Context<AppEnv>): boolean {
  return new URL(c.req.url).search !== "";
}

// ---------------------------------------------------------------- vận hành

app.get("/healthz", async (c) => {
  const migrations = await appliedMigrations(c.env.DB);
  c.header("Cache-Control", NO_STORE);
  return c.json({ ok: migrations !== null, environment: c.env.ENVIRONMENT, migrations });
});

app.get("/robots.txt", (c) => {
  c.header("Cache-Control", "public, max-age=300");
  if (!isIndexable(c.env)) {
    return c.text("User-agent: *\nDisallow: /\n");
  }
  const origin = new URL(c.req.url).origin;
  return c.text(
    `User-agent: *\nDisallow: /report\nDisallow: /api/\nAllow: /\nSitemap: ${origin}/sitemap.xml\n`,
  );
});

/** Trang bảng lương liên bang cho sitemap (D-065): trang tổng, từng vùng GS, từng cơ sở VA. */
async function federalSitemapPaths(db: D1Database): Promise<string[]> {
  const paths: string[] = [];
  const gsYear = await latestPayYear(db, "gs_locality").catch(() => null);
  if (gsYear !== null) {
    paths.push(FEDERAL_PATH, gsPath("base"));
    for (const t of await listPayTables(db, "gs_locality", gsYear)) {
      paths.push(gsPath(t.slug));
    }
  }
  const vaYear = await latestPayYear(db, "va_nurse").catch(() => null);
  if (vaYear !== null) {
    paths.push(VA_NURSE_PATH);
    for (const s of await listVaStations(db, vaYear)) {
      paths.push(vaStationPath(s.groupSlug));
    }
  }
  return paths;
}

/** Sitemap chỉ liệt kê trang học khu có bảng published (PLAN Công đoạn 6, nghiệm thu). */
app.get("/sitemap.xml", async (c) => {
  const origin = new URL(c.req.url).origin;
  const rows = await listSitemapRows(c.env.DB);
  const urls: string[] = [];
  let previous = "";
  for (const row of rows) {
    const base = districtPath(row.stateSlug, row.districtSlug);
    // Hàng đầu của mỗi học khu là năm mới nhất: URL không kèm năm.
    const path = base === previous ? `${base}/${row.schoolYear}` : base;
    previous = base;
    const lastmod = row.lastPublished ? `<lastmod>${escapeXml(row.lastPublished)}</lastmod>` : "";
    urls.push(`<url><loc>${escapeXml(`${origin}${path}`)}</loc>${lastmod}</url>`);
  }
  for (const path of await federalSitemapPaths(c.env.DB)) {
    urls.push(`<url><loc>${escapeXml(`${origin}${path}`)}</loc></url>`);
  }
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join("\n")}
</urlset>
`;
  c.header("Cache-Control", PAGE_CACHE);
  c.header("Cache-Tag", cacheTags(TAG_SITEMAP));
  c.header("Content-Type", "application/xml; charset=utf-8");
  return c.body(body);
});

/**
 * Pipeline gọi sau khi publish để xóa cache các trang liên quan (DECISIONS.md D-102).
 * Body: `{"districtIds": [1, 2]}`. Header: `Authorization: Bearer <PURGE_TOKEN>`.
 */
app.post("/internal/purge", async (c) => {
  c.header("Cache-Control", NO_STORE);
  const expected = c.env.PURGE_TOKEN;
  const given = (c.req.header("Authorization") ?? "").replace(/^Bearer /, "");
  if (!expected || !(await tokensMatch(given, expected))) {
    return c.json({ ok: false, error: "unauthorized" }, 401);
  }
  let ids: number[] = [];
  try {
    const body = (await c.req.json()) as { districtIds?: unknown };
    if (Array.isArray(body.districtIds)) {
      ids = body.districtIds.filter((x): x is number => Number.isInteger(x) && x > 0);
    }
  } catch {
    return c.json({ ok: false, error: "invalid JSON" }, 400);
  }
  if (ids.length === 0 || ids.length > MAX_PURGE_DISTRICTS) {
    return c.json({ ok: false, error: `districtIds: 1 to ${MAX_PURGE_DISTRICTS} ids` }, 400);
  }
  const tags = await purgeTags(c.env.DB, ids);
  let ctx: unknown = null;
  try {
    ctx = c.executionCtx;
  } catch {
    ctx = null;
  }
  const purger = cachePurger(ctx);
  if (!purger) {
    return c.json({ ok: false, error: "cache purge is not available here", tags }, 501);
  }
  const result = await purger.purge({ tags });
  const status = result.success ? 200 : 502;
  return c.json({ ok: result.success, tags, errors: result.errors ?? [] }, status);
});

// ---------------------------------------------------------------- trang chủ, tìm kiếm

app.get("/", async (c) => {
  const db = c.env.DB;
  const [states, coverage, pay, recent, largest] = await Promise.all([
    listStates(db),
    getCoverage(db),
    getPayOverview(db),
    listRecentlyUpdated(db, { limit: HOME_RECENT }),
    listLargestDistricts(db, HOME_LARGEST),
  ]);
  const meta = {
    title: `${SITE_NAME}: public school teacher salary schedules`,
    description:
      "Look up the teacher salary schedule of a US public school district, with a salary calculator, nearby-district comparison and a link to the source document.",
    canonicalPath: "/",
    script: true,
  };
  const body = homePage({ states, coverage, pay, recent, largest });
  return page(c, meta, body, { control: PAGE_CACHE, tags: [TAG_HOME] });
});

app.get("/recently-updated", async (c) => {
  const db = c.env.DB;
  const pageNo = Number(c.req.query("page") ?? "1");
  if (!Number.isInteger(pageNo) || pageNo < 1 || pageNo > 1000) {
    return notFound(c);
  }
  const coverage = await getCoverage(db);
  const pages = Math.max(1, Math.ceil(coverage.districts / RECENT_PAGE_SIZE));
  if (pageNo > pages) {
    return notFound(c);
  }
  const offset = (pageNo - 1) * RECENT_PAGE_SIZE;
  const items = await listRecentlyUpdated(db, { limit: RECENT_PAGE_SIZE, offset });
  const meta = {
    title: pageTitle(pageNo > 1 ? `Recently updated, page ${pageNo}` : "Recently updated"),
    description:
      "School districts whose teacher salary schedule was most recently added or updated, with the school year of each schedule.",
    canonicalPath: recentPath(pageNo),
  };
  const body = recentPage({ items, total: coverage.districts, page: pageNo });
  // Danh sách đổi mỗi lần publish: dùng thẻ trang chủ để bị xóa cùng lúc (D-102).
  return page(c, meta, body, { control: PAGE_CACHE, tags: [TAG_HOME] });
});

function queryParam(c: Context<AppEnv>, name: string): string {
  return (c.req.query(name) ?? "").trim().slice(0, 80);
}

async function search(c: Context<AppEnv>, query: string): Promise<SearchHit[]> {
  return query === "" ? [] : await searchDistricts(c.env.DB, query, SEARCH_LIMIT);
}

app.get("/search", async (c) => {
  const query = queryParam(c, "q");
  const hits = await search(c, query);
  const meta = { title: pageTitle("Search school districts"), noindex: true, script: true };
  const caching = { control: "public, max-age=300, s-maxage=3600" };
  return page(c, meta, searchPage(query, hits), caching);
});

/** Số gợi ý tối đa khi gõ vào ô tìm kiếm. */
const SUGGEST_LIMIT = 8;

/**
 * Gợi ý học khu khi gõ (site.js). Cùng truy vấn với /search, ít kết quả hơn, trả JSON. Dưới hai ký
 * tự thì trả danh sách rỗng để không quét cả bảng FTS với một chữ cái.
 */
app.get("/api/suggest", async (c) => {
  const query = queryParam(c, "q");
  const hits = query.length < 2 ? [] : await searchDistricts(c.env.DB, query, SUGGEST_LIMIT);
  c.header("Cache-Control", "public, max-age=300, s-maxage=3600");
  c.header("X-Robots-Tag", "noindex");
  return c.json({
    q: query,
    hits: hits.map((hit) => ({
      name: hit.name,
      place: placeLine(hit.city, hit.county, hit.state.name),
      href: districtPath(hit.state.slug, hit.slug),
      key: `${hit.state.slug}/${hit.slug}`,
      hasSchedule: hit.hasSchedule,
    })),
  });
});

// ---------------------------------------------------------------- trang nội dung

for (const [slug, content] of Object.entries(CONTENT_PAGES)) {
  app.get(`/${slug}`, (c) => {
    const meta = {
      title: pageTitle(content.title),
      description: content.description,
      canonicalPath: `/${slug}`,
    };
    const body = content.body(c.env.CONTACT_EMAIL || null);
    return page(c, meta, body, { control: STATIC_PAGE_CACHE });
  });
}

// ---------------------------------------------------------------- dữ liệu của một học khu

/** Bảng published của một năm học, đọc đầy đủ. */
async function schedulesOfYear(
  db: D1Database,
  districtId: number,
  year: string,
): Promise<Schedule[]> {
  const published = await listPublishedSchedules(db, districtId);
  const ids = published.filter((s) => s.schoolYear === year).map((s) => s.id);
  const schedules = await Promise.all(ids.map((id) => getSchedule(db, id)));
  return schedules.filter((s): s is Schedule => s !== null);
}

/** Đọc lựa chọn máy tính từ query: `s` (id bảng), `lane`, `step` (đếm từ 1). */
function selectionOf(c: Context<AppEnv>, schedules: Schedule[]): Selection | null {
  const id = Number(c.req.query("s"));
  const schedule = schedules.find((s) => s.id === id);
  if (!schedule) {
    return null;
  }
  return {
    scheduleId: schedule.id,
    laneIndex: positionToIndex(c.req.query("lane"), laneCount(schedule)),
    stepIndex: positionToIndex(c.req.query("step"), schedule.steps.length),
  };
}

async function latestSchedules(db: D1Database, district: District): Promise<Schedule[]> {
  const published = await listPublishedSchedules(db, district.id);
  const latest = published[0]?.schoolYear;
  return latest ? await schedulesOfYear(db, district.id, latest) : [];
}

// ---------------------------------------------------------------- so sánh, máy tính

/**
 * Học khu gần người xem (site.js gọi sau khi /calculator hoặc /compare tải). Bản production chỉ dùng
 * vị trí gần đúng Cloudflare gắn vào request; bản preview nhận thêm ?near=TX để thử từ ngoài Mỹ.
 * Không lưu IP hay vị trí; phản hồi chỉ cache ở trình duyệt người xem.
 */
app.get("/api/nearby", async (c) => {
  c.header("Cache-Control", "private, max-age=600");
  c.header("X-Robots-Tag", "noindex");
  const near = c.req.query("near");
  let loc: ApproxLocation | null = null;
  if (near && !isProduction(c.env)) {
    loc = await locationFromParam(c.env.DB, near);
  } else {
    loc = locationFromCf(c.req.raw.cf as CfLocation | undefined);
  }
  if (!loc) {
    return c.json({ basis: "none", hits: [] });
  }
  const hits = await nearbyHits(c.env.DB, loc);
  if (hits.length === 0) {
    return c.json({ basis: "none", hits: [] });
  }
  return c.json({ basis: "location", label: loc.label, hits });
});

/** Số học khu gợi ý sẵn ở trang /calculator và /compare khi chưa chọn học khu nào. */
const POPULAR_LIMIT = 8;

app.get("/compare", async (c) => {
  const keys = parseDistrictKeys(c.req.query("d"));
  const entries: CompareEntry[] = [];
  for (const key of keys) {
    const district = await getDistrictBySlug(c.env.DB, key.stateSlug, key.districtSlug);
    if (district) {
      const [schedules, summary] = await Promise.all([
        latestSchedules(c.env.DB, district),
        getLatestSummary(c.env.DB, district.id),
      ]);
      entries.push({ district, schedule: schedules[0] ?? null, summary });
    }
  }
  const lanes = laneOptions(entries);
  const wanted = c.req.query("lane") ?? "";
  const lane = lanes.includes(wanted) ? wanted : (lanes[0] ?? null);
  const steps = Math.max(1, maxSteps(entries));
  const step = positionToIndex(c.req.query("step"), steps) + 1;
  const query = entries.length < MAX_COMPARE ? queryParam(c, "q") : "";
  const hits = await search(c, query);
  const meta = {
    title: pageTitle("Compare salary schedules"),
    description: "Compare teacher salary schedules of up to four school districts side by side.",
    canonicalPath: "/compare",
    noindex: hasQuery(c),
    // site.js: gợi ý khi gõ và "Districts near you".
    script: true,
  };
  const tags = [TAG_COMPARE, ...entries.map((e) => districtTag(e.district.id))];
  const popular = entries.length === 0 ? await listLargestDistricts(c.env.DB, POPULAR_LIMIT) : [];
  const featured =
    entries.length === 0
      ? pairLinks(featuredPairs(await latestSummaries(c.env.DB)).slice(0, FEATURED_ON_COMPARE))
      : [];
  const body = comparePage({ entries, lanes, lane, steps, step, query, hits, popular, featured });
  return page(c, meta, body, { control: PAGE_CACHE, tags });
});

app.get("/calculator", async (c) => {
  const query = queryParam(c, "q");
  const key = parseDistrictKey(c.req.query("d") ?? "");
  let district: District | null = null;
  let schedules: Schedule[] = [];
  if (key) {
    district = await getDistrictBySlug(c.env.DB, key.stateSlug, key.districtSlug);
    if (district) {
      schedules = await latestSchedules(c.env.DB, district);
    }
  }
  const hits = district ? [] : await search(c, query);
  const selection = selectionOf(c, schedules);
  const title = district ? `Salary calculator: ${district.name}` : "Teacher salary calculator";
  const meta = {
    title: pageTitle(title),
    description: "Read a teacher’s salary from a district’s published schedule by lane and step.",
    canonicalPath: "/calculator",
    noindex: hasQuery(c),
    script: true,
  };
  const tags = district ? [districtTag(district.id)] : [];
  const popular = district ? [] : await listLargestDistricts(c.env.DB, POPULAR_LIMIT);
  const body = calculatorPage({ query, hits, district, schedules, selection, popular });
  return page(c, meta, body, { control: PAGE_CACHE, tags });
});

// ---------------------------------------------------------------- báo lỗi

async function reportDistrict(c: Context<AppEnv>, rawKey: string): Promise<District | null> {
  const key = parseDistrictKey(rawKey);
  if (!key) {
    return null;
  }
  return await getDistrictBySlug(c.env.DB, key.stateSlug, key.districtSlug);
}

function reportScheduleId(raw: string | undefined): number | null {
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** Form tắt cho tới khi chủ dự án tạo khóa Turnstile (DECISIONS.md D-104). */
app.get("/report", async (c) => {
  if (!reportsEnabled(c.env)) {
    return notFound(c);
  }
  const district = await reportDistrict(c, c.req.query("d") ?? "");
  if (!district) {
    return notFound(c);
  }
  const body = reportPage({
    district,
    scheduleId: reportScheduleId(c.req.query("s")),
    siteKey: c.env.TURNSTILE_SITE_KEY ?? "",
    message: "",
    error: null,
    sent: false,
  });
  const meta = { title: pageTitle("Report an error"), noindex: true, turnstile: true };
  return page(c, meta, body, { control: NO_STORE });
});

app.post("/report", async (c) => {
  if (!reportsEnabled(c.env)) {
    return notFound(c);
  }
  const form = await c.req.parseBody();
  const field = (name: string) => (typeof form[name] === "string" ? (form[name] as string) : "");
  const district = await reportDistrict(c, field("d"));
  if (!district) {
    return notFound(c);
  }
  const scheduleId = reportScheduleId(field("s"));
  const message = field("message").trim();
  const meta = { title: pageTitle("Report an error"), noindex: true, turnstile: true };
  const render = (error: ReportError | null, sent: boolean, status: 200 | 400) =>
    page(
      c,
      meta,
      reportPage({
        district,
        scheduleId,
        siteKey: c.env.TURNSTILE_SITE_KEY ?? "",
        message: sent ? "" : message,
        error,
        sent,
      }),
      { control: NO_STORE },
      status,
    );
  // Trường bẫy: người thật không thấy nên để trống. Bot điền vào thì báo "đã nhận" mà không lưu.
  if (field("website") !== "") {
    return render(null, true, 200);
  }
  if (message.length < REPORT_MIN_LENGTH || message.length > REPORT_MAX_LENGTH) {
    return render("length", false, 400);
  }
  if (scheduleId !== null) {
    const owner = await getPublishedScheduleDistrict(c.env.DB, scheduleId);
    if (owner !== district.id) {
      return render("schedule", false, 400);
    }
  }
  const token = field("cf-turnstile-response");
  const ip = c.req.header("CF-Connecting-IP") ?? null;
  const ok = await verifyTurnstile(c.env.TURNSTILE_SECRET_KEY ?? "", token, ip);
  if (!ok) {
    return render("challenge", false, 400);
  }
  const path = districtPath(district.state.slug, district.slug);
  const report = { districtId: district.id, scheduleId, pagePath: path, message };
  await insertErrorReport(c.env.DB, report);
  return render(null, true, 200);
});

// ---------------------------------------------------------------- trang mẫu

app.get("/demo", (c) => {
  if (isProduction(c.env)) {
    return notFound(c);
  }
  const data: DistrictPageData = {
    district: DEMO_DISTRICT,
    year: DEMO_SCHEDULE.schoolYear,
    latestYear: DEMO_SCHEDULE.schoolYear,
    schedules: [DEMO_SCHEDULE],
    history: DEMO_HISTORY,
    summary: DEMO_SUMMARY,
    neighbors: DEMO_NEIGHBORS,
    selection: selectionOf(c, [DEMO_SCHEDULE]),
    reportsEnabled: false,
    asReported: new Map(),
    path: "/demo",
    demo: true,
  };
  const meta = {
    title: pageTitle(districtTitle(DEMO_DISTRICT, data.year)),
    description: districtDescription(data),
    noindex: true,
    script: true,
  };
  return page(c, meta, districtPage(site(c), data), { control: NO_STORE });
});

// ---------------------------------------------------------------- bang và học khu

function sortOf(value: string | undefined): DistrictSort {
  return DISTRICT_SORTS.find((s) => s === value) ?? "name";
}

function directionOf(value: string | undefined): SortDirection {
  return value === "desc" ? "desc" : "asc";
}

app.get("/schedules/:file", async (c) => {
  const match = /^([0-9]{1,9})\.(csv|xlsx)$/.exec(c.req.param("file"));
  if (!match) {
    return notFound(c);
  }
  const schedule = await getSchedule(c.env.DB, Number(match[1]));
  if (schedule?.status !== "published" || schedule.scheduleType !== "teacher") {
    return notFound(c);
  }
  const district = await getDistrictById(c.env.DB, schedule.districtId);
  if (!district) {
    return notFound(c);
  }
  c.header("Cache-Control", PAGE_CACHE);
  c.header("Cache-Tag", cacheTags(districtTag(district.id)));
  c.header("X-Robots-Tag", "noindex");
  // Trang học khu ghi trong tệp (D-109); theo origin của request nên đổi theo tên miền.
  const pageUrl = new URL(districtPath(district.state.slug, district.slug), c.req.url).href;
  if (match[2] === "xlsx") {
    c.header("Content-Disposition", `attachment; filename="${xlsxFileName(district, schedule)}"`);
    return c.body(scheduleXlsx(district, schedule, pageUrl), 200, { "Content-Type": XLSX_TYPE });
  }
  c.header("Content-Disposition", `attachment; filename="${csvFileName(district, schedule)}"`);
  return c.body(scheduleCsv(district, schedule, pageUrl), 200, {
    "Content-Type": "text/csv; charset=utf-8",
  });
});

// ---------------------------------------------------------------- bảng lương liên bang (D-065)

const TAG_FEDERAL = "federal";

app.get(FEDERAL_PATH, async (c) => {
  const year = await latestPayYear(c.env.DB, "gs_locality");
  if (year === null) {
    return notFound(c);
  }
  const [base, localities, vaYear] = await Promise.all([
    findPayTable(c.env.DB, "gs", "base", year),
    listPayTables(c.env.DB, "gs_locality", year),
    latestPayYear(c.env.DB, "va_nurse"),
  ]);
  const meta = {
    title: pageTitle(`${year} GS pay scale: General Schedule and locality pay tables`),
    description: `Official ${year} General Schedule (GS) pay tables from OPM: the base table and all ${localities.length} locality pay areas, by grade and step.`,
    canonicalPath: FEDERAL_PATH,
    noindex: hasQuery(c),
  };
  const body = federalIndexPage({ year, base, localities, vaYear });
  return page(c, meta, body, { control: PAGE_CACHE, tags: [TAG_FEDERAL] });
});

app.get(`${FEDERAL_PATH}/gs/:slug`, async (c) => {
  const year = await latestPayYear(c.env.DB, "gs_locality");
  const slug = c.req.param("slug");
  if (year === null) {
    return notFound(c);
  }
  const table = await findPayTable(c.env.DB, slug === "base" ? "gs" : "gs_locality", slug, year);
  if (!table) {
    return notFound(c);
  }
  const localities = await listPayTables(c.env.DB, "gs_locality", year);
  const name = table.family === "gs" ? "General Schedule base" : table.name;
  const meta = {
    title: pageTitle(`${year} GS pay scale: ${name}`),
    description: `${year} General Schedule annual pay by grade and step for the ${name} locality pay area, from the official OPM salary table.`,
    canonicalPath: gsPath(table.slug),
    noindex: hasQuery(c),
  };
  return page(c, meta, gsLocalityPage({ table, localities }), {
    control: PAGE_CACHE,
    tags: [TAG_FEDERAL],
  });
});

app.get(VA_NURSE_PATH, async (c) => {
  const year = await latestPayYear(c.env.DB, "va_nurse");
  if (year === null) {
    return notFound(c);
  }
  const stations = await listVaStations(c.env.DB, year);
  const meta = {
    title: pageTitle(`VA nurse pay ${year}: locality pay schedules by facility`),
    description: `Official ${year} VA registered nurse locality pay schedules for ${stations.length} VA facilities, by grade and step.`,
    canonicalPath: VA_NURSE_PATH,
    noindex: hasQuery(c),
  };
  return page(c, meta, vaIndexPage(year, stations), { control: PAGE_CACHE, tags: [TAG_FEDERAL] });
});

app.get(`${VA_NURSE_PATH}/:station`, async (c) => {
  const year = await latestPayYear(c.env.DB, "va_nurse");
  if (year === null) {
    return notFound(c);
  }
  const infos = await listPayTablesOfGroup(c.env.DB, "va_nurse", c.req.param("station"), year);
  if (infos.length === 0) {
    return notFound(c);
  }
  const tables = (await Promise.all(infos.map((t) => getPayTable(c.env.DB, t.id)))).filter(
    (t): t is NonNullable<typeof t> => t !== null,
  );
  const name = infos[0]?.name ?? "VA facility";
  const meta = {
    title: pageTitle(`${name} nurse pay ${year}`),
    description: `${year} registered nurse locality pay schedules at ${name}, annual rates by grade and step from the VA.`,
    canonicalPath: vaStationPath(c.req.param("station")),
    noindex: hasQuery(c),
  };
  return page(c, meta, vaStationPage(name, tables), { control: PAGE_CACHE, tags: [TAG_FEDERAL] });
});

// ---------------------------------------------------------------- so sánh hai học khu (D-118)

/** Số cặp nổi bật gợi ý trên /compare khi chưa chọn học khu. */
const FEATURED_ON_COMPARE = 12;

function pairLinks(pairs: [SummaryEntry, SummaryEntry][]): { href: string; label: string }[] {
  return pairs.map(([a, b]) => ({ href: pairPath(a, b), label: `${a.name} vs ${b.name}` }));
}

app.get("/compare/:pair", async (c) => {
  const parsed = parsePair(c.req.param("pair"));
  if (!parsed) {
    return notFound(c);
  }
  const all = await latestSummaries(c.env.DB);
  const a = findEntry(all, parsed[0]);
  const b = findEntry(all, parsed[1]);
  if (!a || !b) {
    return notFound(c);
  }
  if (!isCanonicalOrder(a, b)) {
    c.header("Cache-Control", PAGE_CACHE);
    return c.redirect(`${pairPath(b, a)}${new URL(c.req.url).search}`, 301);
  }
  const entries: CompareEntry[] = [];
  for (const e of [a, b]) {
    const district = await getDistrictBySlug(c.env.DB, e.stateSlug, e.slug);
    if (!district) {
      return notFound(c);
    }
    const [schedules, summary] = await Promise.all([
      latestSchedules(c.env.DB, district),
      getLatestSummary(c.env.DB, district.id),
    ]);
    entries.push({ district, schedule: schedules[0] ?? null, summary });
  }
  const lanes = laneOptions(entries);
  const wanted = c.req.query("lane") ?? "";
  const lane = lanes.includes(wanted) ? wanted : (lanes[0] ?? null);
  const steps = Math.max(1, maxSteps(entries));
  const step = positionToIndex(c.req.query("step"), steps) + 1;
  const featured = isFeatured(featuredPairs(all), a, b);
  const heading = `${a.name} vs ${b.name} teacher salary`;
  const summaryText = pairSummary(a, b);
  const path = pairPath(a, b);
  const meta = {
    title: pageTitle(`${a.name} vs ${b.name}: teacher salary schedules compared`),
    description:
      summaryText ||
      `Teacher salary schedules of ${a.name} and ${b.name} side by side: starting pay, master’s step 10 and the top of the scale.`,
    canonicalPath: path,
    noindex: !featured || hasQuery(c),
    script: true,
  };
  const body = comparePage({
    entries,
    lanes,
    lane,
    steps,
    step,
    query: "",
    hits: [],
    heading,
    lede: html`${summaryText} <a href="${districtPath(a.stateSlug, a.slug)}">${a.name}</a> (${a.stateName}) and <a href="${districtPath(b.stateSlug, b.slug)}">${b.name}</a> (${b.stateName}), from each district’s latest published schedule.`,
    before: headToHead(a, b, all),
  });
  const tags = [TAG_COMPARE, districtTag(a.id), districtTag(b.id)];
  return page(c, meta, body, { control: PAGE_CACHE, tags });
});

// ---------------------------------------------------------------- xếp hạng (D-116)

app.get("/rankings", async (c) => {
  const entries = await latestSummaries(c.env.DB);
  const meta = {
    title: pageTitle("Teacher salary rankings by school district"),
    description:
      "School districts ranked by teacher starting pay, master’s step 10 and the top of the salary scale, nationally and by state.",
    canonicalPath: "/rankings",
  };
  return page(c, meta, rankingsOverviewPage(entries), { control: PAGE_CACHE, tags: [TAG_HOME] });
});

app.get("/rankings/:milestone", async (c) => {
  const milestone = milestoneBySlug(c.req.param("milestone"));
  if (!milestone) {
    return notFound(c);
  }
  const entries = await latestSummaries(c.env.DB);
  const info = MILESTONE_INFO[milestone];
  const meta = {
    title: pageTitle(`Highest teacher ${info.label.toLowerCase()} by school district`),
    description: `The top ${NATIONAL_LIMIT} school districts ranked by teacher ${info.label.toLowerCase()}: ${info.definition}. Rankings by state too.`,
    canonicalPath: rankingPath(milestone),
  };
  const body = rankingPage(entries, milestone, null);
  return page(c, meta, body, { control: PAGE_CACHE, tags: [TAG_HOME] });
});

app.get("/rankings/:milestone/:state", async (c) => {
  const milestone = milestoneBySlug(c.req.param("milestone"));
  if (!milestone) {
    return notFound(c);
  }
  const entries = await latestSummaries(c.env.DB);
  const stateSlug = c.req.param("state");
  const inState = entries.filter((e) => e.stateSlug === stateSlug);
  const first = inState[0];
  if (!first) {
    return notFound(c);
  }
  const state = { slug: stateSlug, name: first.stateName };
  const info = MILESTONE_INFO[milestone];
  const meta = {
    title: pageTitle(`${state.name} teacher ${info.label.toLowerCase()} by district`),
    description: `${state.name} school districts ranked by teacher ${info.label.toLowerCase()}: ${info.definition}.`,
    canonicalPath: rankingPath(milestone, stateSlug),
    noindex: inState.length < MIN_INDEXED_STATE,
  };
  const body = rankingPage(entries, milestone, state);
  return page(c, meta, body, {
    control: PAGE_CACHE,
    tags: [TAG_HOME, stateTag(first.stateCode)],
  });
});

app.get("/:state", async (c) => {
  const state = await getStateBySlug(c.env.DB, c.req.param("state"));
  if (!state) {
    return notFound(c);
  }
  const sort = sortOf(c.req.query("sort"));
  const dir = directionOf(c.req.query("dir"));
  const totals = await countDistrictsOfState(c.env.DB, state.code);
  const pages = Math.max(1, Math.ceil(totals.districts / STATE_PAGE_SIZE));
  const pageNumber = positionToIndex(c.req.query("p"), pages) + 1;
  const items = await listDistrictsOfState(c.env.DB, state.code, {
    sort,
    dir,
    limit: STATE_PAGE_SIZE,
    offset: (pageNumber - 1) * STATE_PAGE_SIZE,
  });
  const meta = {
    title: pageTitle(`${state.name} teacher salary schedules by district`),
    description: `Teacher salary schedules for public school districts in ${state.name}, sortable by starting and maximum salary.`,
    canonicalPath: `/${state.slug}`,
    noindex: hasQuery(c) || totals.withSchedule === 0,
    script: true,
  };
  const top = (sortBy: "start" | "max") =>
    listDistrictsOfState(c.env.DB, state.code, {
      sort: sortBy,
      dir: "desc",
      limit: TOP_LIMIT,
      offset: 0,
    });
  const [pay, recent, topStart, topMax] = await Promise.all([
    getPayOverview(c.env.DB, state.code),
    listRecentlyUpdated(c.env.DB, { limit: STATE_RECENT, stateCode: state.code }),
    top("start"),
    top("max"),
  ]);
  const body = statePage({
    state,
    pay,
    recent,
    items,
    totals,
    sort,
    dir,
    page: pageNumber,
    topStart,
    topMax,
  });
  return page(c, meta, body, { control: PAGE_CACHE, tags: [stateTag(state.code)] });
});

/**
 * Trung vị của bang cho câu so sánh trên trang học khu. Truy vấn đọc mọi học khu của bang, nên giữ
 * trong bộ nhớ của isolate 10 phút: trang học khu nào chưa có trong cache edge cũng không phải đọc
 * lại cả bang (giới hạn số dòng đọc của D1).
 */
const STATE_PAY_TTL_MS = 10 * 60 * 1000;
const statePayCache = new Map<string, { at: number; value: Promise<PayOverview> }>();

function statePayOverview(db: D1Database, stateCode: string): Promise<PayOverview> {
  const now = Date.now();
  const hit = statePayCache.get(stateCode);
  if (hit && now - hit.at < STATE_PAY_TTL_MS) {
    return hit.value;
  }
  const value = getPayOverview(db, stateCode);
  statePayCache.set(stateCode, { at: now, value });
  value.catch(() => statePayCache.delete(stateCode));
  return value;
}

/** Hạng của học khu ở mốc khởi điểm và tối đa, trong bang và toàn quốc (ranks.ts). */
async function districtRanks(
  db: D1Database,
  districtId: number,
  stateCode: string,
): Promise<DistrictRanks | null> {
  const all = await latestSummaries(db);
  if (!all.some((e) => e.id === districtId)) {
    return null;
  }
  const inState = all.filter((e) => e.stateCode === stateCode);
  return {
    start: {
      state: rankOf(inState, districtId, "start"),
      nation: rankOf(all, districtId, "start"),
    },
    max: { state: rankOf(inState, districtId, "max"), nation: rankOf(all, districtId, "max") },
  };
}

/** Số cặp so sánh nổi bật liệt kê trên trang học khu. */
const PAIRS_ON_DISTRICT = 5;

/** Cặp so sánh nổi bật có học khu này (D-118). */
async function districtPairs(
  db: D1Database,
  districtId: number,
): Promise<{ href: string; label: string }[]> {
  const all = await latestSummaries(db);
  const own = featuredPairs(all).filter(([a, b]) => a.id === districtId || b.id === districtId);
  return own.slice(0, PAIRS_ON_DISTRICT).map(([a, b]) => {
    const other = a.id === districtId ? b : a;
    return { href: pairPath(a, b), label: `vs ${other.name}` };
  });
}

async function districtRoute(c: Context<AppEnv>, yearParam: string | null) {
  const district = await getDistrictBySlug(
    c.env.DB,
    c.req.param("state") ?? "",
    c.req.param("district") ?? "",
  );
  if (!district) {
    return notFound(c);
  }
  const base = districtPath(district.state.slug, district.slug);
  const tags = [districtTag(district.id), stateTag(district.state.code)];
  const published = await listPublishedSchedules(c.env.DB, district.id);
  const latestYear = published[0]?.schoolYear;
  if (!latestYear) {
    if (yearParam !== null) {
      return notFound(c);
    }
    const meta = {
      title: pageTitle(`${district.name}: schedule not found`),
      canonicalPath: base,
      noindex: true,
    };
    return page(c, meta, missingSchedulePage(district), { control: PAGE_CACHE, tags });
  }
  if (yearParam === latestYear) {
    c.header("Cache-Control", PAGE_CACHE);
    return c.redirect(base, 301);
  }
  const year = yearParam ?? latestYear;
  const [schedules, history, summary, neighbors, statePay, sameName] = await Promise.all([
    schedulesOfYear(c.env.DB, district.id, year),
    listYearHistory(c.env.DB, district.id),
    getLatestSummary(c.env.DB, district.id),
    listNeighbors(c.env.DB, district.id, NEIGHBOR_LIMIT),
    statePayOverview(c.env.DB, district.state.code),
    countSameNameInState(c.env.DB, district.id),
  ]);
  if (schedules.length === 0) {
    return notFound(c);
  }
  const path = yearParam === null ? base : `${base}/${year}`;
  const ids = schedules.map((s) => s.id);
  const [asReported, ranks] = await Promise.all([
    listAsReportedChecks(c.env.DB, ids),
    summary && summary.schoolYear === year
      ? districtRanks(c.env.DB, district.id, district.state.code)
      : null,
  ]);
  const data: DistrictPageData = {
    district,
    year,
    latestYear,
    schedules,
    history,
    summary,
    neighbors,
    selection: selectionOf(c, schedules),
    reportsEnabled: reportsEnabled(c.env),
    asReported,
    path,
    demo: false,
    statePay,
    ranks,
    pairs: await districtPairs(c.env.DB, district.id),
    sameNameInState: sameName > 1,
  };
  const meta = {
    title: pageTitle(districtDocumentTitle(district, year, sameName > 1)),
    description: districtDescription(data),
    canonicalPath: path,
    // PLAN Công đoạn 7: chỉ index trang có phần so sánh lân cận. Áp dụng sẵn ở đây.
    noindex: hasQuery(c) || neighbors.length === 0,
    script: true,
  };
  return page(c, meta, districtPage(site(c), data), { control: PAGE_CACHE, tags });
}

app.get("/:state/:district", (c) => districtRoute(c, null));

app.get("/:state/:district/:year", (c) => {
  const year = c.req.param("year");
  return isSchoolYear(year) ? districtRoute(c, year) : notFound(c);
});

// ---------------------------------------------------------------- lỗi

app.notFound((c) => notFound(c));

app.onError((err, c) => {
  console.error(err);
  const meta = { title: pageTitle("Something went wrong"), noindex: true };
  return page(c, meta, errorPage(), { control: NO_STORE }, 500);
});

/** Việc định kỳ (wrangler.jsonc `triggers.crons`): xóa báo lỗi quá hạn lưu (D-109). */
async function scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext) {
  ctx.waitUntil(
    deleteOldErrorReports(env.DB).then((n) => {
      console.log(`deleted ${n} error reports older than ${REPORT_RETENTION_DAYS} days`);
    }),
  );
}

export default { fetch: app.fetch, scheduled } satisfies ExportedHandler<Env>;
