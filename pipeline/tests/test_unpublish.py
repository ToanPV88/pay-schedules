"""Gỡ bảng đọc từ tài liệu dùng chung (D-066), chạy SQL trên SQLite với migration thật."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pay_pipeline.catalog.d1sql import render_sql
from pay_pipeline.pdf_pipeline.run import RAW_LIMIT, _stored_raw
from pay_pipeline.pdf_pipeline.unpublish import unpublish_sql

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
