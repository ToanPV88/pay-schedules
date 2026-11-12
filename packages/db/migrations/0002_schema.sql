-- Migration 0002 (Công đoạn 2): mô hình dữ liệu bảng lương.
-- Thiết kế: docs/PLAN.md Công đoạn 2; khác biệt so với PLAN ghi ở docs/DECISIONS.md D-012.
-- Quy ước:
--   * Tiền là số nguyên cents (`*_cents`), không dùng số thực.
--   * Thời điểm là chuỗi ISO 8601 UTC, ví dụ 2026-11-12T07:23:38Z.
--   * Nhãn gốc giữ nguyên văn ở cột `*_raw`; giá trị chuẩn hóa ở cột riêng.
--   * D1 bật kiểm tra khóa ngoại mặc định, kể cả trong migration.

-- ---------------------------------------------------------------- danh mục mã
-- Bảng mã thay cho CHECK để Công đoạn 10 thêm giá trị bằng INSERT, không phải dựng lại bảng.

CREATE TABLE employer_types (
  code TEXT PRIMARY KEY,
  label TEXT NOT NULL
);
INSERT INTO employer_types (code, label) VALUES ('school_district', 'School district');

CREATE TABLE schedule_types (
  code TEXT PRIMARY KEY,
  label TEXT NOT NULL
);
INSERT INTO schedule_types (code, label) VALUES
  ('teacher', 'Teacher'),
  ('substitute', 'Substitute teacher'),
  ('classified', 'Classified staff');

-- ---------------------------------------------------------------- đơn vị

CREATE TABLE states (
  code TEXT PRIMARY KEY CHECK (length(code) = 2 AND code = upper(code)),
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE
);

-- Một học khu (Công đoạn 10: mọi đơn vị trả lương, phân biệt bằng employer_type).
CREATE TABLE districts (
  id INTEGER PRIMARY KEY,
  nces_id TEXT UNIQUE,                       -- LEAID của NCES; NULL với đơn vị không phải học khu
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  state TEXT NOT NULL REFERENCES states (code),
  city TEXT,
  county TEXT,
  website TEXT,
  enrollment INTEGER CHECK (enrollment IS NULL OR enrollment >= 0),
  lat REAL CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
  lng REAL CHECK (lng IS NULL OR lng BETWEEN -180 AND 180),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  employer_type TEXT NOT NULL DEFAULT 'school_district' REFERENCES employer_types (code),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (state, slug)                       -- URL /{state}/{district-slug}
);
CREATE INDEX districts_state ON districts (state, active);

CREATE TABLE district_neighbors (
  district_id INTEGER NOT NULL REFERENCES districts (id),
  neighbor_id INTEGER NOT NULL REFERENCES districts (id),
  distance_km REAL CHECK (distance_km IS NULL OR distance_km >= 0),
  PRIMARY KEY (district_id, neighbor_id),
  CHECK (district_id <> neighbor_id)
);

-- ---------------------------------------------------------------- tài liệu nguồn

-- Một tài liệu đã tải. Bản gốc nằm trong GitHub Release riêng tư (D-011):
-- release_tag + asset_name chỉ đúng tệp cần tải lại, không phải khôi phục mọi Release.
CREATE TABLE source_documents (
  id INTEGER PRIMARY KEY,
  district_id INTEGER REFERENCES districts (id), -- NULL khi tệp của bang phủ nhiều học khu
  url TEXT NOT NULL,
  fetched_at TEXT NOT NULL,                  -- lần đầu thấy nội dung này ở URL này
  last_seen_at TEXT,                         -- lần tải gần nhất vẫn ra đúng nội dung này
  sha256 TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
  mime TEXT,
  page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
  release_tag TEXT,
  asset_name TEXT,
  UNIQUE (url, sha256)
);
CREATE INDEX source_documents_district ON source_documents (district_id);
CREATE INDEX source_documents_sha256 ON source_documents (sha256);

-- Một lần trích xuất (máy tất định hoặc LLM). Kết quả thô lưu nguyên văn.
CREATE TABLE extraction_runs (
  id INTEGER PRIMARY KEY,
  source_document_id INTEGER NOT NULL REFERENCES source_documents (id),
  model TEXT NOT NULL,                       -- vd. tên extractor@phiên bản, hoặc tên model LLM
  prompt_version TEXT,
  raw_output TEXT NOT NULL,
  cost_usd_micros INTEGER CHECK (cost_usd_micros IS NULL OR cost_usd_micros >= 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX extraction_runs_document ON extraction_runs (source_document_id);

-- ---------------------------------------------------------------- bảng lương

CREATE TABLE schedules (
  id INTEGER PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts (id),
  -- Năm học dạng 2025-26: hai số cuối phải là năm sau của bốn số đầu.
  school_year TEXT NOT NULL CHECK (
    school_year GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
    AND CAST(substr(school_year, 6, 2) AS INTEGER)
      = (CAST(substr(school_year, 1, 4) AS INTEGER) + 1) % 100
  ),
  schedule_type TEXT NOT NULL DEFAULT 'teacher' REFERENCES schedule_types (code),
  title TEXT NOT NULL DEFAULT '',            -- tiêu đề trong tài liệu, nguyên văn
  contract_days INTEGER CHECK (contract_days IS NULL OR contract_days BETWEEN 1 AND 366),
  pay_basis TEXT NOT NULL DEFAULT 'annual'
    CHECK (pay_basis IN ('annual', 'monthly', 'hourly', 'daily')),
  hours_per_year REAL CHECK (hours_per_year IS NULL OR hours_per_year > 0),
  source_document_id INTEGER NOT NULL REFERENCES source_documents (id),
  source_page INTEGER CHECK (source_page IS NULL OR source_page > 0),
  source_sheet TEXT,                         -- tên trang tính khi nguồn là Excel
  extraction_run_id INTEGER REFERENCES extraction_runs (id),
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'validated', 'published', 'superseded')),
  confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  notes TEXT,                                -- ghi chú của tài liệu, nguyên văn
  superseded_by INTEGER REFERENCES schedules (id),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  published_at TEXT,
  CHECK (status <> 'published' OR published_at IS NOT NULL),
  CHECK (status <> 'superseded' OR superseded_by IS NOT NULL)
);
-- Khóa nghiệp vụ của PLAN (district, năm học, loại, tiêu đề), áp cho bảng đang published:
-- mỗi khóa có tối đa một bảng published; bản trích lại được lưu song song ở trạng thái draft (D-012).
CREATE UNIQUE INDEX schedules_published_key
  ON schedules (district_id, school_year, schedule_type, title) WHERE status = 'published';
