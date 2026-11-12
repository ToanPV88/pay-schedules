/** Logic của trang /compare: so tối đa bốn học khu ở cùng bậc và cùng cột bằng cấp. */
import type { District, Schedule, Summary } from "@pay-schedules/db";

export const MAX_COMPARE = 4;

export interface DistrictKey {
  stateSlug: string;
  districtSlug: string;
}

const KEY = /^([a-z][a-z0-9-]{0,63})\/([a-z0-9][a-z0-9-]{0,127})$/;

export function parseDistrictKey(raw: string): DistrictKey | null {
  const match = KEY.exec(raw.trim());
  const stateSlug = match?.[1];
  const districtSlug = match?.[2];
  return stateSlug && districtSlug ? { stateSlug, districtSlug } : null;
}

export function keyOf(key: DistrictKey): string {
  return `${key.stateSlug}/${key.districtSlug}`;
}

/** Đọc tham số `d=bang/hoc-khu,bang/hoc-khu`: bỏ mục sai dạng và mục trùng, giữ tối đa bốn. */
export function parseDistrictKeys(raw: string | undefined): DistrictKey[] {
  const keys: DistrictKey[] = [];
  const seen = new Set<string>();
  for (const part of (raw ?? "").split(",")) {
    const key = parseDistrictKey(part);
    if (!key || seen.has(keyOf(key))) {
      continue;
    }
    seen.add(keyOf(key));
    keys.push(key);
    if (keys.length === MAX_COMPARE) {
      break;
    }
  }
  return keys;
}

export interface CompareEntry {
  district: District;
  /** Bảng lương giáo viên published của năm mới nhất; null khi học khu chưa có bảng. */
  schedule: Schedule | null;
  summary: Summary | null;
}

/** Các cột bằng cấp đã chuẩn hóa có trong ít nhất một bảng, theo thứ tự gặp. */
export function laneOptions(entries: CompareEntry[]): string[] {
  const options: string[] = [];
  for (const entry of entries) {
    for (const lane of entry.schedule?.lanes ?? []) {
      if (lane.laneNormalized && !options.includes(lane.laneNormalized)) {
        options.push(lane.laneNormalized);
      }
    }
  }
  return options;
}

export function maxSteps(entries: CompareEntry[]): number {
  let max = 0;
  for (const entry of entries) {
    max = Math.max(max, entry.schedule?.steps.length ?? 0);
  }
  return max;
}

export interface CompareCell {
  /** Nhãn gốc của cột và bậc đã khớp, để người đọc thấy đang so cái gì. */
  laneLabel: string | null;
  stepLabel: string | null;
  amountCents: number | null;
  /** Lý do không có số (tiếng Anh, hiện cho người dùng). */
  reason: string | null;
}

function blank(reason: string): CompareCell {
  return { laneLabel: null, stepLabel: null, amountCents: null, reason };
}

/**
 * Ô của một bảng tại cột chuẩn hóa `lane` và bậc thứ `stepPosition` (đếm từ 1).
 * `lane` là null khi không bảng nào có cột bằng cấp: khi đó mỗi bảng dùng cột duy nhất của nó.
 */
export function compareCell(
  schedule: Schedule | null,
  lane: string | null,
  stepPosition: number,
): CompareCell {
  if (!schedule) {
    return blank("No published schedule");
  }
  if (schedule.payBasis !== "annual") {
    return blank("Schedule is not annual");
  }
  let laneIndex = 0;
  let laneLabel: string | null = null;
  if (schedule.lanes.length > 0) {
    laneIndex = schedule.lanes.findIndex((l) => lane !== null && l.laneNormalized === lane);
    if (laneIndex < 0) {
      return blank(lane === null ? "Choose a lane" : `No ${lane} lane on this schedule`);
    }
    laneLabel = schedule.lanes[laneIndex]?.labelRaw ?? null;
  }
  const step = schedule.steps[stepPosition - 1];
  if (!step) {
    return blank(`Schedule has ${schedule.steps.length} steps`);
  }
  const cell = schedule.cells[stepPosition - 1]?.[laneIndex] ?? null;
  const amount = cell?.amountCents ?? null;
  const missing = cell?.note ?? "No amount listed";
  return {
    laneLabel,
    stepLabel: step.labelRaw,
    amountCents: amount,
    reason: amount === null ? missing : null,
  };
}
