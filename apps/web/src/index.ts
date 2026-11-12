import { Hono } from "hono";
import { html } from "hono/html";

export type Env = {
  DB: D1Database;
  ASSETS: Fetcher;
  ENVIRONMENT: string;
  INDEXABLE: string;
};

type AppEnv = { Bindings: Env };

/** Tên tạm cho tới khi chủ dự án chọn tên site (DECISIONS.md D-002). */
export const SITE_NAME = "Pay Schedules";

export function isIndexable(env: Env): boolean {
  return env.INDEXABLE === "true";
}

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

const app = new Hono<AppEnv>();

app.use("*", async (c, next) => {
  await next();
  c.header("X-Content-Type-Options", "nosniff");
  c.header("Referrer-Policy", "strict-origin-when-cross-origin");
  if (!isIndexable(c.env)) {
    c.header("X-Robots-Tag", "noindex, nofollow");
  }
});

function layout(env: Env, title: string, body: ReturnType<typeof html>) {
  const robots = isIndexable(env) ? "index, follow" : "noindex, nofollow";
  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="${robots}">
<title>${title}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<main>${body}</main>
</body>
</html>`;
}

app.get("/", async (c) => {
  const migrations = await appliedMigrations(c.env.DB);
  const status =
    migrations === null ? "database not initialised" : `${migrations} migration(s) applied`;
  c.header("Cache-Control", "public, max-age=60");
  return c.html(
    layout(
      c.env,
      SITE_NAME,
      html`<h1>${SITE_NAME}</h1>
<p>Public salary schedules, with a link to every source document. Under construction.</p>
<p class="meta">Environment: ${c.env.ENVIRONMENT} · Database: ${status}</p>`,
    ),
  );
});

app.get("/healthz", async (c) => {
  const migrations = await appliedMigrations(c.env.DB);
  c.header("Cache-Control", "no-store");
  return c.json({ ok: migrations !== null, environment: c.env.ENVIRONMENT, migrations });
});

app.get("/robots.txt", (c) => {
  c.header("Cache-Control", "public, max-age=300");
  const body = isIndexable(c.env) ? "User-agent: *\nAllow: /\n" : "User-agent: *\nDisallow: /\n";
  return c.text(body);
});

app.notFound((c) =>
  c.html(
    layout(
      c.env,
      `Not found · ${SITE_NAME}`,
      html`<h1>Page not found</h1><p><a href="/">Home</a></p>`,
    ),
    404,
  ),
);

export default app;
