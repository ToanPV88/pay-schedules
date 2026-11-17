/**
 * Phân tích một bảng lương: mỗi cột (lane) bắt đầu ở đâu, lên tới đỉnh sau bao nhiêu bậc, tăng
 * bao nhiêu phần trăm, bước tăng lớn nhất. Chỉ tính từ các ô có số; không suy đoán ô trống.
 */
import type { Schedule } from "@pay-schedules/db";
import { laneCount } from "./calc";

export interface LaneGrowth {
  laneIndex: number;
  /** Bậc đầu tiên và cuối cùng có số trong cột. */
  startStepIndex: number;
  startCents: number;
  topStepIndex: number;
  topCents: number;
  /** Số lần lên bậc từ bậc đầu tới đỉnh (theo hàng của bảng). */
  stepMoves: number;
  /** Số năm kinh nghiệm từ bậc đầu tới đỉnh khi tài liệu ghi năm ở cả hai bậc. */
  years: number | null;
  /** Tăng từ bậc đầu tới đỉnh, phần trăm (làm tròn 1 chữ số). */
  growthPct: number;
  /** Bước tăng lớn nhất giữa hai bậc liền nhau có số; null khi cột chỉ có một ô. */
  largestRaise: { fromStepIndex: number; toStepIndex: number; cents: number } | null;
}

export function laneGrowth(schedule: Schedule, laneIndex: number): LaneGrowth | null {
  const amounts: { stepIndex: number; cents: number }[] = [];
  for (let i = 0; i < schedule.steps.length; i++) {
    const cents = schedule.cells[i]?.[laneIndex]?.amountCents ?? null;
    if (cents !== null) {
      amounts.push({ stepIndex: i, cents });
    }
  }
  const first = amounts[0];
  const last = amounts[amounts.length - 1];
  if (!first || !last || first.cents <= 0) {
    return null;
  }
  let largest: LaneGrowth["largestRaise"] = null;
  for (let k = 1; k < amounts.length; k++) {
    const prev = amounts[k - 1];
    const cur = amounts[k];
    if (!prev || !cur) {
      continue;
    }
    const raise = cur.cents - prev.cents;
    if (raise > 0 && (largest === null || raise > largest.cents)) {
      largest = { fromStepIndex: prev.stepIndex, toStepIndex: cur.stepIndex, cents: raise };
    }
  }
  const startYears = schedule.steps[first.stepIndex]?.yearsExperience ?? null;
  const topYears = schedule.steps[last.stepIndex]?.yearsExperience ?? null;
  return {
    laneIndex,
    startStepIndex: first.stepIndex,
    startCents: first.cents,
    topStepIndex: last.stepIndex,
    topCents: last.cents,
    stepMoves: last.stepIndex - first.stepIndex,
    years:
      startYears !== null && topYears !== null && topYears > startYears
        ? topYears - startYears
        : null,
    growthPct: Math.round(((last.cents - first.cents) / first.cents) * 1000) / 10,
    largestRaise: largest,
  };
}

/** Phân tích mọi cột có số; rỗng khi bảng chỉ có một bậc (không có gì để "lên"). */
export function scheduleGrowth(schedule: Schedule): LaneGrowth[] {
  if (schedule.steps.length < 2) {
    return [];
  }
  const lanes: LaneGrowth[] = [];
  for (let l = 0; l < laneCount(schedule); l++) {
    const growth = laneGrowth(schedule, l);
    if (growth) {
      lanes.push(growth);
    }
  }
  return lanes;
}
