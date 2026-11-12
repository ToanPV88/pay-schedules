-- Migration 0005 (Công đoạn 5): nhật ký sửa ô của trang xem tay (apps/review, D-021).
CREATE TABLE review_edits (
  id INTEGER PRIMARY KEY,
  schedule_id INTEGER NOT NULL REFERENCES schedules (id),
  cell_id INTEGER NOT NULL REFERENCES cells (id) ON DELETE CASCADE,
  old_amount_cents INTEGER,
  new_amount_cents INTEGER,
  old_note TEXT,
  new_note TEXT,
  edited_at TEXT NOT NULL
);
CREATE INDEX review_edits_schedule ON review_edits (schedule_id);
CREATE INDEX review_queue_schedule ON review_queue (schedule_id);
