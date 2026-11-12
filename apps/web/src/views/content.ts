/**
 * Trang tin cậy và pháp lý. Đây là bản đầu của Công đoạn 6; Công đoạn 8 rà lại privacy và terms
 * trước khi gắn quảng cáo (cookie, nền tảng quản lý đồng ý).
 */
import { html } from "hono/html";
import { SITE_NAME } from "../env";
import type { Html } from "./layout";

export interface ContentPage {
  title: string;
  description: string;
  body: (contactEmail: string | null) => Html;
}

const about: ContentPage = {
  title: "About",
  description: `What ${SITE_NAME} is and who it is for.`,
  body: () => html`<h1>About ${SITE_NAME}</h1>
<p class="lede">${SITE_NAME} collects the salary schedules that public school districts in the United States publish, and shows each one as a searchable table with a link to its source document.</p>
<p>It is meant for teachers comparing districts, people entering the profession and people moving between states. Each district page adds what a PDF alone does not: a salary calculator, a comparison with nearby districts and earlier school years.</p>
<h2>What this site does not do</h2>
<ul>
<li>It does not publish the names or pay of individual employees. Only the district’s schedule is shown.</li>
<li>It does not estimate or fill in missing figures. A blank cell means the source has no amount there.</li>
<li>It is not affiliated with any school district, union or government agency.</li>
</ul>
<p>See the <a href="/methodology">methodology</a> for how data is collected and checked.</p>`,
};

const methodology: ContentPage = {
  title: "Methodology",
  description: "How salary schedules are collected, extracted and checked.",
  body: () => html`<h1>Methodology</h1>
<p class="lede">Every table on this site comes from a document that a school district or a state education agency publishes. Each table links to that document.</p>
<h2 id="sources">Sources</h2>
<p>The list of districts comes from the National Center for Education Statistics (Common Core of Data). Schedules come from district websites and, where available, from data that state education agencies publish. Documents are downloaded only from public pages, respecting each site’s robots.txt and a minimum delay between requests.</p>
<h2 id="extraction">Extraction</h2>
<p>Tables are read from the documents automatically. The original labels for steps and lanes are kept as written; lanes are also mapped to common levels (BA, MA and so on) when the mapping is unambiguous, so that districts can be compared. Amounts are stored exactly as printed. Nothing is rounded, interpolated or estimated.</p>
<h2 id="checks">Checks</h2>
<p>Before a table is published it must pass automated checks, for example: salaries do not fall as steps or lanes rise, unless the document says why; every cell is accounted for; amounts fall in a plausible range for annual pay; the school year can be read from the document. A table that fails any check is held for review and is not shown.</p>
<p><strong>“Passed automated checks” does not mean a person has verified the table.</strong> Extraction can still be wrong. The source document always governs, and you can report an error from the district page.</p>
<h2 id="comparisons">Comparisons</h2>
<p>Nearby-district comparisons use three cells from each district’s latest published schedule: bachelor’s degree at step 1, master’s degree at step 10, and the highest amount on the schedule. When a schedule has no such cell, the comparison shows a dash. Districts define steps and lanes differently, so a comparison is a starting point, not an equivalence.</p>
<h2 id="history">Earlier years</h2>
<p>When a district publishes a new schedule, the earlier one stays available on its own page. A published table is never edited in place: a corrected table replaces it as a new record.</p>`,
};

const privacy: ContentPage = {
  title: "Privacy",
  description: `What ${SITE_NAME} collects from visitors.`,
  body: () => html`<h1>Privacy</h1>
<p class="lede">This site does not use accounts and does not set cookies of its own.</p>
<h2>Error reports</h2>
<p>If you send an error report, we store the text you write and the page it refers to. We do not store your name, email address or IP address with the report. Please do not include personal information in the message.</p>
<p>The report form uses Cloudflare Turnstile to block spam. Turnstile runs a check in your browser and is covered by <a href="https://www.cloudflare.com/turnstile-privacy-policy/" rel="noopener">Cloudflare’s Turnstile privacy addendum</a>.</p>
<h2>Server logs</h2>
<p>The site runs on Cloudflare, which processes requests and keeps operational logs as described in <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener">Cloudflare’s privacy policy</a>.</p>
<h2>Advertising</h2>
<p>The site does not show advertising yet. This page will be updated, including how to opt out of advertising cookies, before any advertising is added.</p>`,
};

const terms: ContentPage = {
  title: "Terms of use",
  description: `Terms for using ${SITE_NAME}.`,
  body: () => html`<h1>Terms of use</h1>
<p class="lede">The information on this site is provided for reference only, without warranty of any kind.</p>
<ul>
<li>Figures are extracted automatically from public documents and may contain errors or be out of date. The district’s own document governs. Actual pay, placement on a schedule and credit for experience are decided by each district.</li>
<li>Nothing on this site is legal, financial or employment advice.</li>
<li>The source documents belong to their publishers. Links to them are provided so that every figure can be checked.</li>
<li>Do not use automated tools to download large parts of the site in a way that degrades it for others.</li>
</ul>
<p>Districts that want a table corrected or removed can use the <a href="/contact">contact page</a>.</p>`,
};

const contact: ContentPage = {
  title: "Contact",
  description: `How to contact ${SITE_NAME}.`,
  body: (contactEmail) => {
    const email = contactEmail
      ? html`<p>Email: <a href="mailto:${contactEmail}">${contactEmail}</a></p>`
      : html`<p>A contact address will be listed here soon.</p>`;
    return html`<h1>Contact</h1>
<p class="lede">To report a wrong figure, use the “Report an error” button on the district page, so the report is linked to the right table.</p>
<h2>School districts</h2>
<p>If you represent a district and want a schedule corrected, updated or removed, contact us with the district name and a link to the current document. We handle these requests before any other work.</p>
${email}`;
  },
};

export const CONTENT_PAGES: Record<string, ContentPage> = {
  about,
  methodology,
  privacy,
  terms,
  contact,
};
