-- Migration 0010 (Công đoạn 6): báo lỗi của người dùng từ form "Report an error".
-- Số 0010–0019 dành cho Công đoạn 6; 0003–0009 dành cho Công đoạn 3 và 4 (làm song song).
-- Không lưu địa chỉ IP, email hay tên: chỉ nội dung báo lỗi và trang liên quan
-- (docs/DECISIONS.md D-104).

CREATE TABLE error_reports (
  id INTEGER PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts (id),
  schedule_id INTEGER REFERENCES schedules (id), -- NULL khi báo lỗi về học khu, không về một bảng
  page_path TEXT NOT NULL,                   -- đường dẫn trang người dùng đang xem
  message TEXT NOT NULL CHECK (length(message) BETWEEN 10 AND 2000),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  resolved_at TEXT,
  resolution TEXT,
  CHECK (resolved_at IS NULL OR resolution IS NOT NULL)
);
CREATE INDEX error_reports_open ON error_reports (created_at) WHERE resolved_at IS NULL;
CREATE INDEX error_reports_district ON error_reports (district_id);
