-- Migration 0006 (Công đoạn 5): hàng chờ xóa cache web sau khi publish.
-- Quyết định: docs/DECISIONS.md D-023 (nối D-102).

-- Pipeline (nạp SQL vào D1) và trang xem tay (duyệt bảng) ghi học khu vừa đổi vào đây. Worker xem tay
-- chạy theo lịch, gọi POST /internal/purge của Worker web qua service binding (tối đa 100 học khu
-- mỗi lần), xóa dòng khi thành công; lỗi thì tăng attempts và để lần sau thử lại.
CREATE TABLE cache_purge_queue (
  district_id INTEGER PRIMARY KEY REFERENCES districts (id),
  queued_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error TEXT
);
CREATE INDEX cache_purge_queue_queued ON cache_purge_queue (queued_at);
