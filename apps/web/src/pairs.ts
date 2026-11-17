/**
 * Trang so sánh hai học khu có URL riêng (DECISIONS.md D-118): /compare/<a>-vs-<b>, mỗi bên là
 * "<mã bang>-<slug học khu>", vd. /compare/tx-houston-isd-vs-tx-dallas-isd. Thứ tự chuẩn: học khu
 * nhiều học sinh hơn đứng trước. Chỉ "cặp nổi bật" được index; cặp khác vẫn xem được (noindex).
 */
import type { SummaryEntry } from "@pay-schedules/db";

export interface PairSide {
  stateCode: string;
  slug: string;
}

/** Mọi cặp trong số học khu lớn nhất này. */
export const TOP_ALL_PAIRS = 12;
/** Học khu xếp tiếp theo (theo số học sinh) đến hạng này ghép với học khu lớn nhất cùng bang. */
export const TOP_STATE_PAIRS = 60;

const SIDE = /^([a-z]{2})-([a-z0-9]+(?:-[a-z0-9]+)*)$/;

export function sideSlug(entry: { stateCode: string; slug: string }): string {
  return `${entry.stateCode.toLowerCase()}-${entry.slug}`;
}

export function pairPath(
  a: { stateCode: string; slug: string },
  b: { stateCode: string; slug: string },
): string {
  return `/compare/${sideSlug(a)}-vs-${sideSlug(b)}`;
}

/** Tách "<a>-vs-<b>"; null khi sai dạng, mơ hồ (nhiều "-vs-") hay hai bên trùng nhau. */
export function parsePair(raw: string): [PairSide, PairSide] | null {
  const parts = raw.split("-vs-");
  if (parts.length !== 2) {
    return null;
  }
  const sides = parts.map((p) => SIDE.exec(p));
  const [ma, mb] = sides;
  if (!ma || !mb || !ma[1] || !ma[2] || !mb[1] || !mb[2]) {
    return null;
  }
  const a = { stateCode: ma[1].toUpperCase(), slug: ma[2] };
  const b = { stateCode: mb[1].toUpperCase(), slug: mb[2] };
  if (a.stateCode === b.stateCode && a.slug === b.slug) {
    return null;
  }
  return [a, b];
}

export function findEntry(entries: SummaryEntry[], side: PairSide): SummaryEntry | null {
  return entries.find((e) => e.stateCode === side.stateCode && e.slug === side.slug) ?? null;
}

/** true khi `a` đứng trước `b` theo thứ tự chuẩn (nhiều học sinh hơn, rồi theo tên). */
export function isCanonicalOrder(a: SummaryEntry, b: SummaryEntry): boolean {
  const ea = a.enrollment ?? -1;
  const eb = b.enrollment ?? -1;
  if (ea !== eb) {
    return ea > eb;
  }
  return a.name.localeCompare(b.name) <= 0;
}

function eligible(entries: SummaryEntry[]): SummaryEntry[] {
  return entries
    .filter((e) => e.startBaCents !== null && e.maxSalaryCents !== null && e.enrollment !== null)
    .sort((a, b) => (b.enrollment ?? 0) - (a.enrollment ?? 0) || a.name.localeCompare(b.name));
}

/**
 * Cặp nổi bật (được index, có liên kết): mọi cặp trong TOP_ALL_PAIRS học khu lớn nhất có đủ số liệu,
 * và mỗi học khu tiếp theo đến hạng TOP_STATE_PAIRS ghép với học khu lớn nhất cùng bang.
 */
export function featuredPairs(entries: SummaryEntry[]): [SummaryEntry, SummaryEntry][] {
  const list = eligible(entries);
  const pairs: [SummaryEntry, SummaryEntry][] = [];
  const top = list.slice(0, TOP_ALL_PAIRS);
  // Theo khoảng cách hạng: (1,2), (2,3)… rồi (1,3), (2,4)…, để vài cặp đầu không cùng một học khu.
  for (let gap = 1; gap < top.length; gap++) {
    for (let i = 0; i + gap < top.length; i++) {
      const a = top[i];
      const b = top[i + gap];
      if (a && b) {
        pairs.push([a, b]);
      }
    }
  }
  const largestInState = new Map<string, SummaryEntry>();
  for (const e of list) {
    if (!largestInState.has(e.stateCode)) {
      largestInState.set(e.stateCode, e);
    }
  }
  for (const e of list.slice(TOP_ALL_PAIRS, TOP_STATE_PAIRS)) {
    const big = largestInState.get(e.stateCode);
    if (big && big.id !== e.id) {
      pairs.push([big, e]);
    }
  }
  return pairs;
}

export function isFeatured(
  pairs: [SummaryEntry, SummaryEntry][],
  a: SummaryEntry,
  b: SummaryEntry,
): boolean {
  return pairs.some(([x, y]) => x.id === a.id && y.id === b.id);
}
