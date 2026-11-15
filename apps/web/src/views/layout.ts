import { html, raw } from "hono/html";
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

/** Logo cạnh tên site, vẽ thẳng trong HTML (không thêm request), cùng hình với favicon. */
const LOGO = raw(
  '<svg class="logo" viewBox="0 0 32 32" width="28" height="28" aria-hidden="true" focusable="false"><rect width="32" height="32" rx="7" fill="currentColor"/><path d="M8 22h16M8 16h16M8 10h16M14 7v18" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/></svg>',
);

const MENU_ICON = raw(
  '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
);

/**
 * Menu thu gọn trên điện thoại. Script nằm ngay sau nav, chạy trước lần vẽ đầu nên không nháy.
 * Tắt JavaScript thì header không có lớp js-nav: nút Menu bị ẩn và mọi liên kết vẫn hiện như cũ.
 */
const NAV_SCRIPT = raw(
  '<script>(()=>{const b=document.querySelector(".nav-toggle");const h=b&&b.closest(".site-header");if(!h)return;h.classList.add("js-nav");b.addEventListener("click",()=>{const o=h.classList.toggle("nav-open");b.setAttribute("aria-expanded",String(o));});})();</script>',
);

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
<div class="wrap header-inner">
<a class="site-name" href="/">${LOGO}<span>${SITE_NAME}</span></a>
<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">${MENU_ICON}<span>Menu</span></button>
<nav class="site-nav" id="site-nav" aria-label="Main">
${statesMenu()}
<a href="/search">Search</a>
<a href="/recently-updated">Recently updated</a>
<a href="/compare">Compare</a>
<a href="/calculator">Calculator</a>
<a href="/methodology">Methodology</a>
</nav>
${NAV_SCRIPT}
</div>
</header>
<main id="main">
${body}
</main>
<footer class="site-footer">
<div class="wrap">
<p>Figures are for reference only. They are extracted automatically from public documents and may contain errors; the linked source document governs. Actual pay is set by each district. This site is not affiliated with any school district or government agency.</p>
<nav aria-label="Footer">
<a href="/about">About</a>
<a href="/methodology">Methodology</a>
<a href="/privacy">Privacy</a>
<a href="/terms">Terms</a>
<a href="/contact">Contact</a>
</nav>
</div>
</footer>
</body>
</html>`;
}

/** Tám bang đông học sinh nhất; danh sách đủ ở trang chủ. Slug theo tên bang như pipeline đặt. */
const MENU_STATES = [
  ["California", "california"],
  ["Texas", "texas"],
  ["Florida", "florida"],
  ["New York", "new-york"],
  ["Illinois", "illinois"],
  ["Georgia", "georgia"],
  ["Pennsylvania", "pennsylvania"],
  ["Ohio", "ohio"],
] as const;

/** Menu "States" bằng <details>: mở được bằng bàn phím, không cần JavaScript. */
function statesMenu(): Html {
  const links = MENU_STATES.map(([name, slug]) => html`<li><a href="/${slug}">${name}</a></li>`);
  return html`<details class="states-menu">
<summary>States</summary>
<ul>
${links}
<li><a href="/#states-heading">All states</a></li>
</ul>
</details>`;
}

/** Tiêu đề thẻ <title> của trang con: "Tên trang · Tên site". */
export function pageTitle(title: string): string {
  return `${title} · ${SITE_NAME}`;
}
