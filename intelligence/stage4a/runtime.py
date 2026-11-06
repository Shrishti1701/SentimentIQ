from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
import re
from typing import Iterable, Literal

from intelligence.contracts import AnalysisInput, EvidenceSpan as Stage1EvidenceSpan
from intelligence.entity_contracts import (
    DeterministicIdFactory,
    EntityMention,
    EntityResolutionResult,
)
from intelligence.entity_extractor import extract_entity_mentions
from intelligence.synthetic_registry import SyntheticRegistry
from intelligence.stage4a.contracts import (
    CompanyCompetitorEvidenceAssociation,
    CompanyCompetitorProvenance,
    CompanyCompetitorRelationOccurrence,
    EvidenceSpan,
    LinkAttempt,
    resolve_alias,
)
from intelligence.stage4a.runtime_support import process_publication_time


AspectField = Literal["title", "body"]
UnknownReason = Literal[
    "unlisted_taxonomy_concept",
    "ambiguous_metric",
    "insufficient_specificity",
    "unsupported_alias",
    "multi_aspect_phrase",
]


def _stable_id(kind: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return f"{kind}:v1:{hashlib.sha256(encoded).hexdigest()}"


def _span(field: AspectField, text: str, start: int, end: int) -> Stage1EvidenceSpan:
    return Stage1EvidenceSpan(field, start, end, text[start:end], "aspect")


@dataclass(frozen=True)
class RuntimeAspectMention:
    mention_id: str
    document_ref: str
    aspect_code: str
    label: str
    field: AspectField
    start: int
    end: int
    evidence: Stage1EvidenceSpan
    unknown_reason: UnknownReason | None = None
    taxonomy_version: str = "stage4a-taxonomy-v1"
    payload_version: Literal[1] = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "mention_id": self.mention_id,
            "document_ref": self.document_ref,
            "aspect_code": self.aspect_code,
            "label": self.label,
            "field": self.field,
            "start": self.start,
            "end": self.end,
            "evidence_quote": self.evidence.quote,
            "unknown_reason": self.unknown_reason,
            "taxonomy_version": self.taxonomy_version,
            "payload_version": self.payload_version,
        }


@dataclass(frozen=True)
class RuntimeEntityAspectLink:
    link_id: str
    document_ref: str
    entity_mention_id: str
    resolution_result_id: str
    resolved_company_id: str
    aspect_mention_id: str
    aspect_code: str
    attribution_role: Literal["subject", "possessive", "coordinated_subject"]
    entity_evidence: Stage1EvidenceSpan
    aspect_evidence: Stage1EvidenceSpan
    relationship_evidence: Stage1EvidenceSpan
    observation_ids: tuple[str, ...] = ()
    linker_version: str = "stage4a-linker-v1"
    payload_version: Literal[1] = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "link_id": self.link_id,
            "document_ref": self.document_ref,
            "entity_mention_id": self.entity_mention_id,
            "resolution_result_id": self.resolution_result_id,
            "resolved_company_id": self.resolved_company_id,
            "aspect_mention_id": self.aspect_mention_id,
            "aspect_code": self.aspect_code,
            "attribution_role": self.attribution_role,
            "observation_ids": self.observation_ids,
            "linker_version": self.linker_version,
            "payload_version": self.payload_version,
        }


@dataclass(frozen=True)
class RuntimeStatementObservation:
    observation_id: str
    document_ref: str
    source_field: AspectField
    start: int
    end: int
    evidence_quote: str
    observation_type: Literal["statement", "comparison", "contrast", "conditional"]
    negation: bool
    modality: str
    uncertainty: str
    temporal_reference: str
    forward_looking: bool
    conditionality: str
    aspect_mention_ids: tuple[str, ...]
    link_ids: tuple[str, ...]
    payload_version: Literal[1] = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "document_ref": self.document_ref,
            "source_field": self.source_field,
            "start": self.start,
            "end": self.end,
            "evidence_quote": self.evidence_quote,
            "observation_type": self.observation_type,
            "negation": self.negation,
            "modality": self.modality,
            "uncertainty": self.uncertainty,
            "temporal_reference": self.temporal_reference,
            "forward_looking": self.forward_looking,
            "conditionality": self.conditionality,
            "aspect_mention_ids": self.aspect_mention_ids,
            "link_ids": self.link_ids,
            "payload_version": self.payload_version,
        }


