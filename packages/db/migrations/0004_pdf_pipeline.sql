-- Migration 0004 (Công đoạn 5): trạng thái pipeline PDF theo học khu, ứng viên tài liệu, phân loại.
-- Quyết định: docs/DECISIONS.md D-019.

-- Điểm lưu của pipeline: mỗi học khu một dòng, cho biết lần chạy gần nhất ra kết quả gì và khi nào
-- được chạy lại. Học khu chưa có dòng nào là chưa từng chạy.
CREATE TABLE district_pipeline (
  district_id INTEGER PRIMARY KEY REFERENCES districts (id),
  status TEXT NOT NULL CHECK (status IN (
    'no_website',     -- NCES không có website
    'unreachable',    -- không mở được trang chủ (DNS, TLS, robots.txt chặn...)
    'no_candidates',  -- đọc website, không thấy link tài liệu bảng lương
    'no_schedule',    -- tải tài liệu về, không tệp nào là bảng lương giáo viên
    'found',          -- có tài liệu, chưa trích (vd. hết ngân sách lần chạy)
    'unchanged',      -- tài liệu đã xử lý, sha256 không đổi
    'review',         -- đã trích, trượt Validate: chờ xem tay
    'published',      -- đã trích, qua Validate, đã publish
    'error'
  )),
  detail TEXT,
  attempts INTEGER NOT NULL DEFAULT 1 CHECK (attempts >= 1),
  last_run_key TEXT NOT NULL,
  last_run_at TEXT NOT NULL,
  next_run_at TEXT              -- NULL: không tự chạy lại (chờ người)
);
CREATE INDEX district_pipeline_status ON district_pipeline (status);
CREATE INDEX district_pipeline_next ON district_pipeline (next_run_at);

-- Link tài liệu tìm được khi dò website (bước Discover).
CREATE TABLE document_candidates (
  id INTEGER PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts (id),
  url TEXT NOT NULL,
  found_on TEXT,
  anchor_text TEXT,
  method TEXT NOT NULL CHECK (method IN ('crawl', 'sitemap', 'search', 'manual')),
  score REAL NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  UNIQUE (district_id, url)
);

-- Kết quả phân loại một tài liệu (bước Classify).
CREATE TABLE document_classifications (
  id INTEGER PRIMARY KEY,
  source_document_id INTEGER NOT NULL REFERENCES source_documents (id),
  method TEXT NOT NULL,                       -- vd. heuristic@1
  is_schedule INTEGER NOT NULL CHECK (is_schedule IN (0, 1)),
  scanned INTEGER NOT NULL DEFAULT 0 CHECK (scanned IN (0, 1)),
  school_year TEXT,
  pages TEXT,                                 -- JSON: số trang có bảng lương
  score REAL,
  detail TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (source_document_id, method)
);

-- Tra nhanh tài liệu đã biết theo URL (bỏ qua tệp có sha256 không đổi).
CREATE INDEX source_documents_url ON source_documents (url);
