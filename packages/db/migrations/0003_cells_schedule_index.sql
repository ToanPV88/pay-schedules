-- Migration 0003 (Công đoạn 4): chỉ mục cells(schedule_id).
-- Hai chỉ mục duy nhất của cells là chỉ mục một phần (theo lane_id có hay không), nên truy vấn
-- "mọi ô của một bảng" (tóm tắt district_summary, xóa dây chuyền) phải quét cả bảng cells.
CREATE INDEX cells_schedule ON cells (schedule_id);