@dataclass(frozen=True)
class Stage4AResult:
    document_ref: str
    aspect_mentions: tuple[RuntimeAspectMention, ...]
    entity_mentions: tuple[EntityMention, ...]
    resolutions: tuple[EntityResolutionResult, ...]
    links: tuple[RuntimeEntityAspectLink, ...]
    observations: tuple[RuntimeStatementObservation, ...]
    link_attempts: tuple[object, ...]
    competitor_occurrences: tuple[CompanyCompetitorRelationOccurrence, ...]
    supersessions: tuple[object, ...] = ()
    publication_time: object | None = None

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "document_ref": self.document_ref,
            "aspect_mentions": [item.to_dict() for item in self.aspect_mentions            ],
            "supersessions": [
                item.to_dict() for item in self.supersessions
                if hasattr(item, "to_dict")
            ],
            "publication_time": (
                {
                    "raw_timestamp": self.publication_time.raw_timestamp,
                    "utc_instant": self.publication_time.utc_instant,
                    "timezone_status": self.publication_time.timezone_status,
                    "timezone_identifier": self.publication_time.timezone_identifier,
                }
                if self.publication_time is not None else None
            ),
            "entity_mentions": [self._mention_dict(item) for item in self.entity_mentions],
            "resolutions": [asdict(item) for item in self.resolutions],
            "links": [item.to_dict() for item in self.links],
            "observations": [item.to_dict() for item in self.observations],
            "link_attempts": [
                {
                    "attempt_id": item.attempt_id,
                    "document_ref": item.document_ref,
                    "entity_mention_id": item.entity_mention_id,
                    "status": item.status,
                    "ambiguity_basis": item.ambiguity_basis,
                    "reason_code": item.reason_code,
                }
                for item in self.link_attempts
            ],
            "competitor_occurrences": [self._occurrence_dict(item) for item in self.competitor_occurrences],
        }

    @staticmethod
    def _mention_dict(item: EntityMention) -> dict[str, object]:
        return {
            "mention_id": item.mention_id,
            "document_ref": item.document_ref,
            "surface_text": item.surface_text,
            "field": item.field,
            "start": item.start,
            "end": item.end,
        }

    @staticmethod
    def _occurrence_dict(item: CompanyCompetitorRelationOccurrence) -> dict[str, object]:
        return {
            "occurrence_id": item.occurrence_id,
            "relation_id": item.relation_id,
            "document_ref": item.document_ref,
            "relation_type": item.relation_type,
            "left_company_id": item.left_company_id,
            "right_company_id": item.right_company_id,
        }


_UNKNOWN_TERM_RE = re.compile(
    r"(?i)(?:market share|customer satisfaction|environmental score|unknown metric)"
)


