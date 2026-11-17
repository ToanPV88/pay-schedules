/**
 * Trang xếp hạng học khu theo ba mốc lương (DECISIONS.md D-116): /rankings, /rankings/<mốc>,
 * /rankings/<mốc>/<bang>. Số liệu là mốc của năm mới nhất mỗi học khu (ranks.ts).
 */
import type { SummaryEntry } from "@pay-schedules/db";
import { html } from "hono/html";
import { formatCents, schoolYearLabel } from "../format";
import { MILESTONES, type Milestone, ranking } from "../ranks";
import { breadcrumbs, type Html } from "./layout";
import { districtPath } from "./parts";

export interface MilestoneInfo {
  slug: string;
  /** Tiêu đề ngắn. */
  label: string;
  /** Định nghĩa đầy đủ cho câu dẫn. */
  definition: string;
}

export const MILESTONE_INFO: Record<Milestone, MilestoneInfo> = {
  start: {
    slug: "starting-pay",
    label: "Starting pay",
    definition: "the first step of the bachelor’s degree column, what a new teacher is paid",
  },
  ma10: {
    slug: "masters-step-10",
    label: "Master’s, step 10",
    definition: "the master’s degree column at step 10, a typical mid-career salary",
  },
  max: {
    slug: "top-of-scale",
    label: "Top of the scale",
    definition: "the highest salary on the schedule, the most a teacher can reach",
  },
};

/** Số học khu trên trang xếp hạng toàn quốc của một mốc. */
export const NATIONAL_LIMIT = 100;
/** Số học khu mỗi mốc trên trang tổng quan /rankings. */
export const OVERVIEW_LIMIT = 10;
/** Trang xếp hạng của bang có ít học khu hơn thì không cho index (nội dung mỏng). */
export const MIN_INDEXED_STATE = 5;

export function milestoneBySlug(slug: string): Milestone | null {
  return MILESTONES.find((m) => MILESTONE_INFO[m].slug === slug) ?? null;
}

export function rankingPath(milestone: Milestone, stateSlug?: string): string {
  const base = `/rankings/${MILESTONE_INFO[milestone].slug}`;
  return stateSlug ? `${base}/${stateSlug}` : base;
}

export interface StateLink {
  slug: string;
  name: string;
  count: number;
}

