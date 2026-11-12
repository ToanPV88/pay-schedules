import type { PayBasis, Step } from "@pay-schedules/db";

/** 5000000 → "$50,000"; 2550 → "$25.50". Không làm tròn: số trong tài liệu thế nào hiện thế ấy. */
export function formatCents(cents: number): string {
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100);
  const rest = abs % 100;
  const whole = String(dollars).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fraction = rest === 0 ? "" : `.${String(rest).padStart(2, "0")}`;
  const sign = cents < 0 ? "-" : "";
  return `${sign}$${whole}${fraction}`;
}

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "2026-11-12T07:00:00Z" → "November 12, 2026" (ngày theo UTC). Chuỗi lạ thì trả nguyên văn. */
export function formatDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) {
    return iso;
  }
  const [, year, month, day] = match;
  const name = MONTHS[Number(month) - 1];
  if (!name) {
    return iso;
  }
  return `${name} ${Number(day)}, ${year}`;
}

const SCHOOL_YEAR = /^[0-9]{4}-[0-9]{2}$/;

export function isSchoolYear(value: string): boolean {
  return SCHOOL_YEAR.test(value);
}

/** "2025-26" → "2025–26". */
export function schoolYearLabel(year: string): string {
  return year.replace("-", "–");
}

const BASIS_NOUNS: Record<PayBasis, string> = {
  annual: "per year",
  monthly: "per month",
  hourly: "per hour",
  daily: "per day",
};

export function payBasisNoun(basis: PayBasis): string {
  return BASIS_NOUNS[basis];
}

/** Chỉ nhận http và https, để dữ liệu từ D1 không chèn được `javascript:` vào href. */
export function safeHttpUrl(value: string | null): string | null {
  if (!value) {
    return null;
  }
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Nhãn bậc trong ô chọn: nhãn gốc, thêm chữ "Step" khi nhãn chỉ là số. */
export function stepLabel(step: Step): string {
  return /^[0-9]+$/.test(step.labelRaw) ? `Step ${step.labelRaw}` : step.labelRaw;
}

export function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

export function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;
}
