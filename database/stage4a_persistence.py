from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from database.models import Stage4ARecord, Stage4ASupersession
from intelligence.stage4a.runtime import Stage4AResult


@dataclass(frozen=True)
class Stage4APersistenceReport:
    inserted_count: int
    duplicate_count: int


def persist_stage4a_result(
    result: Stage4AResult,
    session_factory: sessionmaker[Session],
) -> Stage4APersistenceReport:
    if not isinstance(result, Stage4AResult):
        raise TypeError("result must be a Stage4AResult")
    payload = result.to_dict()
    records: list[tuple[str, str, str]] = []

    for link in result.links:
        records.append(("entity-aspect-link", link.link_id, link.to_dict()))
    for observation in result.observations:
        records.append(("statement-observation", observation.observation_id, observation.to_dict()))
    for occurrence in result.competitor_occurrences:
        records.append(("competitor-occurrence", occurrence.occurrence_id, {
            "occurrence_id": occurrence.occurrence_id,
            "relation_id": occurrence.relation_id,
            "document_ref": occurrence.document_ref,
            "relation_type": occurrence.relation_type,
            "left_company_id": occurrence.left_company_id,
            "right_company_id": occurrence.right_company_id,
        }))

    inserted = 0
    duplicates = 0
    with session_factory.begin() as session:
        for kind, record_id, record_payload in records:
            existing = session.scalar(
                select(Stage4ARecord).where(Stage4ARecord.record_id == record_id)
            )
            if existing is not None:
                duplicates += 1
                continue
            session.add(Stage4ARecord(
                document_ref=result.document_ref,
                record_id=record_id,
                record_kind=kind,
                payload_json=__import__("json").dumps(
                    record_payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                ),
            ))
            inserted += 1
    return Stage4APersistenceReport(inserted, duplicates)


def persist_supersessions(
    supersessions: Iterable[object],
    session_factory: sessionmaker[Session],
) -> Stage4APersistenceReport:
    records = tuple(supersessions)
    inserted = duplicates = 0
    with session_factory.begin() as session:
        for item in records:
            if not hasattr(item, "supersession_id"):
                raise TypeError("supersession record has no supersession_id")
            existing = session.scalar(
                select(Stage4ASupersession).where(
                    Stage4ASupersession.supersession_id == item.supersession_id
                )
            )
            if existing is not None:
                duplicates += 1
                continue
            session.add(Stage4ASupersession(
                supersession_id=item.supersession_id,
                predecessor_observation_id=item.superseded_observation_id,
                successor_observation_id=item.replacement_observation_id,
                document_ref=item.document_ref,
                source_field=item.source_field,
                start=item.start,
                end=item.end,
                quote=item.quote,
                reason=item.supersession_reason,
                payload_json=__import__("json").dumps(
                    item.immutable_payload(), ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                ),
            ))
            inserted += 1
    return Stage4APersistenceReport(inserted, duplicates)


