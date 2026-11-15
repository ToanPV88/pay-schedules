/** Tải một bảng lương dạng CSV (mở được bằng Excel, Google Sheets). */
import type { District, Schedule } from "@pay-schedules/db";
import { sourceLanding } from "./format";

/** Một ô CSV theo RFC 4180; chặn công thức khi mở bằng bảng tính (=, +, -, @ ở đầu). */
export function csvField(value: string): string {
  let text = value;
  if (/^[=+\-@\t\r]/.test(text)) {
    text = `'${text}`;
  }
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** 5000000 → "50000"; 2550 → "25.50": số thuần để bảng tính hiểu là số. */
export function csvAmount(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const rest = abs % 100;
  return `${sign}${Math.floor(abs / 100)}${rest === 0 ? "" : `.${String(rest).padStart(2, "0")}`}`;
}

/**
 * Hàng đầu: "Step" và nhãn lane; mỗi hàng sau: nhãn bậc và số tiền. Ô trống có ghi chú thì ghi
 * ghi chú; ô không có trong nguồn để trống. Dòng cuối ghi nguồn.
 */
export function scheduleCsv(district: District, schedule: Schedule): string {
  const lanes = schedule.lanes.length > 0 ? schedule.lanes.map((l) => l.labelRaw) : ["Salary"];
  const lines = [["Step", ...lanes].map(csvField).join(",")];
  for (const [i, step] of schedule.steps.entries()) {
    const cells = (schedule.cells[i] ?? []).map((cell) => {
      if (!cell) {
        return "";
      }
      return cell.amountCents === null ? csvField(cell.note ?? "") : csvAmount(cell.amountCents);
    });
    lines.push([csvField(step.labelRaw), ...cells].join(","));
  }
  lines.push("");
  const title = schedule.title ? `${schedule.title}, ` : "";
  lines.push(csvField(`${district.name}, ${title}${schedule.schoolYear}`));
  const source = sourceLanding(schedule.source.url)?.href ?? schedule.source.url;
  const page = schedule.source.page === null ? "" : `, page ${schedule.source.page}`;
  lines.push(csvField(`Source: ${source}${page}`));
  lines.push(csvField("Verify against the source document before relying on these figures."));
  return `${lines.join("\r\n")}\r\n`;
}

export function csvFileName(district: District, schedule: Schedule): string {
  return `${district.slug}-${schedule.schoolYear}-salary-schedule-${schedule.id}.csv`;
}

export function csvPath(scheduleId: number): string {
  return `/schedules/${scheduleId}.csv`;
}
