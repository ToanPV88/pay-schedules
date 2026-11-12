/**
 * Ba bảng lương mẫu nhập tay cho nghiệm thu Công đoạn 2. Dữ liệu GIẢ LẬP (AGENTS.md §2.6):
 * tên học khu chứa "Test", URL thuộc example.invalid, số tiền tự đặt.
 */

/** Một ô trong ma trận mẫu: số tiền (cents) hoặc ô trống có ghi chú. */
export type FixtureCell = number | { empty: string };

export interface FixtureSchedule {
  key: string;
  district: { name: string; slug: string; city: string; county: string };
  document: { url: string; sha256: string; page: number };
  schoolYear: string;
  title: string;
  contractDays: number | null;
  lanes: { labelRaw: string; normalized: string | null }[];
  steps: { labelRaw: string; years: number | null }[];
  /** cells[i][j] cho bậc i, cột j; bảng không có lane thì mỗi hàng một phần tử. */
  cells: FixtureCell[][];
  stipends: { name: string; amountCents: number | null; amountRaw: string | null }[];
}

const sha = (c: string) => c.repeat(64);

/** 1. Bảng chuẩn: 5 bậc × 4 lane, nhãn lane quen thuộc. */
export const standard: FixtureSchedule = {
  key: "standard",
  district: {
    name: "Test Valley Unified School District",
    slug: "test-valley-unified",
    city: "Testville",
    county: "Test County",
  },
  document: {
    url: "https://test-valley.example.invalid/hr/salary-2025-26.pdf",
    sha256: sha("a"),
    page: 3,
  },
  schoolYear: "2025-26",
  title: "Certificated Salary Schedule",
  contractDays: 185,
  lanes: [
    { labelRaw: "BA", normalized: "BA" },
    { labelRaw: "BA+15", normalized: "BA+15" },
    { labelRaw: "MA", normalized: "MA" },
    { labelRaw: "MA+30", normalized: "MA+30" },
  ],
  steps: [1, 2, 3, 4, 5].map((n) => ({ labelRaw: String(n), years: n - 1 })),
  cells: [
    [5_000_000, 5_150_000, 5_400_000, 5_600_000],
    [5_150_000, 5_300_000, 5_550_000, 5_750_000],
    [5_300_000, 5_450_000, 5_700_000, 5_900_000],
    [5_450_000, 5_600_000, 5_850_000, 6_050_000],
    [5_600_000, 5_750_000, 6_000_000, 6_200_000],
  ],
  stipends: [{ name: "Doctorate stipend", amountCents: 250_000, amountRaw: "$2,500" }],
};

/** 2. Nhãn lane lạ, có lane chưa chuẩn hóa được và một ô trống có ghi chú. */
export const oddLanes: FixtureSchedule = {
  key: "odd-lanes",
  district: {
    name: "Cañon Test School District",
    slug: "canon-test",
    city: "Cañon Test City",
    county: "Fremont Test County",
  },
  document: {
    url: "https://canon-test.example.invalid/docs/negotiated-agreement.pdf",
    sha256: sha("b"),
    page: 41,
  },
  schoolYear: "2024-25",
  title: "Appendix A – Teacher Salary Schedule",
  contractDays: null,
  lanes: [
    { labelRaw: "Class I", normalized: null },
    { labelRaw: "Class II (BA+30)", normalized: "BA+30" },
    { labelRaw: "Class III (MA)", normalized: "MA" },
    { labelRaw: "Column D – Doctorate", normalized: "PhD" },
  ],
  steps: [
    { labelRaw: "Step A", years: null },
    { labelRaw: "Step B", years: null },
    { labelRaw: "Step C", years: null },
  ],
  cells: [
    [4_800_000, 4_950_000, 5_200_000, { empty: "No placement on this step for Column D" }],
    [4_900_000, 5_050_000, 5_300_000, 5_600_000],
    [5_000_000, 5_150_000, 5_400_000, 5_700_000],
  ],
  stipends: [{ name: "Department chair", amountCents: null, amountRaw: "2% of base salary" }],
};

/** 3. Chỉ có bậc, không có lane. */
export const stepsOnly: FixtureSchedule = {
  key: "steps-only",
  district: {
    name: "Test Ridge Public Schools",
    slug: "test-ridge",
    city: "Ridge Test",
    county: "Test County",
  },
  document: {
    url: "https://test-ridge.example.invalid/salary.pdf",
    sha256: sha("c"),
    page: 1,
  },
  schoolYear: "2025-26",
  title: "",
  contractDays: 180,
  lanes: [],
  steps: Array.from({ length: 8 }, (_, i) => ({ labelRaw: `Step ${i + 1}`, years: i })),
  cells: Array.from({ length: 8 }, (_, i) => [4_500_000 + i * 120_000]),
  stipends: [],
};

export const FIXTURES = [standard, oddLanes, stepsOnly];