def extract_aspect_mentions(
    document: AnalysisInput,
) -> tuple[RuntimeAspectMention, ...]:
    sources = (( "title", document.title), ("body", document.body))
    results: list[RuntimeAspectMention] = []
    alias_terms = tuple(sorted((
        "profitability", "profit", "net profit", "operating profit",
        "sales growth", "growth in sales", "sales grew", "business growth",
        "revenue", "debt", "debt repayment", "repaid debt",
        "debt refinancing", "refinancing", "operating expenses",
        "employee expenses", "management change", "management",
        "regulatory developments", "regulatory development",
        "profit margin", "operating margin", "gross margin", "net margin",
        "margin",
    ), key=lambda value: (-len(value), value)))
    for field, source in sources:
        if source is None:
            continue
        occupied: list[tuple[int, int]] = []
        for alias in alias_terms:
            for match in re.finditer(re.escape(alias), source, flags=re.IGNORECASE):
                span = (match.start(), match.end())
                if any(match.start() < end and match.end() > start for start, end in occupied):
                    continue
                code = resolve_alias(match.group(0))
                if code is None:
                    continue
                occupied.append(span)
                label = match.group(0)
                payload = {
                    "document_ref": document.document_ref,
                    "aspect_code": code,
                    "field": field,
                    "start": match.start(),
                    "end": match.end(),
                    "taxonomy_version": "stage4a-taxonomy-v1",
                }
                results.append(RuntimeAspectMention(
                    mention_id=_stable_id("aspect-mention", payload),
                    document_ref=document.document_ref,
                    aspect_code=code,
                    label=label,
                    field=field,
                    start=match.start(),
                    end=match.end(),
                    evidence=_span(field, source, match.start(), match.end()),
                ))

        for match in _UNKNOWN_TERM_RE.finditer(source):
            payload = {
                "document_ref": document.document_ref,
                "aspect_code": "unknown_aspect",
                "field": field,
                "start": match.start(),
                "end": match.end(),
                "taxonomy_version": "stage4a-taxonomy-v1",
            }
            results.append(RuntimeAspectMention(
                mention_id=_stable_id("aspect-mention", payload),
                document_ref=document.document_ref,
                aspect_code="unknown_aspect",
                label=match.group(0),
                field=field,
                start=match.start(),
                end=match.end(),
                evidence=_span(field, source, match.start(), match.end()),
                unknown_reason="unlisted_taxonomy_concept",
            ))
    return tuple(sorted(results, key=lambda item: (item.field, item.start, item.end, item.aspect_code)))


def _relationship_evidence(
    document: AnalysisInput, field: AspectField, start: int, end: int
) -> Stage1EvidenceSpan:
    source = document.title if field == "title" else document.body
    if source is None:
        raise ValueError("evidence field is absent")
    left = max(0, start - 20)
    right = min(len(source), end + 20)
    while left > 0 and source[left] not in ".!?":
        left -= 1
    while right < len(source) and source[right] not in ".!?":
        right += 1
    quote = source[left:right].strip()
    quote_start = source.find(quote, left, right + 1)
    if quote_start < 0:
        quote_start = left
    quote_end = quote_start + len(quote)
    return Stage1EvidenceSpan(field, quote_start, quote_end, quote, "relation")