def persist_stage4a_result_with_supersessions(
    result: Stage4AResult,
    session_factory: sessionmaker[Session],
) -> Stage4APersistenceReport:
    """Persist output records and supersessions atomically."""
    records: list[tuple[str, str, dict[str, object]]] = []
    for link in result.links:
        records.append(("entity-aspect-link", link.link_id, link.to_dict()))
    for observation in result.observations:
        records.append(("statement-observation", observation.observation_id, observation.to_dict()))
    for occurrence in result.competitor_occurrences:
        records.append(("competitor-occurrence", occurrence.occurrence_id, {
            "occurrence_id": occurrence.occurrence_id,
            "relation_id": occurrence.relation_id,
            "document_ref": occurrence.document_ref,
            "relation_type": occurrence.relation_type,
            "left_company_id": occurrence.left_company_id,
            "right_company_id": occurrence.right_company_id,
        }))

    supersessions = tuple(result.supersessions)
    for item in supersessions:
        if not hasattr(item, "supersession_id") or not hasattr(item, "immutable_payload"):
            raise TypeError("supersession record is incomplete")

    inserted = duplicates = 0
    with session_factory.begin() as session:
        for kind, record_id, payload in records:
            existing = session.scalar(select(Stage4ARecord).where(Stage4ARecord.record_id == record_id))
            if existing is not None:
                duplicates += 1
                continue
            session.add(Stage4ARecord(
                document_ref=result.document_ref,
                record_id=record_id,
                record_kind=kind,
                payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ))
            inserted += 1
        for item in supersessions:
            existing = session.scalar(select(Stage4ASupersession).where(
                Stage4ASupersession.supersession_id == item.supersession_id
            ))
            if existing is not None:
                duplicates += 1
                continue
            session.add(Stage4ASupersession(
                supersession_id=item.supersession_id,
                predecessor_observation_id=item.superseded_observation_id,
                successor_observation_id=item.replacement_observation_id,
                document_ref=item.document_ref,
                source_field=item.source_field,
                start=item.start,
                end=item.end,
                quote=item.quote,
                reason=item.supersession_reason,
                payload_json=json.dumps(item.immutable_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ))
            inserted += 1
    return Stage4APersistenceReport(inserted, duplicates)


def persist_stage4a_result_with_supersessions_session(
    result: Stage4AResult,
    session: Session,
) -> Stage4APersistenceReport:
    """Persist Stage 4A records and supersessions into the caller's transaction."""
    inserted = 0
    duplicates = 0

    records: list[tuple[str, str, dict[str, object]]] = []
    for link in result.links:
        records.append(("entity-aspect-link", link.link_id, link.to_dict()))
    for observation in result.observations:
        records.append(("statement-observation", observation.observation_id, observation.to_dict()))
    for occurrence in result.competitor_occurrences:
        records.append(("competitor-occurrence", occurrence.occurrence_id, {
            "occurrence_id": occurrence.occurrence_id,
            "relation_id": occurrence.relation_id,
            "document_ref": occurrence.document_ref,
            "relation_type": occurrence.relation_type,
            "left_company_id": occurrence.left_company_id,
            "right_company_id": occurrence.right_company_id,
        }))

    for kind, record_id, payload in records:
        existing = session.scalar(select(Stage4ARecord).where(Stage4ARecord.record_id == record_id))
        if existing is not None:
            duplicates += 1
            continue
        session.add(Stage4ARecord(
            document_ref=result.document_ref,
            record_id=record_id,
            record_kind=kind,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
        ))
        inserted += 1

    for item in result.supersessions:
        if not hasattr(item, "supersession_id") or not hasattr(item, "immutable_payload"):
            raise TypeError("supersession record is incomplete")
        existing = session.scalar(select(Stage4ASupersession).where(
            Stage4ASupersession.supersession_id == item.supersession_id
        ))
        if existing is not None:
            duplicates += 1
            continue
        session.add(Stage4ASupersession(
            supersession_id=item.supersession_id,
            predecessor_observation_id=item.superseded_observation_id,
            successor_observation_id=item.replacement_observation_id,
            document_ref=item.document_ref,
            source_field=item.source_field,
            start=item.start,
            end=item.end,
            quote=item.quote,
            reason=item.supersession_reason,
            payload_json=json.dumps(item.immutable_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
        ))
        inserted += 1
    return Stage4APersistenceReport(inserted, duplicates)


def get_supersessions(
    document_ref: str,
    session_factory: sessionmaker[Session],
) -> tuple[Stage4ASupersession, ...]:
    with session_factory() as session:
        return tuple(session.scalars(
            select(Stage4ASupersession)
            .where(Stage4ASupersession.document_ref == document_ref)
            .order_by(Stage4ASupersession.supersession_id)
        ))


def replace_stage4a_record(
    record_id: str,
    record_kind: str,
    record_payload: dict[str, object],
    document_ref: str,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        existing = session.scalar(
            select(Stage4ARecord).where(Stage4ARecord.record_id == record_id)
        )
        if existing is None:
            raise LookupError(record_id)
        existing.record_kind = record_kind
        existing.document_ref = document_ref
        existing.payload_json = __import__("json").dumps(
            record_payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )


def delete_stage4a_record(record_id: str, session_factory: sessionmaker[Session]) -> bool:
    with session_factory.begin() as session:
        existing = session.scalar(
            select(Stage4ARecord).where(Stage4ARecord.record_id == record_id)
        )
        if existing is None:
            return False
        session.delete(existing)
        return True
