"""Take back schedules read from one document shared by many districts (D-066).

A state or union compilation (all Connecticut districts in one CEA PDF, every West Virginia county
in one WVDE file, Missouri's MNEA benchmark report) is not one district's schedule: the PDF reader
picks the largest table of the file, so every district seeded with it got the same table. The
SQL below, for a list of source URLs:

* sets the published schedules from those documents back to ``draft`` (no review entry, so
  "Duyệt hết" cannot publish them again) and closes their open review entries;
* publishes again a schedule they had superseded;
* sets ``district_pipeline`` to ``no_schedule`` (or ``published`` when another schedule remains);
* recomputes ``district_summary`` and queues the districts for a cache purge (D-023).
"""

from __future__ import annotations

import datetime as dt

from pay_pipeline.catalog.d1sql import quote


def unpublish_sql(urls: list[str], reason: str, now: dt.datetime | None = None) -> list[str]:
    stamp = (now or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    in_urls = ", ".join(quote(u) for u in urls)
    picked = (
        "SELECT s.id FROM schedules s JOIN source_documents d ON d.id = s.source_document_id"
        f" WHERE d.url IN ({in_urls}) AND s.status IN ('published', 'draft')"
    )
    sql = [
        "CREATE TABLE IF NOT EXISTS _unp (schedule_id INTEGER PRIMARY KEY, district_id INTEGER)",
        "DELETE FROM _unp",
        "INSERT INTO _unp (schedule_id, district_id) SELECT s.id, s.district_id FROM schedules s"
        f" WHERE s.id IN ({picked})",
        "UPDATE schedules SET status = 'draft', published_at = NULL"
        " WHERE status = 'published' AND id IN (SELECT schedule_id FROM _unp)",
        f"UPDATE schedules SET status = 'published', superseded_by = NULL,"
        f" published_at = COALESCE(published_at, {quote(stamp)})"
        " WHERE status = 'superseded' AND superseded_by IN (SELECT schedule_id FROM _unp)",
        f"UPDATE review_queue SET resolved_at = {quote(stamp)}, resolution = {quote(reason)}"
        " WHERE resolved_at IS NULL AND schedule_id IN (SELECT schedule_id FROM _unp)",
        "UPDATE district_pipeline SET status = CASE WHEN EXISTS (SELECT 1 FROM schedules x"
        " WHERE x.district_id = district_pipeline.district_id AND x.status = 'published'"
        " AND x.schedule_type = 'teacher') THEN 'published' ELSE 'no_schedule' END,"
        f" detail = {quote(reason)}"
        " WHERE district_id IN (SELECT district_id FROM _unp)",
        "DELETE FROM district_summary WHERE district_id IN (SELECT district_id FROM _unp)",
    ]
    cell_at = (
        "(SELECT c.amount_cents FROM cells c JOIN steps t ON t.id = c.step_id"
        " JOIN lanes l ON l.id = c.lane_id WHERE c.schedule_id = s.id"
        " AND t.position = {pos} AND l.lane_normalized = '{lane}')"
    )
    sql.append(
        "INSERT INTO district_summary (district_id, school_year, schedule_id, start_ba_cents,"
        " ma_step10_cents, max_salary_cents, computed_at)"
        " SELECT s.district_id, s.school_year, s.id, "
        + cell_at.format(pos=1, lane="BA")
        + ", "
        + cell_at.format(pos=10, lane="MA")
        + ", (SELECT max(amount_cents) FROM cells WHERE schedule_id = s.id),"
        f" {quote(stamp)} FROM schedules s"
        " WHERE s.status = 'published' AND s.schedule_type = 'teacher'"
        " AND s.id = (SELECT min(x.id) FROM schedules x WHERE x.district_id = s.district_id"
        " AND x.school_year = s.school_year AND x.status = 'published'"
        " AND x.schedule_type = 'teacher')"
        " AND s.district_id IN (SELECT district_id FROM _unp)"
        " ON CONFLICT (district_id, school_year) DO UPDATE SET"
        " schedule_id = excluded.schedule_id, start_ba_cents = excluded.start_ba_cents,"
        " ma_step10_cents = excluded.ma_step10_cents,"
        " max_salary_cents = excluded.max_salary_cents, computed_at = excluded.computed_at"
    )
    sql.append(
        "INSERT INTO cache_purge_queue (district_id, queued_at) SELECT DISTINCT district_id,"
        f" {quote(stamp)} FROM _unp WHERE true"
        " ON CONFLICT (district_id) DO UPDATE SET queued_at = excluded.queued_at"
    )
    sql.append("DROP TABLE _unp")
    return sql


REJECTED_RETRY_DAYS = 90
"""Như nút "Loại" của trang duyệt (apps/review: REJECTED_RETRY_DAYS)."""


def reject_sql(schedule_ids: list[int], reason: str, now: dt.datetime | None = None) -> list[str]:
    """Close the review entries of draft schedules, as the review page's "Loại" button does."""
    when = now or dt.datetime.now(dt.UTC)
    stamp = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    retry = (when + dt.timedelta(days=REJECTED_RETRY_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = ", ".join(str(int(i)) for i in schedule_ids)
    drafts = f"SELECT id FROM schedules WHERE id IN ({ids}) AND status = 'draft'"
    return [
        f"UPDATE district_pipeline SET status = 'no_schedule', detail = {quote(reason)},"
        f" next_run_at = {quote(retry)} WHERE district_id IN (SELECT district_id FROM schedules"
        f" WHERE id IN ({drafts}) AND id IN (SELECT schedule_id FROM review_queue"
        " WHERE resolved_at IS NULL))",
        f"UPDATE review_queue SET resolved_at = {quote(stamp)}, resolution = {quote(reason)}"
        f" WHERE resolved_at IS NULL AND schedule_id IN ({drafts})",
    ]
