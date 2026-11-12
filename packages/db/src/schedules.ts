/**
 * Đọc một bảng lương từ D1 thành ma trận bậc × bằng cấp (schema: migrations/0002_schema.sql).
 * Hàm chỉ đọc; không đổi dữ liệu.
 */

export type ScheduleStatus = "draft" | "validated" | "published" | "superseded";
export type PayBasis = "annual" | "monthly" | "hourly" | "daily";

export interface Lane {
  id: number;
  position: number;
  labelRaw: string;
  laneNormalized: string | null;
}

export interface Step {
  id: number;
  position: number;
  labelRaw: string;
  yearsExperience: number | null;
}

/** Một ô. `amountCents` null nghĩa là ô trống trong tài liệu; khi đó `note` luôn có giá trị. */
export interface Cell {
  amountCents: number | null;
  note: string | null;
}

export interface Stipend {
  name: string;
  amountCents: number | null;
  amountRaw: string | null;
  condition: string | null;
}

export interface Schedule {
  id: number;
  districtId: number;
  schoolYear: string;
  scheduleType: string;
  title: string;
  contractDays: number | null;
  payBasis: PayBasis;
  hoursPerYear: number | null;
  status: ScheduleStatus;
  confidence: number | null;
  notes: string | null;
  source: {
    documentId: number;
    url: string;
    fetchedAt: string;
    sha256: string;
    page: number | null;
    sheet: string | null;
  };
  /** Theo thứ tự `position`. Rỗng khi bảng chỉ có bậc. */
  lanes: Lane[];
  /** Theo thứ tự `position`. */
  steps: Step[];
  /**
   * `cells[i][j]`: bậc `steps[i]`, cột `lanes[j]`. Bảng chỉ có bậc thì mỗi hàng có đúng một phần tử.
   * Vị trí không có dòng trong bảng `cells` là `null` (khác với ô trống có ghi chú).
   */
  cells: (Cell | null)[][];
  stipends: Stipend[];
}

interface ScheduleRow {
  id: number;
  district_id: number;
  school_year: string;
  schedule_type: string;
  title: string;
  contract_days: number | null;
  pay_basis: PayBasis;
  hours_per_year: number | null;
  status: ScheduleStatus;
  confidence: number | null;
  notes: string | null;
  source_document_id: number;
  source_page: number | null;
  source_sheet: string | null;
  url: string;
  fetched_at: string;
  sha256: string;
}

interface LaneRow {
  id: number;
  position: number;
  label_raw: string;
  lane_normalized: string | null;
}

interface StepRow {
  id: number;
  position: number;
  label_raw: string;
  years_experience: number | null;
}

interface CellRow {
  step_id: number;
  lane_id: number | null;
  amount_cents: number | null;
  note: string | null;
}

interface StipendRow {
  name: string;
  amount_cents: number | null;
  amount_raw: string | null;
  condition: string | null;
}

function rows<T>(result: D1Result | undefined): T[] {
  return (result?.results ?? []) as T[];
}

export async function getSchedule(db: D1Database, scheduleId: number): Promise<Schedule | null> {
  const [head, lanes, steps, cells, stipends] = await db.batch([
    db
      .prepare(
        `SELECT s.id, s.district_id, s.school_year, s.schedule_type, s.title, s.contract_days,
                s.pay_basis, s.hours_per_year, s.status, s.confidence, s.notes,
                s.source_document_id, s.source_page, s.source_sheet,
                d.url, d.fetched_at, d.sha256
           FROM schedules s JOIN source_documents d ON d.id = s.source_document_id
          WHERE s.id = ?`,
      )
      .bind(scheduleId),
    db
      .prepare(
        "SELECT id, position, label_raw, lane_normalized FROM lanes WHERE schedule_id = ? ORDER BY position",
      )
      .bind(scheduleId),
    db
      .prepare(
        "SELECT id, position, label_raw, years_experience FROM steps WHERE schedule_id = ? ORDER BY position",
      )
      .bind(scheduleId),
    db
      .prepare("SELECT step_id, lane_id, amount_cents, note FROM cells WHERE schedule_id = ?")
      .bind(scheduleId),
    db
      .prepare(
        "SELECT name, amount_cents, amount_raw, condition FROM stipends WHERE schedule_id = ? ORDER BY id",
      )
      .bind(scheduleId),
  ]);

  const row = rows<ScheduleRow>(head)[0];
  if (!row) {
    return null;
  }

  const laneList: Lane[] = rows<LaneRow>(lanes).map((l) => ({
    id: l.id,
    position: l.position,
    labelRaw: l.label_raw,
    laneNormalized: l.lane_normalized,
  }));
  const stepList: Step[] = rows<StepRow>(steps).map((s) => ({
    id: s.id,
    position: s.position,
    labelRaw: s.label_raw,
    yearsExperience: s.years_experience,
  }));

  const laneIndex = new Map(laneList.map((l, j) => [l.id, j]));
  const stepIndex = new Map(stepList.map((s, i) => [s.id, i]));
  const width = Math.max(laneList.length, 1);
  const matrix: (Cell | null)[][] = stepList.map(() => Array<Cell | null>(width).fill(null));

  for (const c of rows<CellRow>(cells)) {
    const i = stepIndex.get(c.step_id);
    const j = c.lane_id === null ? 0 : laneIndex.get(c.lane_id);
    if (i === undefined || j === undefined) {
      // Khóa ngoại kép trong schema làm trường hợp này không xảy ra; báo lỗi thay vì bỏ qua ô.
      throw new Error(`Ô của bảng ${scheduleId} trỏ tới bậc hoặc cột không thuộc bảng`);
    }
    const rowCells = matrix[i];
    if (rowCells) {
      rowCells[j] = { amountCents: c.amount_cents, note: c.note };
    }
  }

  return {
    id: row.id,
    districtId: row.district_id,
    schoolYear: row.school_year,
    scheduleType: row.schedule_type,
    title: row.title,
    contractDays: row.contract_days,
    payBasis: row.pay_basis,
    hoursPerYear: row.hours_per_year,
    status: row.status,
    confidence: row.confidence,
    notes: row.notes,
    source: {
      documentId: row.source_document_id,
      url: row.url,
      fetchedAt: row.fetched_at,
      sha256: row.sha256,
      page: row.source_page,
      sheet: row.source_sheet,
    },
    lanes: laneList,
    steps: stepList,
    cells: matrix,
    stipends: rows<StipendRow>(stipends).map((s) => ({
      name: s.name,
      amountCents: s.amount_cents,
      amountRaw: s.amount_raw,
      condition: s.condition,
    })),
  };
}
