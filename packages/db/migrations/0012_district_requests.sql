-- Migration 0012: người xem yêu cầu bổ sung bảng lương cho học khu chưa có (docs/DECISIONS.md D-121).
-- Chỉ đếm số lần theo ngày; không lưu IP, tên, email hay gì về người gửi.

CREATE TABLE district_requests (
  district_id INTEGER NOT NULL REFERENCES districts (id),
  day TEXT NOT NULL CHECK (day GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  requests INTEGER NOT NULL DEFAULT 0 CHECK (requests >= 0),
  PRIMARY KEY (district_id, day)
);
