from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from database.stage4a_persistence import persist_stage4a_result_with_supersessions
from intelligence.contracts import AnalysisInput
from intelligence.entity_contracts import EntityMention, EntityResolutionResult
from intelligence.stage4a.runtime import Stage4APipeline, Stage4AResult


class Stage4AService:
    def __init__(
        self,
        pipeline: Stage4APipeline,
        session_factory: sessionmaker[Session],
    ) -> None:
        if not isinstance(pipeline, Stage4APipeline):
            raise TypeError("pipeline must be Stage4APipeline")
        self.pipeline = pipeline
        self.session_factory = session_factory

    def process_and_persist(
        self,
        document: AnalysisInput,
        *,
        upstream_mentions: tuple[EntityMention, ...],
        upstream_resolutions: tuple[EntityResolutionResult, ...],
        timezone_authorities: frozenset[str] = frozenset(),
        timezone_identifier: str | None = None,
        supersessions: tuple[object, ...] = (),
    ) -> Stage4AResult:
        result = self.pipeline.process(
            document,
            upstream_mentions=upstream_mentions,
            upstream_resolutions=upstream_resolutions,
            timezone_authorities=timezone_authorities,
            timezone_identifier=timezone_identifier,
            supersessions=supersessions,
        )
        persist_stage4a_result_with_supersessions(result, self.session_factory)
        return result
