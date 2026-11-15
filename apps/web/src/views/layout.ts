import { html } from "hono/html";
import { adSlotsEnabled, type Env, isIndexable, SITE_NAME } from "../env";

export type Html = ReturnType<typeof html>;

export interface Site {
  env: Env;
  /** Gốc của URL đang phục vụ, ví dụ https://example.org. */
  origin: string;
}

export interface PageMeta {
  title: string;
  description?: string;
  /** Đường dẫn chuẩn của trang, không kèm query. */
  canonicalPath?: string;
  /** Trang không nên được lập chỉ mục dù site đã mở index (trang tham số, trang thiếu dữ liệu). */
  noindex?: boolean;
  /** Nạp /site.js: máy tính lương và sắp xếp bảng. */
  script?: boolean;
  /** Nạp script Turnstile; chỉ trang báo lỗi cần. */
  turnstile?: boolean;
}

export const TURNSTILE_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js";

export function robotsContent(env: Env, meta: PageMeta): string {
  if (!isIndexable(env)) {
    return "noindex, nofollow";
  }
  return meta.noindex ? "noindex, follow" : "index, follow";
}

/**
 * Chỗ dành cho quảng cáo, kích thước cố định trong CSS để bố cục không xô lệch. Chưa có mã quảng
 * cáo (Công đoạn 8); khi biến AD_SLOTS khác "true" thì không chiếm chỗ.
 */
export function adSlot(site: Site, position: string): Html {
  if (!adSlotsEnabled(site.env)) {
    return html``;
  }
  return html`<aside class="ad-slot" aria-label="Advertisement" data-ad-slot="${position}"></aside>`;
}

export interface Crumb {
  label: string;
  href?: string;
}

export function breadcrumbs(crumbs: Crumb[]): Html {
  const items: Html[] = [];
  for (const crumb of crumbs) {
    if (crumb.href) {
      items.push(html`<li><a href="${crumb.href}">${crumb.label}</a></li>`);
    } else {
      items.push(html`<li aria-current="page">${crumb.label}</li>`);
    }
  }
  return html`<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>${items}</ol></nav>`;
}

export function renderPage(site: Site, meta: PageMeta, body: Html): Html {
  const head: Html[] = [];
  if (meta.description) {
    head.push(html`<meta name="description" content="${meta.description}">\n`);
  }
  if (meta.canonicalPath) {
    const canonical = `${site.origin}${meta.canonicalPath}`;
    head.push(html`<link rel="canonical" href="${canonical}">\n`);
  }
  if (meta.script) {
    head.push(html`<script src="/site.js" defer></script>\n`);
  }
  if (meta.turnstile) {
    head.push(html`<script src="${TURNSTILE_SCRIPT}" async defer></script>\n`);
  }
  const robots = robotsContent(site.env, meta);
  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="${robots}">
<title>${meta.title}</title>
${head}<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
<a class="site-name" href="/">${SITE_NAME}</a>
<nav class="site-nav" aria-label="Main">
<a href="/search">Search</a>
<a href="/recently-updated">Recently updated</a>
<a href="/compare">Compare</a>
<a href="/calculator">Calculator</a>
<a href="/methodology">Methodology</a>
</nav>
</header>
<main id="main">
${body}
</main>
<footer class="site-footer">
<p>Figures are for reference only. They are extracted automatically from public documents and may contain errors; the linked source document governs. Actual pay is set by each district. This site is not affiliated with any school district or government agency.</p>
<nav aria-label="Footer">
<a href="/about">About</a>
<a href="/methodology">Methodology</a>
<a href="/privacy">Privacy</a>
<a href="/terms">Terms</a>
<a href="/contact">Contact</a>
</nav>
</footer>
</body>
</html>`;
}

/** Tiêu đề thẻ <title> của trang con: "Tên trang · Tên site". */
export function pageTitle(title: string): string {
  return `${title} · ${SITE_NAME}`;
}
