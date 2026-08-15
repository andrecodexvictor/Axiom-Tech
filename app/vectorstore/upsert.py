"""Provider-neutral planning for idempotent vector upserts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping


@dataclass(frozen=True)
class UpsertPlan:
    chunks: List[Dict[str, Any]]
    to_write: List[Dict[str, Any]]
    current_ids_by_source: Dict[str, set[str]]
    inserted: int
    updated: int
    unchanged: int


def build_upsert_plan(
    chunks: List[Dict[str, Any]],
    existing_by_id: Mapping[str, Any],
    *,
    force: bool,
    is_unchanged: Callable[[Any, Dict[str, Any]], bool],
) -> UpsertPlan:
    to_write: List[Dict[str, Any]] = []
    current_ids_by_source: Dict[str, set[str]] = {}
    inserted = updated = unchanged = 0

    for chunk in chunks:
        identifier = chunk["id"]
        source_key = str(chunk["metadata"].get("source_key", ""))
        current_ids_by_source.setdefault(source_key, set()).add(identifier)
        prior = existing_by_id.get(identifier)
        if prior is None:
            inserted += 1
            to_write.append(chunk)
        elif not force and is_unchanged(prior, chunk):
            unchanged += 1
        else:
            updated += 1
            to_write.append(chunk)

    return UpsertPlan(
        chunks=chunks,
        to_write=to_write,
        current_ids_by_source=current_ids_by_source,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
    )
