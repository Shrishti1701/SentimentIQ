from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from intelligence.contracts import AnalysisInput
from intelligence.stage4a.contracts import canonical_utc


@dataclass(frozen=True)
class RuntimePublicationTime:
    raw_timestamp: str | None
    utc_instant: str | None
    timezone_status: str
    timezone_identifier: str | None


def process_publication_time(
    document: AnalysisInput,
    *,
    timezone_authorities: frozenset[str] = frozenset(),
    timezone_identifier: str | None = None,
) -> RuntimePublicationTime:
    raw = document.published_at_raw
    status = document.timezone_status
    if raw is None:
        return RuntimePublicationTime(None, None, status, None)
    if status == "unknown":
        return RuntimePublicationTime(raw, None, status, None)
    if status not in ("claimed", "verified", "verified_ietf", "verified_source"):
        return RuntimePublicationTime(raw, None, status, None)
    if status.startswith("verified_"):
        base_status = "verified"
    else:
        base_status = status
    if base_status == "claimed" and timezone_identifier not in timezone_authorities:
        return RuntimePublicationTime(raw, None, status, timezone_identifier)
    if timezone_identifier is None:
        return RuntimePublicationTime(raw, None, status, None)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_identifier))
        utc = canonical_utc(parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
    except ValueError:
        return RuntimePublicationTime(raw, None, status, timezone_identifier)
    return RuntimePublicationTime(raw, utc, status, timezone_identifier)


@dataclass(frozen=True)
class EvidenceSupersessionConflict:
    conflict_id: str
    supersession_ids: tuple[str, ...]
    reason: str


def validate_supersession(
    *,
    supersession_id: str,
    predecessor_observation_id: str,
    successor_observation_id: str,
) -> None:
    if not supersession_id.strip():
        raise ValueError("supersession_id must be non-empty")
    if predecessor_observation_id == successor_observation_id:
        raise ValueError("supersession self-reference is forbidden")


def find_supersession_conflicts(
    edges: tuple[tuple[str, str, str], ...],
) -> tuple[EvidenceSupersessionConflict, ...]:
    by_predecessor: dict[str, list[str]] = {}
    for supersession_id, predecessor, successor in edges:
        validate_supersession(
            supersession_id=supersession_id,
            predecessor_observation_id=predecessor,
            successor_observation_id=successor,
        )
        by_predecessor.setdefault(predecessor, []).append(supersession_id)
    conflicts = []
    for predecessor in sorted(by_predecessor):
        ids = tuple(sorted(set(by_predecessor[predecessor])))
        if len(ids) > 1:
            conflicts.append(EvidenceSupersessionConflict(
                conflict_id=f"supersession-conflict:v1:{predecessor}:{'+'.join(ids)}",
                supersession_ids=ids,
                reason="multiple_successors_for_predecessor",
            ))
    return tuple(conflicts)
