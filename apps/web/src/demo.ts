/**
 * Trang mẫu /demo với dữ liệu GIẢ LẬP (AGENTS.md §2.6), chỉ có ở bản xem trước. Dùng để đo
 * Lighthouse và xem giao diện trang học khu khi chưa có dữ liệu thật (Công đoạn 4).
 */
import type { District, Neighbor, Schedule, Summary, YearHistory } from "@pay-schedules/db";

const START_CENTS = 5_000_000;

/** Bốn cột của bậc thứ `step` (đếm từ 0): BA, BA+15, MA, MA+30. */
function row(step: number): number[] {
  const ba = START_CENTS + step * 150_000;
  return [ba, ba + 150_000, ba + 400_000, ba + 600_000];
}

const STEPS = 15;

export const DEMO_DISTRICT: District = {
  id: 0,
  ncesId: null,
  name: "Demo Valley Unified School District",
  slug: "demo",
  city: "Demoville",
  county: "Demo County",
  website: "https://demo-valley.example.invalid/",
  enrollment: null,
  active: true,
  state: { code: "ZZ", name: "Demo State", slug: "demo-state" },
};

export const DEMO_SCHEDULE: Schedule = {
  id: 1,
  districtId: 0,
  schoolYear: "2025-26",
  scheduleType: "teacher",
  title: "Certificated Salary Schedule",
  contractDays: 185,
  payBasis: "annual",
  hoursPerYear: null,
  status: "published",
  confidence: null,
  notes: "Placement on the schedule is determined by Human Resources at the time of hire.",
  source: {
    documentId: 0,
    url: "https://demo-valley.example.invalid/hr/salary-2025-26.pdf",
    fetchedAt: "2026-11-12T07:00:00Z",
    sha256: "a".repeat(64),
    page: 3,
    sheet: null,
  },
  lanes: [
    { id: 1, position: 1, labelRaw: "BA", laneNormalized: "BA" },
    { id: 2, position: 2, labelRaw: "BA+15", laneNormalized: "BA+15" },
    { id: 3, position: 3, labelRaw: "MA", laneNormalized: "MA" },
    { id: 4, position: 4, labelRaw: "MA+30", laneNormalized: "MA+30" },
  ],
  steps: Array.from({ length: STEPS }, (_, i) => ({
    id: i + 1,
    position: i + 1,
    labelRaw: String(i + 1),
    yearsExperience: i,
  })),
  cells: Array.from({ length: STEPS }, (_, i) =>
    row(i).map((amount, j) =>
      i === 0 && j === 3
        ? { amountCents: null, note: "No initial placement in this lane" }
        : { amountCents: amount, note: null },
    ),
  ),
  stipends: [
    { name: "Doctorate stipend", amountCents: 250_000, amountRaw: "$2,500", condition: null },
    {
      name: "Department chair",
      amountCents: null,
      amountRaw: "2% of base salary",
      condition: "Per assignment",
    },
  ],
};

export const DEMO_HISTORY: YearHistory[] = [
  { schoolYear: "2025-26", schedules: 1, minCents: 5_000_000, maxCents: 7_700_000 },
];

export const DEMO_NEIGHBORS: Neighbor[] = [
  ["Demo Ridge Public Schools", "demo-ridge", 4.2, 4_900_000, 6_500_000, 7_400_000],
  ["Demo Lake School District", "demo-lake", 9.8, 5_200_000, 6_900_000, 8_100_000],
  ["Demo Hills Unified School District", "demo-hills", 15.1, 4_750_000, null, 7_050_000],
].map(([name, slug, distanceKm, start, ma10, max], index) => ({
  id: index + 1,
  name: name as string,
  slug: slug as string,
  stateSlug: "demo-state",
  distanceKm: distanceKm as number,
  summary: {
    schoolYear: "2025-26",
    startBaCents: start as number,
    maStep10Cents: ma10 as number | null,
    maxSalaryCents: max as number,
  },
}));

export const DEMO_SUMMARY: Summary = {
  schoolYear: "2025-26",
  startBaCents: 5_000_000,
  maStep10Cents: 6_750_000,
  maxSalaryCents: 7_700_000,
};
