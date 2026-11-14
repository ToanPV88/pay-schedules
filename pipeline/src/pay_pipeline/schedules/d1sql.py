"""SQL that loads prepared schedules into D1 (schema: packages/db/migrations/0002_schema.sql).

The data goes into staging tables (``_imp_*``) first, then set-based statements copy it into the
real tables. Re-running the same script, or a script built from the same source files, adds
nothing (PLAN Công đoạn 5: "chạy lại ... không tạo bản ghi trùng"):

* ``source_documents`` is upserted on (url, sha256); only ``last_seen_at`` moves;
* a schedule is identified by (district, school year, type, title, source document); an
  existing one is reused, and each child row (lane, step, cell, stipend, review reason) is
  inserted only when missing, so a run cut off half-way can simply be run again;
* schedules are inserted as ``draft``; those that passed every check are then published, and a
  published schedule with the same key from an older source becomes ``superseded``;
* ``district_summary`` is recomputed for the districts touched, and those districts are queued in
  ``cache_purge_queue`` so the website's cached pages are purged (D-023).

Every statement stays under D1's 100 KB statement limit; child rows are copied in slices of
schedules so no single statement runs long.
"""

from __future__ import annotations

import datetime as dt
import json

from pay_pipeline.catalog.d1sql import batched_insert, quote
from pay_pipeline.schedules.state_import import ImportResult, RunRecord

SLICE = 40
"""Schedules per statement when copying child rows from staging tables."""

STAGING = {
    "_imp_sources": "asset_name TEXT, url TEXT, sha256 TEXT, fetched_at TEXT, mime TEXT,"
    " release_tag TEXT, district_nces TEXT",
    "_imp_runs": "url TEXT, sha256 TEXT, model TEXT, prompt_version TEXT, raw TEXT, cost INTEGER",
    "_imp_schedules": "k INTEGER PRIMARY KEY, nces_id TEXT, school_year TEXT, schedule_type TEXT,"
    " title TEXT, contract_days INTEGER, pay_basis TEXT, url TEXT, sha256 TEXT, importer TEXT,"
    " source_sheet TEXT, source_page INTEGER, notes TEXT, status TEXT, confidence REAL",
    "_imp_lanes": "k INTEGER, position INTEGER, label_raw TEXT, lane_normalized TEXT",
    "_imp_steps": "k INTEGER, position INTEGER, label_raw TEXT, years INTEGER",
    "_imp_cells": "k INTEGER, step_pos INTEGER, lane_pos INTEGER, amount_cents INTEGER, note TEXT",
    "_imp_stipends": "k INTEGER, name TEXT, amount_cents INTEGER, amount_raw TEXT, condition TEXT",
    "_imp_reviews": "k INTEGER, reason TEXT",
    "_imp_accepted": "k INTEGER, reason TEXT",
    "_imp_map": "k INTEGER PRIMARY KEY, schedule_id INTEGER NOT NULL",
}


def state_runs(result: ImportResult) -> list[RunRecord]:
    """One summary run per state file: the raw data is the file itself (deterministic import)."""
    importers = {p.source.asset_name: p.importer for p in result.prepared}
    return [
        RunRecord(
            url=s.url,
            sha256=s.sha256,
            model=importers[s.asset_name],
            prompt_version=None,
            raw_output=json.dumps(
                {
                    "importer": importers[s.asset_name],
                    "asset": s.asset_name,
                    "release": s.release_tag,
                    "schedules": sum(p.source == s for p in result.prepared),
                    "note": "Deterministic import of a state file; the raw data is the"
                    " source file kept in the GitHub Release.",
                },
                ensure_ascii=False,
            ),
            cost_usd_micros=None,
        )
        for s in result.sources
        if s.asset_name in importers
    ]


AUTO_RESOLVED = "auto: the checks no longer report this on re-import"
SUPERSEDED = "auto: a newer reading of the same document replaced this draft (D-053)"
AS_REPORTED = "as reported: published from the state file as the district reported it (D-028)"
"""Resolution of a finding on a state-file schedule that is published anyway (D-028)."""
"""Resolution of an open review reason that a re-import with changed checks no longer gives."""