class Stage4APipeline:
    def __init__(self, registry: SyntheticRegistry | None, resolver_version: str = "stage4a-resolver-v1"):
        if registry is not None and not isinstance(registry, SyntheticRegistry):
            raise TypeError("registry must be a SyntheticRegistry")
        self.registry = registry
        self.resolver_version = resolver_version
        self._factory = DeterministicIdFactory()

    def process(
        self,
        document: AnalysisInput,
        *,
        upstream_mentions: tuple[EntityMention, ...] | None = None,
        upstream_resolutions: tuple[EntityResolutionResult, ...] | None = None,
        timezone_authorities: frozenset[str] = frozenset(),
        timezone_identifier: str | None = None,
        supersessions: tuple[object, ...] = (),
    ) -> Stage4AResult:
        if not isinstance(document, AnalysisInput):
            raise TypeError("document must be an AnalysisInput")
        if (upstream_mentions is None) != (upstream_resolutions is None):
            raise ValueError("upstream mentions and resolutions must be supplied together")
        if upstream_mentions is None:
            if not isinstance(self.registry, SyntheticRegistry):
                raise RuntimeError(
                    "production Stage 4A processing requires upstream Stage 3 resolutions"
                )
            mentions = list(extract_entity_mentions(document, extractor_version="stage4a-extractor-v1"))
            mentions.extend(self._registry_mentions(document, mentions))
        else:
            if not isinstance(upstream_mentions, tuple) or not isinstance(upstream_resolutions, tuple):
                raise TypeError("upstream mentions and resolutions must be tuples")
            if any(not isinstance(item, EntityMention) for item in upstream_mentions):
                raise TypeError("upstream_mentions contains an invalid entity mention")
            if any(not isinstance(item, EntityResolutionResult) for item in upstream_resolutions):
                raise TypeError("upstream_resolutions contains an invalid resolution result")
            mentions = list(upstream_mentions)
        resolutions: list[EntityResolutionResult] = []
        effective_time = None
        if document.published_at is not None and document.timezone_status.startswith("verified_"):
            from intelligence.contracts import verified_effective_time_from_input
            effective_time = verified_effective_time_from_input(document)

        if upstream_resolutions is None:
            for mention in mentions:
                resolutions.append(self.registry.resolve_result(
                    mention,
                    resolver_version=self.resolver_version,
                    effective_time=effective_time,
                    id_factory=self._factory,
                ))
        else:
            by_mention = {item.mention_id: item for item in upstream_resolutions}
            if len(by_mention) != len(upstream_resolutions):
                raise ValueError("duplicate upstream resolution results are forbidden")
            for mention in mentions:
                result = by_mention.get(mention.mention_id)
                if result is None:
                    continue
                if result.document_ref != document.document_ref or result.mention_id != mention.mention_id:
                    raise ValueError("upstream resolution does not match its document mention")
                resolutions.append(result)
        aspects = extract_aspect_mentions(document)

        link_attempts: list[LinkAttempt] = []
        for result in resolutions:
            if result.status == "ambiguous":
                attempt_payload = {
                    "document_ref": document.document_ref,
                    "entity_mention_id": result.mention_id,
                    "status": "ambiguous",
                    "ambiguity_basis": "resolved_company",
                }
                attempt = LinkAttempt(
                    attempt_id=_stable_id("stage4a-link-attempt", attempt_payload),
                    document_ref=document.document_ref,
                    entity_mention_id=result.mention_id,
                    status="ambiguous",
                    ambiguity_basis="resolved_company",
                    reason_code="resolved_company_ambiguous",
                    candidate_entity_ids=(),
                    candidate_resolved_company_ids=tuple(sorted(
                        item.entity_id for item in result.candidates
                    )),
                    candidate_attribution_roles=(),
                    relationship_evidence_required=False,
                )
                attempt.validate()
                link_attempts.append(attempt)
            elif result.status == "unresolved" and any(
                item.aspect_code != "unknown_aspect" for item in aspects
            ):
                attempt_payload = {
                    "document_ref": document.document_ref,
                    "entity_mention_id": result.mention_id,
                    "status": "abstained",
                }
                attempt = LinkAttempt(
                    attempt_id=_stable_id("stage4a-link-attempt", attempt_payload),
                    document_ref=document.document_ref,
                    entity_mention_id=result.mention_id,
                    status="abstained",
                    ambiguity_basis="none",
                    reason_code="insufficient_evidence",
                    candidate_entity_ids=(),
                    candidate_resolved_company_ids=(),
                    candidate_attribution_roles=(),
                    relationship_evidence_required=False,
                )
                attempt.validate()
                link_attempts.append(attempt)

        links: list[RuntimeEntityAspectLink] = []
        resolved_results = {
            result.mention_id: result
            for result in resolutions
            if result.status == "resolved" and result.selected_entity_id is not None
        }
        mentions_by_id = {item.mention_id: item for item in mentions}
        for aspect in aspects:
            if aspect.aspect_code == "unknown_aspect":
                continue
            same_field_mentions = [item for item in mentions if item.field == aspect.field]
            for mention in same_field_mentions:
                result = resolved_results.get(mention.mention_id)
                if result is None:
                    continue
                source = document.title if aspect.field == "title" else document.body
                if source is None:
                    continue
                # Attribution is accepted only when the company mention and aspect
                # occur in the same conservative sentence/field.
                sentence_start = max(source.rfind(".", 0, min(mention.start, aspect.start)) + 1, 0)
                sentence_start_aspect = max(source.rfind(".", 0, aspect.start) + 1, 0)
                sentence_start_mention = max(source.rfind(".", 0, mention.start) + 1, 0)
                if sentence_start_aspect != sentence_start_mention:
                    continue
                sentence_end_candidates = [
                    position for position in (
                        source.find(".", max(mention.end, aspect.end)),
                        source.find("!", max(mention.end, aspect.end)),
                        source.find("?", max(mention.end, aspect.end)),
                    ) if position >= 0
                ]
                sentence_end = min(sentence_end_candidates, default=len(source))
                if not (sentence_start <= min(mention.start, aspect.start) and max(mention.end, aspect.end) <= sentence_end):
                    continue
                role: Literal["subject", "possessive", "coordinated_subject"] = "coordinated_subject" if re.search(r"\band\b", source[sentence_start:max(mention.start, aspect.start)], re.I) else "subject"
                payload = {
                    "document_ref": document.document_ref,
                    "entity_mention_id": mention.mention_id,
                    "resolution_result_id": result.resolution_id,
                    "resolved_company_id": result.selected_entity_id,
                    "aspect_mention_id": aspect.mention_id,
                    "aspect_code": aspect.aspect_code,
                }
                links.append(RuntimeEntityAspectLink(
                    link_id=_stable_id("entity-aspect-link", payload),
                    document_ref=document.document_ref,
                    entity_mention_id=mention.mention_id,
                    resolution_result_id=result.resolution_id,
                    resolved_company_id=result.selected_entity_id,
                    aspect_mention_id=aspect.mention_id,
                    aspect_code=aspect.aspect_code,
                    attribution_role=role,
                    entity_evidence=Stage1EvidenceSpan(
                        mention.field, mention.start, mention.end, mention.surface_text, "entity"
                    ),
                    aspect_evidence=aspect.evidence,
                    relationship_evidence=_relationship_evidence(
                        document, aspect.field, mention.start, mention.end
                    ),
                ))

        observations = self._observations(document, aspects, links)
        observation_ids_by_link: dict[str, list[str]] = {}
        for observation in observations:
            for link_id in observation.link_ids:
                observation_ids_by_link.setdefault(link_id, []).append(observation.observation_id)
        links = [
            replace(link, observation_ids=tuple(sorted(observation_ids_by_link.get(link.link_id, ()))))
            for link in links
        ]
        competitor_occurrences = self._competitor_occurrences(document, mentions, resolutions)
        return Stage4AResult(
            document_ref=document.document_ref,
            aspect_mentions=aspects,
            entity_mentions=tuple(mentions),
            resolutions=tuple(resolutions),
            links=tuple(sorted(links, key=lambda item: item.link_id)),
            observations=observations,
            link_attempts=tuple(sorted(link_attempts, key=lambda item: item.attempt_id)),
            competitor_occurrences=competitor_occurrences,
            supersessions=supersessions,
            publication_time=process_publication_time(
                document,
                timezone_authorities=timezone_authorities,
                timezone_identifier=timezone_identifier,
            ),
        )

    def _registry_mentions(
        self,
        document: AnalysisInput,
        extracted: list[EntityMention],
    ) -> list[EntityMention]:
        from processing.cleaner import normalize_document
        normalized = normalize_document(document)
        occupied = {(item.field, item.start, item.end) for item in extracted}
        results: list[EntityMention] = []
        search_names: dict[str, str] = {}
        for company in self.registry.companies.values():
            search_names[company.legal_name.casefold()] = company.legal_name
            for alias, _validity, _provenance in company.aliases:
                search_names[alias.casefold()] = alias
        for field in ("title", "body"):
            source = getattr(document, field)
            if source is None:
                continue
            for name_key, display in sorted(search_names.items(), key=lambda item: (-len(item[1]), item[1])):
                start = 0
                while True:
                    start = source.casefold().find(name_key, start)
                    if start < 0:
                        break
                    end = start + len(display)
                    key = (field, start, end)
                    if key not in occupied and not any(
                        field == other_field and start < other_end and end > other_start
                        for other_field, other_start, other_end in occupied
                    ):
                        evidence = Stage1EvidenceSpan(
                            field, start, end, source[start:end], "entity"
                        )
                        mention_id = self._factory.mention_id(
                            document_ref=document.document_ref,
                            field=field,
                            start=start,
                            end=end,
                            observation_kind="organization_name_candidate",
                            security_namespace=None,
                            extractor_version="stage4a-registry-mention-v1",
                        )
                        item = EntityMention(
                            mention_id,
                            document_ref=document.document_ref,
                            surface_text=source[start:end],
                            field=field,
                            start=start,
                            end=end,
                            observation_kind="organization_name_candidate",
                            evidence=evidence,
                            extractor_version="stage4a-registry-mention-v1",
                        )
                        results.append(item)
                        occupied.add(key)
                    start += max(1, len(name_key))
        return results

    def _observations(
        self,
        document: AnalysisInput,
        aspects: tuple[RuntimeAspectMention, ...],
        links: list[RuntimeEntityAspectLink],
    ) -> tuple[RuntimeStatementObservation, ...]:
        observations: list[RuntimeStatementObservation] = []
        for aspect in aspects:
            source = document.title if aspect.field == "title" else document.body
            if source is None:
                continue
            linked_ids = tuple(sorted(link.link_id for link in links if link.aspect_mention_id == aspect.mention_id))
            start = max(0, source.rfind(".", 0, aspect.start) + 1)
            end_candidates = [position for position in (
                source.find(".", aspect.end), source.find("!", aspect.end), source.find("?", aspect.end)
            ) if position >= 0]
            end = min(end_candidates, default=len(source))
            quote = source[start:end].strip()
            quote_start = source.find(quote, start, end + 1)
            if quote_start < 0:
                quote_start = start
            payload = {
                "document_ref": document.document_ref,
                "source_field": aspect.field,
                "start": quote_start,
                "end": quote_start + len(quote),
                "aspect_mention_ids": (aspect.mention_id,),
                "link_ids": linked_ids,
            }
            observations.append(RuntimeStatementObservation(
                observation_id=_stable_id("statement-observation", payload),
                document_ref=document.document_ref,
                source_field=aspect.field,
                start=quote_start,
                end=quote_start + len(quote),
                evidence_quote=quote,
                observation_type="contrast" if re.search(r"\b(?:but|whereas)\b", quote, re.I) else "comparison" if re.search(r"\b(?:versus|compared with)\b", quote, re.I) else "statement",
                negation=bool(re.search(r"\b(?:not|never|no longer)\b", quote, re.I)),
                modality="possibility" if re.search(r"\b(?:may|might)\b", quote, re.I) else "expectation" if re.search(r"\b(?:expects?|expected|anticipates?)\b", quote, re.I) else "none",
                uncertainty="modal" if re.search(r"\b(?:may|might)\b", quote, re.I) else "none",
                temporal_reference="future" if re.search(r"\b(?:will|next year)\b", quote, re.I) else "past" if re.search(r"\b(?:was|were|reported)\b", quote, re.I) else "present",
                forward_looking=bool(re.search(r"\b(?:will|next year)\b", quote, re.I)),
                conditionality="conditional" if re.search(r"\b(?:if|unless)\b", quote, re.I) else "none",
                aspect_mention_ids=(aspect.mention_id,),
                link_ids=linked_ids,
            ))
        return tuple(sorted(observations, key=lambda item: item.observation_id))

    def _competitor_occurrences(
        self,
        document: AnalysisInput,
        mentions: tuple[EntityMention, ...],
        resolutions: tuple[EntityResolutionResult, ...],
    ) -> tuple[CompanyCompetitorRelationOccurrence, ...]:
        resolved = [
            result for result in resolutions
            if result.status == "resolved" and result.selected_entity_id is not None
        ]
        if len(resolved) < 2:
            return ()
        occurrences: list[CompanyCompetitorRelationOccurrence] = []
        mention_by_id = {item.mention_id: item for item in mentions}
        for field in ("title", "body"):
            source = getattr(document, field)
            if source is None or not re.search(r"\b(?:competitor|peer|competitors|versus|rival)\b", source, re.I):
                continue
            for match in re.finditer(r"(?i)\b(?:competitor|peer|competitors|versus|rival)\b", source):
                endpoints = [
                    result.selected_entity_id
                    for result in resolved
                    if result.document_ref == document.document_ref
                    and result.mention_id in mention_by_id
                    and mention_by_id[result.mention_id].field == field
                ]
                endpoints = sorted(set(endpoints))
                if len(endpoints) != 2:
                    continue
                left, right = endpoints[:2]
                provenance_items = []
                associations = []
                for result in resolved:
                    if result.selected_entity_id not in endpoints:
                        continue
                    mention = mention_by_id[result.mention_id]
                    p = CompanyCompetitorProvenance(
                        document_ref=document.document_ref,
                        resolved_company_id=result.selected_entity_id,
                        company_mention_id=mention.mention_id,
                        resolution_result_id=result.resolution_id,
                    )
                    provenance_items.append(p)
                    associations.append(CompanyCompetitorEvidenceAssociation(
                        p.resolved_company_id,
                        p.company_mention_id,
                        p.resolution_result_id,
                        EvidenceSpan(field=field, start=mention.start, end=mention.end, quote=mention.surface_text),
                    ))
                relation_payload = {"left": left, "right": right, "relation_type": "competitor"}
                relation_id = _stable_id("company-competitor-relation", relation_payload)
                quote_start = max(0, source.rfind(".", 0, match.start()) + 1)
                quote_end_candidates = [p for p in (source.find(".", match.end()), source.find("!", match.end()), source.find("?", match.end())) if p >= 0]
                quote_end = min(quote_end_candidates, default=len(source))
                quote = source[quote_start:quote_end].strip()
                quote_start = source.find(quote, quote_start, quote_end + 1)
                if quote_start < 0:
                    quote_start = max(0, match.start() - len(left))
                occurrence = CompanyCompetitorRelationOccurrence(
                    occurrence_id=_stable_id("company-relation-occurrence", {
                        "document_ref": document.document_ref,
                        "relation_id": relation_id,
                        "source_field": field,
                        "start": quote_start,
                        "end": quote_start + len(quote),
                        "relation_type": "competitor",
                    }),
                    relation_id=relation_id,
                    document_ref=document.document_ref,
                    source_field=field,
                    start=quote_start,
                    end=quote_start + len(quote),
                    quote=quote,
                    relation_type="competitor",
                    left_company_id=left,
                    right_company_id=right,
                    provenance=tuple(provenance_items),
                    evidence_associations=tuple(associations),
                )
                try:
                    occurrence.validate(
                        source=source,
                        mention_companies={
                            item.company_mention_id: item.resolved_company_id
                            for item in provenance_items
                        },
                        resolution_pairs={
                            item.resolution_id: (
                                item.mention_id,
                                item.selected_entity_id,
                            )
                            for item in resolved
                        },
                    )
                except ValueError:
                    continue
                occurrences.append(occurrence)
        return tuple(sorted(occurrences, key=lambda item: item.occurrence_id))


