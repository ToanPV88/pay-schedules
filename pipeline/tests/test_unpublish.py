"""Gỡ bảng đọc từ tài liệu dùng chung (D-066), chạy SQL trên SQLite với migration thật."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from pay_pipeline.catalog.d1sql import render_sql
from pay_pipeline.pdf_pipeline.run import RAW_LIMIT, _stored_raw
from pay_pipeline.pdf_pipeline.unpublish import due_sql, unpublish_sql

MIGRATIONS = Path(__file__).resolve().parents[2] / "packages" / "db" / "migrations"
SHARED = "https://example.org/all-districts.pdf"


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    for m in sorted(MIGRATIONS.glob("*.sql")):
        db.executescript(m.read_text())
    db.executescript(
        """
        INSERT INTO states VALUES ('CT', 'Connecticut', 'connecticut');
        INSERT INTO districts (id, nces_id, name, slug, state) VALUES
          (1, '0900001', 'A', 'a', 'CT'), (2, '0900002', 'B', 'b', 'CT');
        INSERT INTO source_documents (id, url, fetched_at, sha256) VALUES
          (1, 'https://example.org/b-old.pdf', '2026-01-01T00:00:00Z', printf('%064d', 1)),
          (2, 'https://example.org/all-districts.pdf', '2026-11-16T00:00:00Z', printf('%064d', 2));
        INSERT INTO schedules (id, district_id, school_year, source_document_id, status,
                               published_at, superseded_by) VALUES
          (10, 1, '2025-26', 2, 'published', '2026-11-16T00:00:00Z', NULL),
          (12, 2, '2025-26', 2, 'published', '2026-11-16T00:00:00Z', NULL),
          (11, 2, '2024-25', 1, 'superseded', '2026-01-01T00:00:00Z', 12);
        INSERT INTO district_pipeline VALUES
          (1, 'published', '', 1, 'k', '2026-11-16T00:00:00Z', NULL),
          (2, 'published', '', 1, 'k', '2026-11-16T00:00:00Z', NULL);
        """
    )
    return db


def test_unpublish_shared_document() -> None:
    db = _db()
    db.executescript(render_sql(unpublish_sql([SHARED], "Gỡ: tài liệu dùng chung (D-066)")))
    status = dict(db.execute("SELECT id, status FROM schedules").fetchall())
    assert status == {10: "draft", 11: "published", 12: "draft"}
    pipeline = dict(db.execute("SELECT district_id, status FROM district_pipeline").fetchall())
    assert pipeline == {1: "no_schedule", 2: "published"}
    assert db.execute("SELECT COUNT(*) FROM cache_purge_queue").fetchone() == (2,)
    # chạy lại không đổi gì
    db.executescript(render_sql(unpublish_sql([SHARED], "Gỡ")))
    assert dict(db.execute("SELECT id, status FROM schedules").fetchall())[11] == "published"


def test_long_raw_output_is_cut() -> None:
    raw = "x" * (RAW_LIMIT + 10)
    stored = _stored_raw(raw)
    assert len(stored) < RAW_LIMIT + 200 and '"truncated": true' in stored
    assert _stored_raw("short") == "short"


def test_reject_closes_review_like_the_button() -> None:
    from pay_pipeline.pdf_pipeline.unpublish import reject_sql

    db = _db()
    db.executescript(
        """
        INSERT INTO schedules (id, district_id, school_year, source_document_id, status)
          VALUES (20, 1, '2026-27', 1, 'draft');
        INSERT INTO review_queue (schedule_id, reason) VALUES (20, '[lane_label] x');
        """
    )
    db.executescript(render_sql(reject_sql([20, 10], "Loại")))
    assert db.execute("SELECT resolution FROM review_queue").fetchone() == ("Loại",)
    assert db.execute("SELECT status FROM district_pipeline WHERE district_id = 1").fetchone() == (
        "no_schedule",
    )
    # bảng đã published (10) không bị đụng tới
    assert db.execute("SELECT status FROM schedules WHERE id = 10").fetchone() == ("published",)


def test_requeue_takes_published_back_to_review() -> None:
    from pay_pipeline.pdf_pipeline.unpublish import requeue_sql

    db = _db()
    db.executescript(render_sql(requeue_sql([12], "[lane_label] Cột không có tên (D-067)")))
    status = dict(db.execute("SELECT id, status FROM schedules").fetchall())
    assert status == {10: "published", 11: "published", 12: "draft"}
    assert db.execute("SELECT schedule_id, resolved_at FROM review_queue").fetchall() == [
        (12, None)
    ]
    # bảng cũ 11 được publish lại nên học khu 2 vẫn có bảng
    assert db.execute("SELECT status FROM district_pipeline WHERE district_id = 2").fetchone() == (
        "published",
    )
    db.executescript(render_sql(requeue_sql([12], "x")))  # chạy lại: không thêm mục trùng
    assert db.execute("SELECT COUNT(*) FROM review_queue").fetchone() == (1,)


def test_due_sql_makes_districts_due() -> None:
    sql = due_sql(["3600009", "3600009", "4812120"], now=dt.datetime(2026, 11, 16, tzinfo=dt.UTC))
    assert sql == [
        "UPDATE district_pipeline SET next_run_at = '2026-11-16T00:00:00Z'"
        " WHERE district_id IN (SELECT id FROM districts WHERE nces_id IN ('3600009', '4812120'))"
    ]


def test_retire_future_year_read_before_d070() -> None:
    from pay_pipeline.pdf_pipeline.unpublish import retire_future_sql

    db = _db()
    db.executescript(
        """
        INSERT INTO schedules (id, district_id, school_year, source_document_id, status,
                               published_at) VALUES
          (30, 1, '2027-28', 1, 'published', '2026-11-15T00:00:00Z'),
          (31, 1, '2026-27', 1, 'published', '2026-11-17T00:00:00Z'),
          (32, 2, '2027-28', 1, 'published', '2026-11-15T00:00:00Z');
        """
    )
    sql = retire_future_sql(dt.date(2026, 11, 17))
    db.executescript(render_sql(sql))
    rows = {r[0]: r[1:] for r in db.execute("SELECT id, status, superseded_by FROM schedules")}
    assert rows[30] == ("superseded", 31)
    assert rows[31] == ("published", None)
    assert rows[32] == ("published", None)  # district 2 has no table of the year in force
    assert db.execute("SELECT district_id FROM cache_purge_queue").fetchall() == [(1,)]
    db.executescript(render_sql(sql))  # running again changes nothing
    assert db.execute("SELECT status FROM schedules WHERE id = 30").fetchone() == ("superseded",)