def _decided(schedule_id: str, decision: str) -> str:
    """Rows of a decision taken on the review page (apps/review: "approved (…)", "rejected: …")."""
    return (
        f"SELECT 1 FROM review_queue d WHERE d.schedule_id = {schedule_id}"
        f" AND d.resolution LIKE '{decision}%'"
    )


def _stamp(now: dt.datetime) -> str:
    return now.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def schedules_sql(result: ImportResult, now: dt.datetime | None = None) -> list[str]:
    stamp = _stamp(now or dt.datetime.now(dt.UTC))
    sql: list[str] = []
    for table, columns in STAGING.items():
        sql.append(f"DROP TABLE IF EXISTS {table}")
        sql.append(f"CREATE TABLE {table} ({columns})")
        if columns.startswith("k INTEGER,"):
            sql.append(f"CREATE INDEX {table}_k ON {table} (k)")

    sql += batched_insert(
        "INSERT INTO _imp_sources (asset_name, url, sha256, fetched_at, mime, release_tag,"
        " district_nces)",
        (
            (s.asset_name, s.url, s.sha256, s.fetched_at, s.mime, s.release_tag, s.district_nces)
            for s in result.sources
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_runs (url, sha256, model, prompt_version, raw, cost)",
        (
            (r.url, r.sha256, r.model, r.prompt_version, r.raw_output, r.cost_usd_micros)
            for r in (result.runs if result.runs is not None else state_runs(result))
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_schedules (k, nces_id, school_year, schedule_type, title, contract_days,"
        " pay_basis, url, sha256, importer, source_sheet, source_page, notes, status, confidence)",
        (
            (
                p.key,
                p.nces_id,
                p.draft.school_year,
                p.draft.schedule_type,
                p.draft.title,
                p.draft.contract_days,
                p.draft.pay_basis,
                p.source.url,
                p.source.sha256,
                p.importer,
                p.draft.source_sheet,
                p.draft.source_page,
                p.draft.notes,
                p.status,
                p.confidence,
            )
            for p in result.prepared
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_lanes (k, position, label_raw, lane_normalized)",
        (
            (p.key, i + 1, lane.label_raw, lane.lane_normalized)
            for p in result.prepared
            for i, lane in enumerate(p.draft.lanes)
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_steps (k, position, label_raw, years)",
        (
            (p.key, i + 1, step.label_raw, step.years_experience)
            for p in result.prepared
            for i, step in enumerate(p.draft.steps)
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_cells (k, step_pos, lane_pos, amount_cents, note)",
        (
            (p.key, s + 1, None if ln is None else ln + 1, c.amount_cents, c.note)
            for p in result.prepared
            for (s, ln), c in sorted(
                p.draft.cells.items(),
                key=lambda kv: (kv[0][0], -1 if kv[0][1] is None else kv[0][1]),
            )
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_stipends (k, name, amount_cents, amount_raw, condition)",
        (
            (p.key, st.name, st.amount_cents, st.amount_raw, st.condition)
            for p in result.prepared
            for st in p.draft.stipends
        ),
    )
    sql += batched_insert(
        "INSERT INTO _imp_reviews (k, reason)",
        ((p.key, reason) for p in result.prepared for reason in p.reasons),
    )
    sql += batched_insert(
        "INSERT INTO _imp_accepted (k, reason)",
        ((p.key, reason) for p in result.prepared for reason in p.accepted_reasons),
    )

    # Source documents: a state file has district_id NULL (it covers many districts).
    sql.append(
        "INSERT INTO source_documents (district_id, url, fetched_at, last_seen_at, sha256, mime,"
        " release_tag, asset_name)"
        " SELECT (SELECT id FROM districts WHERE nces_id = i.district_nces), i.url, i.fetched_at,"
        " i.fetched_at, i.sha256, i.mime, i.release_tag, i.asset_name"
        " FROM _imp_sources i WHERE true"
        " ON CONFLICT (url, sha256) DO UPDATE SET"
        " last_seen_at = max(coalesce(source_documents.last_seen_at, ''), excluded.last_seen_at)"
    )
    sql.append(
        "INSERT INTO extraction_runs (source_document_id, model, prompt_version, raw_output,"
        " cost_usd_micros, created_at)"
        f" SELECT d.id, i.model, i.prompt_version, i.raw, i.cost, {quote(stamp)}"
        " FROM _imp_runs i JOIN source_documents d ON d.url = i.url AND d.sha256 = i.sha256"
        " WHERE NOT EXISTS (SELECT 1 FROM extraction_runs e WHERE e.source_document_id = d.id"
        " AND e.model = i.model AND e.prompt_version IS i.prompt_version)"
    )

    same_schedule = (
        "s.district_id = dist.id AND s.school_year = i.school_year"
        " AND s.schedule_type = i.schedule_type AND s.title = i.title"
        " AND s.source_document_id = d.id"
    )
    joins = (
        " FROM _imp_schedules i JOIN districts dist ON dist.nces_id = i.nces_id"
        " JOIN source_documents d ON d.url = i.url AND d.sha256 = i.sha256"
    )
    sql.append(
        "INSERT INTO schedules (district_id, school_year, schedule_type, title, contract_days,"
        " pay_basis, source_document_id, source_sheet, source_page, extraction_run_id, status,"
        " confidence, notes, created_at)"
        " SELECT dist.id, i.school_year, i.schedule_type, i.title, i.contract_days, i.pay_basis,"
        " d.id, i.source_sheet, i.source_page,"
        " (SELECT max(e.id) FROM extraction_runs e"
        " WHERE e.source_document_id = d.id AND e.model = i.importer),"
        f" 'draft', i.confidence, i.notes, {quote(stamp)}"
        + joins
        + f" WHERE NOT EXISTS (SELECT 1 FROM schedules s WHERE {same_schedule})"
        " ORDER BY i.k"
    )
    sql.append(
        "INSERT INTO _imp_map (k, schedule_id) SELECT i.k, max(s.id)"
        + joins
        + f" JOIN schedules s ON {same_schedule} GROUP BY i.k"
    )

    last = max((p.key for p in result.prepared), default=0)
    for lo in range(1, last + 1, SLICE):
        hi = lo + SLICE - 1
        rng = f"BETWEEN {lo} AND {hi}"
        sql.append(
            "INSERT INTO lanes (schedule_id, position, label_raw, lane_normalized)"
            " SELECT m.schedule_id, x.position, x.label_raw, x.lane_normalized"
            f" FROM _imp_lanes x JOIN _imp_map m ON m.k = x.k WHERE x.k {rng}"
            " AND NOT EXISTS (SELECT 1 FROM lanes l"
            " WHERE l.schedule_id = m.schedule_id AND l.position = x.position)"
        )
        sql.append(
            "INSERT INTO steps (schedule_id, position, label_raw, years_experience)"
            " SELECT m.schedule_id, x.position, x.label_raw, x.years"
            f" FROM _imp_steps x JOIN _imp_map m ON m.k = x.k WHERE x.k {rng}"
            " AND NOT EXISTS (SELECT 1 FROM steps t"
            " WHERE t.schedule_id = m.schedule_id AND t.position = x.position)"
        )
        sql.append(
            "INSERT INTO cells (schedule_id, step_id, lane_id, amount_cents, note)"
            " SELECT m.schedule_id, t.id, l.id, x.amount_cents, x.note"
            " FROM _imp_cells x JOIN _imp_map m ON m.k = x.k"
            " JOIN steps t ON t.schedule_id = m.schedule_id AND t.position = x.step_pos"
            " LEFT JOIN lanes l ON l.schedule_id = m.schedule_id AND l.position = x.lane_pos"
            f" WHERE x.k {rng} AND ("
            # Two branches so each NOT EXISTS can use its partial unique index on cells.
            " (x.lane_pos IS NOT NULL AND l.id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cells c"
            " WHERE c.schedule_id = m.schedule_id AND c.step_id = t.id AND c.lane_id = l.id))"
            " OR (x.lane_pos IS NULL AND NOT EXISTS (SELECT 1 FROM cells c"
            " WHERE c.schedule_id = m.schedule_id AND c.step_id = t.id AND c.lane_id IS NULL)))"
        )
    # Stipends are replaced as a set: rows no longer produced for a schedule are removed.
    sql.append(
        "DELETE FROM stipends WHERE schedule_id IN (SELECT schedule_id FROM _imp_map)"
        " AND NOT EXISTS (SELECT 1 FROM _imp_stipends x JOIN _imp_map m ON m.k = x.k"
        " WHERE m.schedule_id = stipends.schedule_id AND x.name = stipends.name"
        " AND x.amount_cents IS stipends.amount_cents AND x.amount_raw IS stipends.amount_raw)"
    )
    sql.append(
        "INSERT INTO stipends (schedule_id, name, amount_cents, amount_raw, condition)"
        " SELECT m.schedule_id, x.name, x.amount_cents, x.amount_raw, x.condition"
        " FROM _imp_stipends x JOIN _imp_map m ON m.k = x.k"
        " WHERE NOT EXISTS (SELECT 1 FROM stipends p WHERE p.schedule_id = m.schedule_id"
        " AND p.name = x.name AND p.amount_cents IS x.amount_cents"
        " AND p.amount_raw IS x.amount_raw)"
    )
    # A schedule that now fails a check (new rule, or a hold from a manual cross-check) goes
    # back to draft even if an earlier run published it, unless a person approved it on the
    # review page (D-024): a person's decision is not undone by a re-run.
    sql.append(
        "UPDATE schedules SET status = 'draft', published_at = NULL"
        " WHERE status = 'published' AND id IN (SELECT m.schedule_id FROM _imp_map m"
        " JOIN _imp_schedules i ON i.k = m.k WHERE i.status = 'draft')"
        f" AND NOT EXISTS ({_decided('schedules.id', 'approved')})"
    )
    # Open reasons the checks no longer give (a rule changed) are closed, so the review page
    # only lists what is still wrong.
    accepted = (
        "SELECT 1 FROM _imp_accepted x JOIN _imp_map m ON m.k = x.k"
        " WHERE m.schedule_id = review_queue.schedule_id AND x.reason = review_queue.reason"
    )
    sql.append(
        f"UPDATE review_queue SET resolved_at = {quote(stamp)}, resolution ="
        f" CASE WHEN EXISTS ({accepted}) THEN {quote(AS_REPORTED)} ELSE {quote(AUTO_RESOLVED)} END"
        " WHERE resolved_at IS NULL AND schedule_id IN (SELECT schedule_id FROM _imp_map)"
        " AND NOT EXISTS (SELECT 1 FROM _imp_reviews x JOIN _imp_map m ON m.k = x.k"
        " WHERE m.schedule_id = review_queue.schedule_id AND x.reason = review_queue.reason)"
    )
    # Findings of a schedule published as reported are kept, already resolved: the website says
    # the figures are shown as the district reported them (D-028).
    sql.append(
        "INSERT INTO review_queue (schedule_id, reason, created_at, resolved_at, resolution)"
        f" SELECT m.schedule_id, x.reason, {quote(stamp)}, {quote(stamp)}, {quote(AS_REPORTED)}"
        " FROM _imp_accepted x JOIN _imp_map m ON m.k = x.k"
        " WHERE NOT EXISTS (SELECT 1 FROM review_queue r"
        " WHERE r.schedule_id = m.schedule_id AND r.reason = x.reason)"
        f" AND NOT EXISTS ({_decided('m.schedule_id', 'rejected')})"
    )
    sql.append(
        "INSERT INTO review_queue (schedule_id, reason, created_at)"
        f" SELECT m.schedule_id, x.reason, {quote(stamp)}"
        " FROM _imp_reviews x JOIN _imp_map m ON m.k = x.k"
        " JOIN schedules s ON s.id = m.schedule_id AND s.status = 'draft'"
        " WHERE NOT EXISTS (SELECT 1 FROM review_queue r"
        " WHERE r.schedule_id = m.schedule_id AND r.reason = x.reason)"
        f" AND NOT EXISTS ({_decided('m.schedule_id', 'rejected')})"
    )

    # A newer reading of the same document (a new reader version, D-052) can give a different
    # school year or title, hence a new schedule: the old draft from that document is retired
    # and its open review reasons closed, so the review page does not list both (D-053).
    # Drafts a person decided on are left alone.
    newer = (
        "SELECT max(m.schedule_id) FROM _imp_map m JOIN schedules n ON n.id = m.schedule_id"
        " WHERE n.source_document_id = schedules.source_document_id"
        " AND n.schedule_type = schedules.schedule_type"
    )
    sql.append(
        f"UPDATE schedules SET status = 'superseded', superseded_by = ({newer})"
        " WHERE status = 'draft' AND id NOT IN (SELECT schedule_id FROM _imp_map)"
        f" AND ({newer}) IS NOT NULL"
        f" AND NOT EXISTS ({_decided('schedules.id', 'approved')})"
        f" AND NOT EXISTS ({_decided('schedules.id', 'rejected')})"
    )
    sql.append(
        f"UPDATE review_queue SET resolved_at = {quote(stamp)}, resolution = {quote(SUPERSEDED)}"
        " WHERE resolved_at IS NULL AND schedule_id IN (SELECT id FROM schedules"
        " WHERE status = 'superseded' AND superseded_by IN (SELECT schedule_id FROM _imp_map))"
    )

    # Publish: first retire the published schedule each new one replaces, then publish.
    # A draft a person rejected stays a draft even when the checks now pass.
    to_publish = (
        "SELECT m.schedule_id FROM _imp_map m JOIN _imp_schedules i ON i.k = m.k"
        " JOIN schedules n ON n.id = m.schedule_id"
        " WHERE i.status = 'published' AND n.status = 'draft'"
        f" AND NOT EXISTS ({_decided('n.id', 'rejected')})"
    )
    sql.append(
        "UPDATE schedules SET status = 'superseded', superseded_by = ("
        f"{to_publish} AND n.district_id = schedules.district_id"
        " AND n.school_year = schedules.school_year AND n.schedule_type = schedules.schedule_type"
        " AND n.title = schedules.title)"
        " WHERE status = 'published' AND EXISTS ("
        f"{to_publish} AND n.district_id = schedules.district_id"
        " AND n.school_year = schedules.school_year AND n.schedule_type = schedules.schedule_type"
        " AND n.title = schedules.title AND n.id <> schedules.id)"
    )
    sql.append(
        f"UPDATE schedules SET status = 'published', published_at = {quote(stamp)}"
        f" WHERE id IN ({to_publish})"
    )

    # district_summary: one row per district and school year, from its first published teacher
    # schedule. start_ba: step 1 of the lane normalised to BA; ma_step10: step position 10 of
    # the MA lane; max: the largest cell (D-018).
    cell_at = (
        "(SELECT c.amount_cents FROM cells c JOIN steps t ON t.id = c.step_id"
        " JOIN lanes l ON l.id = c.lane_id WHERE c.schedule_id = s.id"
        " AND t.position = {pos} AND l.lane_normalized = '{lane}')"
    )
    touched = "SELECT t.district_id FROM schedules t JOIN _imp_map m ON m.schedule_id = t.id"
    sql.append(f"DELETE FROM district_summary WHERE district_id IN ({touched})")
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
        f" AND s.district_id IN ({touched})"
        " ON CONFLICT (district_id, school_year) DO UPDATE SET"
        " schedule_id = excluded.schedule_id, start_ba_cents = excluded.start_ba_cents,"
        " ma_step10_cents = excluded.ma_step10_cents,"
        " max_salary_cents = excluded.max_salary_cents, computed_at = excluded.computed_at"
    )
    # The website caches district pages; queue the districts touched so the review Worker purges
    # their cache tags (D-023).
    sql.append(
        f"INSERT INTO cache_purge_queue (district_id, queued_at) SELECT DISTINCT t.district_id,"
        f" {quote(stamp)} FROM ({touched}) t WHERE true"
        " ON CONFLICT (district_id) DO UPDATE SET queued_at = excluded.queued_at"
    )
    for table in STAGING:
        sql.append(f"DROP TABLE {table}")
    return sql