@dataclass(frozen=True)
class LegacyAdapterResult:
    records: tuple[object, ...]
    unavailable: tuple[object, ...]


def adapt_legacy_comparison(
    *,
    document_ref: str,
    legacy_id: str,
    entity_ref: str | None,
    aspect_ref: str | None,
    evidence_quote: str | None,
) -> LegacyAdapterResult:
    if evidence_quote is None or not evidence_quote.strip():
        unavailable = ({"legacy_id": legacy_id, "reason": "missing_evidence"},)
        return LegacyAdapterResult((), unavailable)
    if not entity_ref or not aspect_ref:
        unavailable = ({"legacy_id": legacy_id, "reason": "missing_relation_evidence"},)
        return LegacyAdapterResult((), unavailable)
    record = {
        "document_ref": document_ref,
        "legacy_id": legacy_id,
        "observation_type": "comparison",
        "entity_ref": entity_ref,
        "aspect_ref": aspect_ref,
        "evidence_quote": evidence_quote,
    }
    return LegacyAdapterResult((record,), ())


def adapt_legacy_competitor(
    *,
    document_ref: str,
    legacy_id: str,
    left_company_id: str | None,
    right_company_id: str | None,
    evidence_quote: str | None,
) -> LegacyAdapterResult:
    ids = (left_company_id, right_company_id)
    if any(item is None or not item.startswith("COMPANY:") for item in ids):
        return LegacyAdapterResult((), ({"legacy_id": legacy_id, "reason": "missing_resolved_endpoints"},))
    if left_company_id == right_company_id or evidence_quote is None or not evidence_quote.strip():
        return LegacyAdapterResult((), ({"legacy_id": legacy_id, "reason": "insufficient_competitor_evidence"},))
    return LegacyAdapterResult(({
        "document_ref": document_ref,
        "legacy_id": legacy_id,
        "relation_type": "competitor",
        "left_company_id": left_company_id,
        "right_company_id": right_company_id,
        "evidence_quote": evidence_quote,
    }), ())
