-- Migration 0011 (D-065): bảng lương ngạch × bậc của cơ quan liên bang (OPM General Schedule và
-- 58 vùng locality, y tá VA theo cơ sở; sau này USPS).
-- Tách khỏi `districts`/`schedules`: đơn vị trả lương là cả nước hoặc một vùng/cơ sở liên bang,
-- không thuộc một bang, và mỗi bảng có hàng là ngạch (grade) thay vì bậc của giáo viên. Trang học
-- khu và pipeline giáo viên không đổi.
-- Quy ước như 0002: tiền là cents, thời điểm ISO 8601 UTC.

CREATE TABLE pay_tables (
  id INTEGER PRIMARY KEY,
  family TEXT NOT NULL CHECK (family IN ('gs', 'gs_locality', 'va_nurse', 'usps')),
  code TEXT NOT NULL,                        -- mã của nguồn: 'GS', 'ATL', '626-N001'
  slug TEXT NOT NULL,                        -- URL: /federal/gs/{slug}, /va-nurse/{slug}
  group_slug TEXT,                           -- y tá VA: cơ sở (station) chứa bảng
  name TEXT NOT NULL,                        -- tên hiển thị
  area TEXT,                                 -- vùng/địa điểm áp dụng, nguyên văn
  state TEXT REFERENCES states (code),       -- bang chính (NULL với bảng toàn quốc)
  year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
  effective_date TEXT,                       -- YYYY-MM-DD
  pay_basis TEXT NOT NULL DEFAULT 'annual' CHECK (pay_basis IN ('annual', 'hourly')),
  row_header TEXT NOT NULL DEFAULT 'Grade',
  col_header TEXT NOT NULL DEFAULT 'Step',
  title TEXT NOT NULL,                       -- tiêu đề trong tài liệu, nguyên văn
  notes TEXT,                                -- chú thích của tài liệu, nguyên văn
  source_url TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
  release_tag TEXT,
  asset_name TEXT,
  fetched_at TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (family, slug, year)
);
CREATE INDEX pay_tables_family_year ON pay_tables (family, year);
CREATE INDEX pay_tables_group ON pay_tables (family, group_slug, year);

CREATE TABLE pay_cells (
  table_id INTEGER NOT NULL REFERENCES pay_tables (id) ON DELETE CASCADE,
  row_pos INTEGER NOT NULL CHECK (row_pos >= 1),
  row_label TEXT NOT NULL,
  col_pos INTEGER NOT NULL CHECK (col_pos >= 1),
  col_label TEXT NOT NULL,
  amount_cents INTEGER CHECK (amount_cents IS NULL OR amount_cents > 0),
  note TEXT,                                 -- vd. "*" = trần lương Executive Schedule IV
  PRIMARY KEY (table_id, row_pos, col_pos)
);
