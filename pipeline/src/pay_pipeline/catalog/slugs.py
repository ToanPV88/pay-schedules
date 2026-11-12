"""Stable URL slugs for districts: ``/{state}/{district-slug}`` (PLAN Công đoạn 3, bước 4).

Rules:

* A district that already has a slug keeps it forever (looked up by NCES id), even if its
  name changes, so published URLs never break.
* A new district gets ``slugify(name)``. If that is taken in the same state, the county is
  appended; if still taken, the NCES id is appended. Collisions are resolved in a fixed order
  (by NCES id), so a rerun on the same input gives the same slugs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
MAX_SLUG = 80  # matches the web route pattern


def slugify(text: str) -> str:
    """ASCII, lowercase, hyphen-separated. 'Cañon City R-1' -> 'canon-city-r-1'."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().replace("&", " and ")
    slug = _NON_ALNUM.sub("-", ascii_text).strip("-")
    if len(slug) > MAX_SLUG:
        slug = slug[:MAX_SLUG].rstrip("-")
    return slug


@dataclass(frozen=True)
class SlugInput:
    nces_id: str
    state: str
    name: str
    county: str | None


@dataclass(frozen=True)
class SlugResult:
    slugs: dict[str, str]
    """nces_id -> slug for every input."""
    disambiguated: list[tuple[str, str, str]]
    """(nces_id, base slug, final slug) for new slugs that needed a suffix."""


def assign_slugs(
    districts: Iterable[SlugInput],
    existing: Mapping[str, tuple[str, str]],
) -> SlugResult:
    """``existing`` maps nces_id -> (state, slug) already stored in the database."""
    rows = sorted(districts, key=lambda d: d.nces_id)
    taken: dict[str, set[str]] = {}
    for state, slug in existing.values():
        taken.setdefault(state, set()).add(slug)

    slugs: dict[str, str] = {}
    disambiguated: list[tuple[str, str, str]] = []
    pending: list[SlugInput] = []
    for d in rows:
        kept = existing.get(d.nces_id)
        if kept is not None and kept[0] == d.state:
            slugs[d.nces_id] = kept[1]
        else:
            pending.append(d)

    base_counts: dict[tuple[str, str], int] = {}
    for d in pending:
        key = (d.state, slugify(d.name))
        base_counts[key] = base_counts.get(key, 0) + 1

    for d in pending:
        state_taken = taken.setdefault(d.state, set())
        base = slugify(d.name) or slugify(d.nces_id)
        candidates = []
        if base_counts[(d.state, base)] == 1:
            candidates.append(base)
        if d.county:
            candidates.append(slugify(f"{base} {d.county}"))
        candidates.append(slugify(f"{base} {d.nces_id}"))
        chosen = next((c for c in candidates if c and c not in state_taken), None)
        if chosen is None:  # pragma: no cover - the NCES id makes the last candidate unique
            raise ValueError(f"Không tạo được slug duy nhất cho {d.nces_id}")
        state_taken.add(chosen)
        slugs[d.nces_id] = chosen
        if chosen != base:
            disambiguated.append((d.nces_id, base, chosen))
    return SlugResult(slugs=slugs, disambiguated=disambiguated)