CREATE INDEX schedules_district_year ON schedules (district_id, school_year);
CREATE INDEX schedules_status ON schedules (status);

-- Một cột bằng cấp. Bảng chỉ có bậc thì không có dòng nào ở đây.
CREATE TABLE lanes (
  id INTEGER PRIMARY KEY,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK (position >= 1),
  label_raw TEXT NOT NULL,
  lane_normalized TEXT,                      -- BA, BA+15, MA, MA+30, PhD...; NULL khi chưa chắc
  UNIQUE (schedule_id, position),
  UNIQUE (id, schedule_id)                   -- đích của khóa ngoại kép ở cells
);

-- Một bậc.
CREATE TABLE steps (
  id INTEGER PRIMARY KEY,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK (position >= 1),
  label_raw TEXT NOT NULL,
  years_experience INTEGER CHECK (years_experience IS NULL OR years_experience >= 0),
  UNIQUE (schedule_id, position),
  UNIQUE (id, schedule_id)
);

-- Một ô lương. Khóa ngoại kép bảo đảm bậc và cột thuộc đúng bảng lương của ô.
-- Ô trống phải có ghi chú (PLAN: "ô nào thiếu thì để trống và ghi rõ").
CREATE TABLE cells (
  id INTEGER PRIMARY KEY,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id) ON DELETE CASCADE,
  step_id INTEGER NOT NULL,
  lane_id INTEGER,                           -- NULL khi bảng không có lane
  amount_cents INTEGER CHECK (amount_cents IS NULL OR amount_cents >= 0),
  note TEXT,
  CHECK (amount_cents IS NOT NULL OR note IS NOT NULL),
  FOREIGN KEY (step_id, schedule_id) REFERENCES steps (id, schedule_id) ON DELETE CASCADE,
  FOREIGN KEY (lane_id, schedule_id) REFERENCES lanes (id, schedule_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX cells_step_lane ON cells (schedule_id, step_id, lane_id) WHERE lane_id IS NOT NULL;
CREATE UNIQUE INDEX cells_step_no_lane ON cells (schedule_id, step_id) WHERE lane_id IS NULL;

-- Phụ cấp ngoài bảng. Số tiền có thể không quy ra được (vd. "2% of base"): giữ nguyên văn.
CREATE TABLE stipends (
  id INTEGER PRIMARY KEY,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  amount_cents INTEGER CHECK (amount_cents IS NULL OR amount_cents >= 0),
  amount_raw TEXT,
  condition TEXT,
  CHECK (amount_cents IS NOT NULL OR amount_raw IS NOT NULL)
);
CREATE INDEX stipends_schedule ON stipends (schedule_id);

-- ---------------------------------------------------------------- vận hành

CREATE TABLE review_queue (
  id INTEGER PRIMARY KEY,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id),
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  resolved_at TEXT,
  resolution TEXT,
  CHECK (resolved_at IS NULL OR resolution IS NOT NULL)
);
CREATE INDEX review_queue_open ON review_queue (created_at) WHERE resolved_at IS NULL;

-- Số liệu tóm tắt để so sánh nhanh; tính lại sau mỗi lần publish (Công đoạn 5).
CREATE TABLE district_summary (
  district_id INTEGER NOT NULL REFERENCES districts (id),
  school_year TEXT NOT NULL,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id),
  start_ba_cents INTEGER,
  ma_step10_cents INTEGER,
  max_salary_cents INTEGER,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (district_id, school_year)
);

-- ---------------------------------------------------------------- tìm kiếm

-- Tìm theo tên học khu, thành phố, quận; bỏ dấu (D1 hỗ trợ FTS5).
CREATE VIRTUAL TABLE districts_fts USING fts5 (
  name, city, county,
  content = 'districts', content_rowid = 'id',
  tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER districts_fts_insert AFTER INSERT ON districts BEGIN
  INSERT INTO districts_fts (rowid, name, city, county) VALUES (new.id, new.name, new.city, new.county);
END;
CREATE TRIGGER districts_fts_delete AFTER DELETE ON districts BEGIN
  INSERT INTO districts_fts (districts_fts, rowid, name, city, county)
    VALUES ('delete', old.id, old.name, old.city, old.county);
END;
CREATE TRIGGER districts_fts_update AFTER UPDATE OF name, city, county ON districts BEGIN
  INSERT INTO districts_fts (districts_fts, rowid, name, city, county)
    VALUES ('delete', old.id, old.name, old.city, old.county);
  INSERT INTO districts_fts (rowid, name, city, county) VALUES (new.id, new.name, new.city, new.county);
END;