/** Các bang có học khu có số ở mốc, theo tên. */
export function statesWithData(entries: SummaryEntry[], milestone: Milestone): StateLink[] {
  const states = new Map<string, StateLink>();
  for (const e of entries) {
    const has =
      milestone === "start"
        ? e.startBaCents
        : milestone === "ma10"
          ? e.maStep10Cents
          : e.maxSalaryCents;
    if (has === null) {
      continue;
    }
    const s = states.get(e.stateSlug) ?? { slug: e.stateSlug, name: e.stateName, count: 0 };
    s.count += 1;
    states.set(e.stateSlug, s);
  }
  return [...states.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function rankTable(rows: ReturnType<typeof ranking>, caption: string, showState: boolean): Html {
  const body = rows.map(
    (
      r,
    ) => html`<tr><td>${r.rank}</td><th scope="row"><a href="${districtPath(r.entry.stateSlug, r.entry.slug)}">${r.entry.name}</a></th>${showState ? html`<td>${r.entry.stateName}</td>` : html``}<td>${schoolYearLabel(r.entry.schoolYear)}</td><td class="num">${formatCents(r.cents)}</td></tr>
`,
  );
  return html`<div class="table-scroll" role="region" aria-label="${caption}" tabindex="0">
<table class="rank-table">
<caption>${caption}</caption>
<thead><tr><th scope="col">Rank</th><th scope="col">District</th>${showState ? html`<th scope="col">State</th>` : html``}<th scope="col">School year</th><th scope="col">Salary</th></tr></thead>
<tbody>
${body}</tbody>
</table>
</div>`;
}

function milestoneTabs(current: Milestone, stateSlug?: string): Html {
  const links = MILESTONES.map((m) =>
    m === current
      ? html`<a href="${rankingPath(m, stateSlug)}" aria-current="page">${MILESTONE_INFO[m].label}</a>`
      : html`<a href="${rankingPath(m, stateSlug)}">${MILESTONE_INFO[m].label}</a>`,
  );
  return html`<nav class="tabs" aria-label="Salary milestone">${links}</nav>`;
}

function stateList(states: StateLink[], milestone: Milestone): Html {
  if (states.length === 0) {
    return html``;
  }
  const items = states.map(
    (s) =>
      html`<li><a href="${rankingPath(milestone, s.slug)}">${s.name}</a> <span class="muted">${s.count.toLocaleString("en-US")}</span></li>`,
  );
  return html`<h2 id="by-state">By state</h2>
<ul class="chip-list">${items}</ul>`;
}

const NOTE = html`<p class="muted">Only districts whose latest published teacher schedule is an annual salary schedule are ranked. Districts with the same amount share a rank. Figures come from each district’s own document; check the district page for the source.</p>`;

export function rankingsOverviewPage(entries: SummaryEntry[]): Html {
  const crumbs = breadcrumbs([{ label: "Home", href: "/" }, { label: "Rankings" }]);
  const sections = MILESTONES.map((m) => {
    const info = MILESTONE_INFO[m];
    const rows = ranking(entries, m);
    if (rows.length === 0) {
      return html``;
    }
    return html`<section aria-labelledby="rank-${info.slug}">
<h2 id="rank-${info.slug}">${info.label}</h2>
<p>Ranked by ${info.definition}.</p>
${rankTable(rows.slice(0, OVERVIEW_LIMIT), `Top ${OVERVIEW_LIMIT} districts by ${info.label.toLowerCase()}`, true)}
<p><a href="${rankingPath(m)}">See the top ${NATIONAL_LIMIT} and rankings by state</a></p>
</section>`;
  });
  return html`${crumbs}
<h1>Teacher salary rankings</h1>
<p class="lede">School districts ranked at three points of the salary schedule: starting pay, mid-career pay with a master’s degree, and the top of the scale.</p>
${sections}
${NOTE}`;
}

export function rankingPage(
  entries: SummaryEntry[],
  milestone: Milestone,
  state: { slug: string; name: string } | null,
): Html {
  const info = MILESTONE_INFO[milestone];
  const scoped = state ? entries.filter((e) => e.stateSlug === state.slug) : entries;
  const rows = ranking(scoped, milestone);
  const crumbItems = [
    { label: "Home", href: "/" },
    { label: "Rankings", href: "/rankings" },
    state ? { label: info.label, href: rankingPath(milestone) } : { label: info.label },
  ];
  if (state) {
    crumbItems.push({ label: state.name });
  }
  const where = state ? state.name : "the United States";
  const shown = state ? rows : rows.slice(0, NATIONAL_LIMIT);
  const caption = state
    ? `${state.name} districts by ${info.label.toLowerCase()}`
    : `Top ${shown.length} districts by ${info.label.toLowerCase()}`;
  const count = rows.length.toLocaleString("en-US");
  const lede = state
    ? html`All ${count} ${state.name} districts on this site, ranked by ${info.definition}.`
    : html`The ${shown.length} highest-paying of ${count} districts on this site, ranked by ${info.definition}.`;
  const back = state
    ? html`<p><a href="/${state.slug}">All ${state.name} districts and schedules</a> · <a href="${rankingPath(milestone)}">National ranking</a></p>`
    : stateList(statesWithData(entries, milestone), milestone);
  return html`${breadcrumbs(crumbItems)}
<h1>${info.label}: teacher salary ranking, ${where}</h1>
<p class="lede">${lede}</p>
${milestoneTabs(milestone, state?.slug)}
${rows.length > 0 ? rankTable(shown, caption, !state) : html`<p>No districts have this figure yet.</p>`}
${back}
${NOTE}`;
}
