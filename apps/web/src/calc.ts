/**
 * Phép tính của máy tính lương. Chỉ đọc số có trong bảng: không nội suy, không ước lượng
 * (PLAN, nguyên tắc 2). `public/site.js` lặp lại đúng các phép tính này để cập nhật tại chỗ.
 */
import type { Schedule } from "@pay-schedules/db";

export interface Range {
  minCents: number;
  maxCents: number;
}

/** Ô thấp nhất và cao nhất của bảng; null khi bảng không có số nào. */
export function scheduleRange(schedule: Schedule): Range | null {
  let min: number | null = null;
  let max: number | null = null;
  for (const row of schedule.cells) {
    for (const cell of row) {
      const amount = cell?.amountCents ?? null;
      if (amount === null) {
        continue;
      }
      min = min === null ? amount : Math.min(min, amount);
      max = max === null ? amount : Math.max(max, amount);
    }
  }
  return min === null || max === null ? null : { minCents: min, maxCents: max };
}

export interface Calculation {
  laneIndex: number;
  stepIndex: number;
  amountCents: number | null;
  /** Ghi chú của ô trống, nguyên văn từ tài liệu. */
  note: string | null;
  /** Chỉ có khi bảng tính theo năm, tài liệu ghi số ngày hợp đồng và ô có số. */
  perDayCents: number | null;
  /** Chênh lệch với bậc kế tiếp cùng cột; null khi là bậc cuối hoặc thiếu số. */
  nextStepRaiseCents: number | null;
  isTopStep: boolean;
  /** Bảng tính theo năm và ô có số: lương chia đều 12 tháng. */
  perMonthCents: number | null;
  /** Bậc cuối của cột có số (đỉnh của lane) và số tiền ở đó; null khi cột không có số nào. */
  topStepIndex: number | null;
  topCents: number | null;
}

function amountAt(schedule: Schedule, stepIndex: number, laneIndex: number): number | null {
  return schedule.cells[stepIndex]?.[laneIndex]?.amountCents ?? null;
}

export function laneCount(schedule: Schedule): number {
  return Math.max(schedule.lanes.length, 1);
}

/** Bậc cuối cùng của một cột có số; null khi cả cột trống. */
export function laneTop(
  schedule: Schedule,
  laneIndex: number,
): { stepIndex: number; cents: number } | null {
  for (let i = schedule.steps.length - 1; i >= 0; i--) {
    const amount = amountAt(schedule, i, laneIndex);
    if (amount !== null) {
      return { stepIndex: i, cents: amount };
    }
  }
  return null;
}

/** Kết quả cho một ô; null khi chỉ số nằm ngoài bảng. */
export function calculate(
  schedule: Schedule,
  laneIndex: number,
  stepIndex: number,
): Calculation | null {
  if (stepIndex < 0 || stepIndex >= schedule.steps.length) {
    return null;
  }
  if (laneIndex < 0 || laneIndex >= laneCount(schedule)) {
    return null;
  }
  const cell = schedule.cells[stepIndex]?.[laneIndex] ?? null;
  const amount = cell?.amountCents ?? null;
  const isTopStep = stepIndex === schedule.steps.length - 1;
  const next = isTopStep ? null : amountAt(schedule, stepIndex + 1, laneIndex);
  const days = schedule.contractDays;
  const perDay =
    amount !== null && days !== null && schedule.payBasis === "annual"
      ? Math.round(amount / days)
      : null;
  const top = laneTop(schedule, laneIndex);
  return {
    laneIndex,
    stepIndex,
    amountCents: amount,
    note: cell?.note ?? null,
    perDayCents: perDay,
    nextStepRaiseCents: amount !== null && next !== null ? next - amount : null,
    isTopStep,
    perMonthCents:
      amount !== null && schedule.payBasis === "annual" ? Math.round(amount / 12) : null,
    topStepIndex: top?.stepIndex ?? null,
    topCents: top?.cents ?? null,
  };
}

/** Đổi tham số vị trí (đếm từ 1) thành chỉ số; giá trị lạ thì về 0. */
export function positionToIndex(value: string | undefined, count: number): number {
  if (value === undefined || !/^[0-9]{1,4}$/.test(value)) {
    return 0;
  }
  const position = Number(value);
  return position >= 1 && position <= count ? position - 1 : 0;
}
