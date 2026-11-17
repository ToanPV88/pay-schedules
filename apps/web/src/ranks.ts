/**
 * Xếp hạng học khu theo ba mốc lương (BA bậc 1, MA bậc 10, mức tối đa), toàn quốc và trong bang.
 * Nguồn là mốc của năm mới nhất mỗi học khu (`listLatestSummaries`), giữ trong bộ nhớ isolate 10
 * phút để mỗi lần dựng trang không phải đọc lại mọi học khu từ D1.
 */
import { listLatestSummaries, type SummaryEntry } from "@pay-schedules/db";

export type Milestone = "start" | "ma10" | "max";

export const MILESTONES: readonly Milestone[] = ["start", "ma10", "max"];

export function milestoneValue(entry: SummaryEntry, milestone: Milestone): number | null {
  if (milestone === "start") {
    return entry.startBaCents;
  }
  return milestone === "ma10" ? entry.maStep10Cents : entry.maxSalaryCents;
}

const TTL_MS = 10 * 60 * 1000;
let cached: { at: number; value: Promise<SummaryEntry[]> } | null = null;

export function latestSummaries(db: D1Database, now = Date.now()): Promise<SummaryEntry[]> {
  if (cached && now - cached.at < TTL_MS) {
    return cached.value;
  }
  const value = listLatestSummaries(db);
  cached = { at: now, value };
  value.catch(() => {
    cached = null;
  });
  return value;
}

export function resetSummaryCache(): void {
  cached = null;
}

export interface Rank {
  /** Hạng, 1 là cao nhất; học khu bằng nhau cùng hạng. */
  rank: number;
  total: number;
}

/** Hạng của học khu `id` ở một mốc, trong các dòng đã lọc; null khi học khu không có số ở mốc đó. */
export function rankOf(entries: SummaryEntry[], id: number, milestone: Milestone): Rank | null {
  const own = entries.find((e) => e.id === id);
  const value = own ? milestoneValue(own, milestone) : null;
  if (value === null) {
    return null;
  }
  let higher = 0;
  let total = 0;
  for (const entry of entries) {
    const v = milestoneValue(entry, milestone);
    if (v === null) {
      continue;
    }
    total += 1;
    if (v > value) {
      higher += 1;
    }
  }
  return { rank: higher + 1, total };
}

/** Các học khu có số ở mốc, xếp từ cao xuống thấp, kèm hạng (bằng nhau cùng hạng). */
export function ranking(
  entries: SummaryEntry[],
  milestone: Milestone,
): { entry: SummaryEntry; cents: number; rank: number }[] {
  const rows = entries
    .map((entry) => ({ entry, cents: milestoneValue(entry, milestone) }))
    .filter((r): r is { entry: SummaryEntry; cents: number } => r.cents !== null)
    .sort((a, b) => b.cents - a.cents || a.entry.name.localeCompare(b.entry.name));
  let rank = 0;
  let previous: number | null = null;
  return rows.map((row, i) => {
    if (row.cents !== previous) {
      rank = i + 1;
      previous = row.cents;
    }
    return { ...row, rank };
  });
}

/** 1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st… */
export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) {
    return `${n.toLocaleString("en-US")}th`;
  }
  const suffix = ["th", "st", "nd", "rd"][n % 10] ?? "th";
  return `${n.toLocaleString("en-US")}${n % 10 > 3 ? "th" : suffix}`;
}

/** "top 7%" khi hạng nằm trong nửa trên; null khi quá ít học khu để nói phần trăm. */
export function topPercent(rank: Rank): string | null {
  if (rank.total < 20) {
    return null;
  }
  // Tính theo số nguyên để tránh sai số dấu phẩy động (7/100*100 = 7.000…01).
  const pct = Math.max(1, Math.ceil((rank.rank * 100) / rank.total - 1e-9));
  return pct <= 50 ? `top ${pct}%` : null;
}
