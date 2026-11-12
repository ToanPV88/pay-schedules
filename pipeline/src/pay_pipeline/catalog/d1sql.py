"""SQL for loading a :class:`Catalog` into D1 (schema: packages/db/migrations/0002_schema.sql).

The script is idempotent:

* states and districts are upserted by key (state code, NCES id); unchanged rows are not
  rewritten; a district keeps its slug unless it moved to another state;
* districts of this catalogue type missing from the new file are marked ``active = 0``, never
  deleted (PLAN Công đoạn 3, bước 6);
* neighbours of school districts are replaced as a whole.

Every statement stays under D1's 100 KB statement limit.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator, Sequence

from pay_pipeline.catalog.districts import Catalog, state_slug

MAX_STATEMENT_BYTES = 90_000
SqlValue = str | int | float | None


def quote(value: SqlValue) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        raise TypeError("Không dùng bool trong SQL; dùng 0/1")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return "'" + value.replace("'", "''") + "'"


def batched_insert(head: str, rows: Iterable[Sequence[SqlValue]], tail: str = "") -> Iterator[str]:
    """Yield ``head VALUES (...),(...) tail`` statements, each under the size limit."""
    batch: list[str] = []
    size = len(head) + len(tail) + 16
    for row in rows:
        values = "(" + ", ".join(quote(v) for v in row) + ")"
        if batch and size + len(values) + 2 > MAX_STATEMENT_BYTES:
            yield f"{head} VALUES {', '.join(batch)}{tail}"
            batch, size = [], len(head) + len(tail) + 16
        batch.append(values)
        size += len(values) + 2
    if batch:
        yield f"{head} VALUES {', '.join(batch)}{tail}"


DISTRICT_FIELDS = ("name", "state", "city", "county", "website", "enrollment", "lat", "lng")


def catalog_sql(catalog: Catalog, now: dt.datetime | None = None) -> list[str]:
    stamp = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    statements: list[str] = []

    statements += batched_insert(
        "INSERT INTO states (code, name, slug)",
        ((code, name, state_slug(name)) for code, name in sorted(catalog.states.items())),
        " ON CONFLICT (code) DO UPDATE SET name = excluded.name"
        " WHERE states.name IS NOT excluded.name",
    )

    changed = " OR ".join(f"districts.{f} IS NOT excluded.{f}" for f in DISTRICT_FIELDS)
    statements += batched_insert(
        "INSERT INTO districts (nces_id, name, slug, state, city, county, website, enrollment,"
        " lat, lng, active, employer_type, created_at, updated_at)",
        (
            (
                d.nces_id,
                d.name,
                d.slug,
                d.state,
                d.city,
                d.county,
                d.website,
                d.enrollment,
                d.lat,
                d.lng,
                1,
                "school_district",
                stamp,
                stamp,
            )
            for d in catalog.districts
        ),
        " ON CONFLICT (nces_id) DO UPDATE SET"
        " name = excluded.name, city = excluded.city, county = excluded.county,"
        " website = excluded.website, enrollment = excluded.enrollment,"
        " lat = excluded.lat, lng = excluded.lng, active = 1, updated_at = excluded.updated_at,"
        " slug = CASE WHEN districts.state IS NOT excluded.state THEN excluded.slug"
        " ELSE districts.slug END,"
        " state = excluded.state"
        f" WHERE districts.active = 0 OR {changed}",
    )

    statements.append("CREATE TABLE IF NOT EXISTS _import_nces_ids (nces_id TEXT PRIMARY KEY)")
    statements.append("DELETE FROM _import_nces_ids")
    statements += batched_insert(
        "INSERT INTO _import_nces_ids (nces_id)", ((d.nces_id,) for d in catalog.districts)
    )
    # Literal values only come from quote(); no user input reaches this SQL.
    statements.append(
        f"UPDATE districts SET active = 0, updated_at = {quote(stamp)}"  # noqa: S608
        " WHERE employer_type = 'school_district' AND nces_id IS NOT NULL AND active = 1"
        " AND nces_id NOT IN (SELECT nces_id FROM _import_nces_ids)"
    )

    statements.append(
        "CREATE TABLE IF NOT EXISTS _import_neighbors (a TEXT NOT NULL, b TEXT NOT NULL, km REAL)"
    )
    statements.append("DELETE FROM _import_neighbors")
    statements += batched_insert(
        "INSERT INTO _import_neighbors (a, b, km)",
        ((n.district, n.neighbor, n.distance_km) for n in catalog.neighbors),
    )
    statements.append(
        "DELETE FROM district_neighbors WHERE district_id IN"
        " (SELECT id FROM districts WHERE employer_type = 'school_district')"
    )
    statements.append(
        "INSERT INTO district_neighbors (district_id, neighbor_id, distance_km)"
        " SELECT a.id, b.id, n.km FROM _import_neighbors n"
        " JOIN districts a ON a.nces_id = n.a JOIN districts b ON b.nces_id = n.b"
    )
    statements.append("DROP TABLE _import_neighbors")
    statements.append("DROP TABLE _import_nces_ids")
    return statements


def render_sql(statements: Sequence[str]) -> str:
    oversize = [len(s.encode()) for s in statements if len(s.encode()) > 100_000]
    if oversize:
        raise ValueError(f"Câu lệnh vượt 100 KB: {oversize}")
    return ";\n".join(statements) + ";\n"
