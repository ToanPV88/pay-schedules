import { html, raw } from "hono/html";
import { adSlotsEnabled, type Env, isIndexable, SITE_NAME } from "../env";

export type Html = ReturnType<typeof html>;

export interface Site {
  env: Env;
  /** Gốc của URL đang phục vụ, ví dụ https://example.org. */
  origin: string;
  /** Bang cho menu "States" (bang có dữ liệu, đông học sinh trước); thiếu thì dùng danh sách sẵn. */
  menuStates?: { name: string; slug: string }[];
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

/**
 * Logo "PS" cạnh tên site, vẽ thẳng trong HTML (không thêm request), cùng hình với favicon. Chữ là
 * đường vẽ lấy từ phông Inter ExtraBold (OFL) để hiện giống nhau trên mọi máy, không phụ thuộc phông.
 */
const LOGO = raw(
  '<svg class="logo" viewBox="0 0 32 32" width="28" height="28" aria-hidden="true" focusable="false"><rect width="32" height="32" rx="7" fill="currentColor"/><path class="logo-text" fill="#fff" d="M5.56 22.33H8.56V18.38H10.66C13.56 18.38 15.35 16.65 15.35 14.05C15.35 11.45 13.6 9.67 10.74 9.67H5.56ZM8.56 16.01V12.1H10.1C11.51 12.1 12.24 12.86 12.24 14.05C12.24 15.22 11.51 16.01 10.11 16.01ZM21.44 22.5C24.57 22.5 26.44 21.06 26.44 18.66C26.44 16.64 25.02 15.41 22.58 14.88L21.48 14.62C20.35 14.37 19.61 13.99 19.61 13.21C19.61 12.51 20.23 11.99 21.43 11.99C22.64 11.99 23.31 12.52 23.39 13.44H26.27C26.24 11.1 24.37 9.5 21.44 9.5C18.57 9.5 16.51 11.07 16.51 13.42C16.51 15.32 17.84 16.42 20.02 16.92L21.36 17.23C22.75 17.55 23.41 17.93 23.41 18.65C23.41 19.46 22.64 20.01 21.4 20.01C20.04 20.01 19.13 19.38 19.06 18.15H16.18C16.23 21.07 18.27 22.5 21.44 22.5Z"/></svg>',
);

const MENU_ICON = raw(
  '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
);

/**
 * Menu thu gọn trên điện thoại. Script nằm ngay sau nav, chạy trước lần vẽ đầu nên không nháy.
 * Tắt JavaScript thì header không có lớp js-nav: nút Menu bị ẩn và mọi liên kết vẫn hiện như cũ.
 */
/** Mã của NAV_SCRIPT (không kể thẻ), để security.ts tính hash cho CSP. */
export const NAV_SCRIPT_BODY =
  '(()=>{const b=document.querySelector(".nav-toggle");const h=b&&b.closest(".site-header");if(!h)return;h.classList.add("js-nav");b.addEventListener("click",()=>{const o=h.classList.toggle("nav-open");b.setAttribute("aria-expanded",String(o));});})();';
const NAV_SCRIPT = raw(`<script>${NAV_SCRIPT_BODY}</script>`);

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

/** Ảnh xem trước khi chia sẻ link (1200×630), nằm trong public/. */
export const OG_IMAGE = "/og-image.png";

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
  // Thẻ chia sẻ (Facebook, Zalo, X, Slack…): tiêu đề và mô tả của trang, một ảnh chung của site.
  const share: Html[] = [
    html`<meta property="og:type" content="website">\n`,
    html`<meta property="og:site_name" content="${SITE_NAME}">\n`,
    html`<meta property="og:title" content="${meta.title}">\n`,
    html`<meta property="og:image" content="${site.origin}${OG_IMAGE}">\n`,
    html`<meta property="og:image:width" content="1200">\n`,
    html`<meta property="og:image:height" content="630">\n`,
    html`<meta property="og:image:alt" content="${SITE_NAME}: public school teacher salary schedules">\n`,
    html`<meta name="twitter:card" content="summary_large_image">\n`,
  ];
  if (meta.description) {
    share.push(html`<meta property="og:description" content="${meta.description}">\n`);
  }
  // Trang có tham số (tìm kiếm, máy tính) không có địa chỉ chuẩn: để mạng xã hội dùng chính link đó.
  if (meta.canonicalPath) {
    share.push(html`<meta property="og:url" content="${site.origin}${meta.canonicalPath}">\n`);
  }
  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="${robots}">
<title>${meta.title}</title>
${head}${share}<meta name="theme-color" content="#9f224e">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
<div class="wrap header-inner">
<a class="site-name" href="/">${LOGO}<span>${SITE_NAME}</span></a>
<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">${MENU_ICON}<span>Menu</span></button>
<nav class="site-nav" id="site-nav" aria-label="Main">
${statesMenu(site.menuStates)}
<a href="/search">Search</a>
<a href="/recently-updated">Recently updated</a>
<a href="/compare">Compare</a>
<a href="/calculator">Calculator</a>
<a href="/federal-pay">Federal pay</a>
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
<p class="copyright">© ${new Date().getUTCFullYear()} ${SITE_NAME}. Pay figures come from public district documents; the compilation, checks and site text are our own.</p>
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
/** Danh sách dự phòng khi chưa đọc được bang từ D1 (lỗi truy vấn, test không có dữ liệu). */
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
function statesMenu(states?: { name: string; slug: string }[]): Html {
  const list =
    states && states.length > 0 ? states : MENU_STATES.map(([name, slug]) => ({ name, slug }));
  const links = list.map(({ name, slug }) => html`<li><a href="/${slug}">${name}</a></li>`);
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
