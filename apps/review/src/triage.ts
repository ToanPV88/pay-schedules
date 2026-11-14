// Tự phân loại hàng chờ xem tay (DECISIONS.md D-034).
// Chủ dự án không duyệt tay hết được, nên các nhóm lý do an toàn được xử lý tự động:
// - Bảng bắt đầu ở bậc cao (step_start) mà hai bộ đọc không lệch nhau: publish như nguồn.
// - Bảng năm cũ (pdf_checks "đã cũ"): còn trong MAX_PUBLISH_AGE năm thì publish như nguồn (trang
//   web ghi rõ đây là bảng mới nhất tìm thấy); cũ hơn thì loại, học khu được tìm lại sau 90 ngày.
// Bảng có bất kỳ lý do nào khác (hai lần trích lệch nhau, lương đổi chiều, nhãn lane lạ...) để
// người xem. Lý do được nhận theo mã "[code]" đầu dòng và câu chữ của kiểm tra trong pipeline.

/** Bảng năm học bắt đầu từ (năm học hiện tại − số này) trở về sau thì publish như nguồn. */
export const MAX_PUBLISH_AGE = 3;
export const TRIAGE_PUBLISHED = "as reported: auto-triage (D-034)";
export const TRIAGE_REJECTED = "rejected: auto-triage (D-034)";

const CODE = /^\[([a-z_]+)\]/;
const OLD_YEAR = /^\[school_year\] Bảng năm (\d{4})-\d{2} đã cũ/;
/** Bảng một cột mà cột chỉ có nhãn "salary" (D-045): số liệu không đổi, chỉ thiếu tên cột. */
export const SINGLE_SALARY_LANE = "[lane_label] Nhãn lane thiếu tên: 'salary'";

export type Decision = { kind: "publish" } | { kind: "reject"; reason: string } | { kind: "keep" };

/** Năm bắt đầu của năm học hiện tại: từ tháng 7 là năm học mới (như pipeline). */
export function currentSchoolYearStart(today: Date): number {
  return today.getUTCMonth() >= 6 ? today.getUTCFullYear() : today.getUTCFullYear() - 1;
}

export function triage(reasons: string[], today: Date): Decision {
  if (reasons.length === 0) return { kind: "keep" };
  let oldStart: number | null = null;
  for (const reason of reasons) {
    const code = CODE.exec(reason)?.[1];
    if (code === "step_start" || reason === SINGLE_SALARY_LANE) continue;
    const old = OLD_YEAR.exec(reason);
    if (code === "school_year" && old) {
      oldStart = Number(old[1]);
      continue;
    }
    return { kind: "keep" };
  }
  if (oldStart !== null && oldStart < currentSchoolYearStart(today) - MAX_PUBLISH_AGE) {
    return {
      kind: "reject",
      reason: `chỉ tìm thấy bảng năm ${oldStart}-${String(oldStart + 1).slice(2)}, quá cũ`,
    };
  }
  return { kind: "publish" };
}
