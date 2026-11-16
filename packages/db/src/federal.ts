/**
 * Truy vấn chỉ đọc cho bảng lương liên bang (DECISIONS.md D-065, migration 0011): OPM General
 * Schedule (bảng cơ bản và 58 vùng locality) và bảng lương y tá VA theo cơ sở. Pipeline chỉ nạp
 * bảng đã qua kiểm tra, nên mọi dòng trong `pay_tables` đều là dữ liệu hiển thị được.
 */

export type PayFamily = "gs" | "gs_locality" | "va_nurse" | "usps";

export interface PayTableInfo {
  id: number;
  family: PayFamily;
  code: string;
  slug: string;
  groupSlug: string | null;
  name: string;
  area: string | null;
  stateCode: string | null;
  stateName: string | null;
  year: number;
  effectiveDate: string | null;
  title: string;
}

export interface PayTable extends PayTableInfo {
  rowHeader: string;
  colHeader: string;
  notes: string | null;
  sourceUrl: string;
  fetchedAt: string;
  rows: string[];
  cols: string[];
  /** cells[row][col]: cents hoặc null; note là chú thích của ô ("*"). */
  cells: ({ cents: number; note: string | null } | null)[][];
}

export interface VaStation {
  groupSlug: string;
  name: string;
  stateCode: string | null;
  stateName: string | null;
  tables: number;
  minCents: number | null;
  maxCents: number | null;
}

interface InfoRow {
  id: number;
  family: PayFamily;
  code: string;
  slug: string;
  group_slug: string | null;
  name: string;
  area: string | null;
  state: string | null;
  state_name: string | null;
  year: number;
  effective_date: string | null;
  title: string;
}

const INFO = `SELECT t.id, t.family, t.code, t.slug, t.group_slug, t.name, t.area, t.state,
                     s.name AS state_name, t.year, t.effective_date, t.title
                FROM pay_tables t LEFT JOIN states s ON s.code = t.state`;

function info(r: InfoRow): PayTableInfo {
  return {
    id: r.id,
    family: r.family,
    code: r.code,
    slug: r.slug,
    groupSlug: r.group_slug,
    name: r.name,
    area: r.area,
    stateCode: r.state,
    stateName: r.state_name,
    year: r.year,
    effectiveDate: r.effective_date,
    title: r.title,
  };
}

/** Năm mới nhất có dữ liệu của một loại bảng (null khi chưa nạp). */
export async function latestPayYear(db: D1Database, family: PayFamily): Promise<number | null> {
  const row = await db
    .prepare("SELECT MAX(year) AS year FROM pay_tables WHERE family = ?")
    .bind(family)
    .first<{ year: number | null }>();
  return row?.year ?? null;
}

/** Mọi bảng của một loại trong một năm, theo tên. */
export async function listPayTables(
  db: D1Database,
  family: PayFamily,
  year: number,
): Promise<PayTableInfo[]> {
  const { results } = await db
    .prepare(`${INFO} WHERE t.family = ? AND t.year = ? ORDER BY t.name, t.slug`)
    .bind(family, year)
    .all<InfoRow>();
  return results.map(info);
}

/** Bảng của một nhóm (y tá VA: một cơ sở), theo tiêu đề. */
export async function listPayTablesOfGroup(
  db: D1Database,
  family: PayFamily,
  groupSlug: string,
  year: number,
): Promise<PayTableInfo[]> {
  const { results } = await db
    .prepare(
      `${INFO} WHERE t.family = ? AND t.group_slug = ? AND t.year = ? ORDER BY t.title, t.slug`,
    )
    .bind(family, groupSlug, year)
    .all<InfoRow>();
  return results.map(info);
}

/** Một bảng đầy đủ các ô. */
export async function getPayTable(db: D1Database, id: number): Promise<PayTable | null> {
  const head = await db
    .prepare(
      `${INFO.replace("t.title", "t.title, t.row_header, t.col_header, t.notes, t.source_url, t.fetched_at")} WHERE t.id = ?`,
    )
    .bind(id)
    .first<
      InfoRow & {
        row_header: string;
        col_header: string;
        notes: string | null;
        source_url: string;
        fetched_at: string;
      }
    >();
  if (!head) {
    return null;
  }
  const { results } = await db
    .prepare(
      `SELECT row_pos, row_label, col_pos, col_label, amount_cents, note
         FROM pay_cells WHERE table_id = ? ORDER BY row_pos, col_pos`,
    )
    .bind(id)
    .all<{
      row_pos: number;
      row_label: string;
      col_pos: number;
      col_label: string;
      amount_cents: number | null;
      note: string | null;
    }>();
  const rows: string[] = [];
  const cols: string[] = [];
  for (const c of results) {
    rows[c.row_pos - 1] = c.row_label;
    cols[c.col_pos - 1] = c.col_label;
  }
  const cells: PayTable["cells"] = rows.map(() => cols.map(() => null));
  for (const c of results) {
    const row = cells[c.row_pos - 1];
    if (row && c.amount_cents !== null) {
      row[c.col_pos - 1] = { cents: c.amount_cents, note: c.note };
    }
  }
  return {
    ...info(head),
    rowHeader: head.row_header,
    colHeader: head.col_header,
    notes: head.notes,
    sourceUrl: head.source_url,
    fetchedAt: head.fetched_at,
    rows: rows.map((r, i) => r ?? `Row ${i + 1}`),
    cols: cols.map((c, i) => c ?? `Column ${i + 1}`),
    cells,
  };
}

/** Bảng theo (loại, slug, năm). */
export async function findPayTable(
  db: D1Database,
  family: PayFamily,
  slug: string,
  year: number,
): Promise<PayTable | null> {
  const row = await db
    .prepare("SELECT id FROM pay_tables WHERE family = ? AND slug = ? AND year = ?")
    .bind(family, slug, year)
    .first<{ id: number }>();
  return row ? await getPayTable(db, row.id) : null;
}

/** Các cơ sở VA có bảng lương y tá trong một năm, kèm khoảng lương thấp nhất – cao nhất. */
export async function listVaStations(db: D1Database, year: number): Promise<VaStation[]> {
  const { results } = await db
    .prepare(
      `SELECT t.group_slug, MIN(t.name) AS name, t.state, s.name AS state_name,
              COUNT(DISTINCT t.id) AS tables, MIN(c.amount_cents) AS min_cents,
              MAX(c.amount_cents) AS max_cents
         FROM pay_tables t
         LEFT JOIN states s ON s.code = t.state
         LEFT JOIN pay_cells c ON c.table_id = t.id
        WHERE t.family = 'va_nurse' AND t.year = ? AND t.group_slug IS NOT NULL
        GROUP BY t.group_slug
        ORDER BY s.name IS NULL, s.name, name`,
    )
    .bind(year)
    .all<{
      group_slug: string;
      name: string;
      state: string | null;
      state_name: string | null;
      tables: number;
      min_cents: number | null;
      max_cents: number | null;
    }>();
  return results.map((r) => ({
    groupSlug: r.group_slug,
    name: r.name,
    stateCode: r.state,
    stateName: r.state_name,
    tables: r.tables,
    minCents: r.min_cents,
    maxCents: r.max_cents,
  }));
}
