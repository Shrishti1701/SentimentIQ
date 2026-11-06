"""Deterministic, resolution-independent entity mention extraction.

The rules in this module identify textual candidates only. They do not consult
the entity registry or determine that a mention names a particular company.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import unicodedata
from typing import Literal

from intelligence.contracts import AnalysisInput, EvidenceSpan, NormalizedDocument
from intelligence.entity_contracts import DeterministicIdFactory, EntityMention, validate_entity_source
from processing.cleaner import normalize_document, normalize_text
from processing.text_alignment import map_normalized_span


logger = logging.getLogger(__name__)
Field = Literal["title", "body"]
ObservationKind = Literal[
    "organization_name_candidate",
    "abbreviation_candidate",
    "security_identifier_candidate",
    "other_company_reference",
]
Namespace = Literal["NSE", "BSE", "ISIN"]

_KIND_ORDER = {
    "organization_name_candidate": 0,
    "abbreviation_candidate": 1,
    "security_identifier_candidate": 2,
    "other_company_reference": 3,
}
_SUFFIX_RE = re.compile(
    r"(?i:Private\s+Limited|Pvt\.\s+Ltd\.|Limited\s+Liability\s+Partnership|"
    r"Public\s+Limited|Limited|Ltd\.|LLP)(?![\w])"
)
_ABBR_TOKEN = r"[A-Z0-9]{2,}"
_TEXTUAL_DEFINITION_RE = re.compile(
    rf"(?i:hereinafter[ \t]+referred[ \t]+to[ \t]+as|abbreviated[ \t]+as|abbreviated[ \t]+to|"
    rf"referred[ \t]+to[ \t]+as|hereafter)[ \t]+(?P<abbr>{_ABBR_TOKEN})(?![\w])"
)
_REFERENCE_RE = re.compile(
    r"(?i)(?<![\w])(?:the[ \t]+parent[ \t]+company|the[ \t]+subsidiary|the[ \t]+company|the[ \t]+issuer)(?![\w])"
)
_SECURITY_LABEL_RE = re.compile(
    r"(?i)(?<![\w])(?P<label>NSE[ \t]+symbol|BSE[ \t]+scrip[ \t]+code|ISIN)[ \t]*[:=][ \t]*"
)
_SECURITY_NAMESPACE = {"nse symbol": "NSE", "bse scrip code": "BSE", "isin": "ISIN"}
_NAME_CONNECTORS = {"and", "of", "the"}
_CLAUSE_BOUNDARY_WORDS = {
    "after", "announced", "announces", "announcing", "because", "by", "declared",
    "disclosed", "during", "filed", "for", "from", "grew", "has", "have", "in",
    "increased", "is", "on", "posted", "reported", "reports", "results", "said",
    "says", "strong", "stated", "that", "today", "to", "updated", "was", "were",
    "which", "while", "with",
}
_GRAMMATICAL_NAME_BOUNDARIES = {"and", "by", "for", "from", "in", "of", "on", "to", "with"}
_HARD_NAME_BOUNDARY_RE = re.compile(r"[,;:!?()\[\]]|\.(?=\s|$)")
_ORGANIZATION_NAME_CUES = {
    "bank", "capital", "enterprises", "finance", "group", "holdings", "industries",
    "infrastructure", "logistics", "motors", "pharmaceuticals", "systems",
    "technologies", "technology",
}
_CLEAR_CLAUSE_BOUNDARIES = {
    "after", "announced", "announces", "announcing", "because", "by",
    "declared", "disclosed", "during", "filed", "for", "from", "grew",
    "has", "have", "in", "increased", "is", "on", "posted", "reported",
    "reports", "said", "says", "stated", "that", "today", "to", "updated",
    "was", "were", "which", "while", "with",
}


def _is_token_character(character: str) -> bool:
    """Treat letters, digits, underscore, and all Unicode marks as token text."""
    return character == "_" or character.isalnum() or unicodedata.category(character).startswith("M")


def _has_token_boundaries(text: str, start: int, end: int) -> bool:
    return not (
        (start > 0 and _is_token_character(text[start - 1]))
        or (end < len(text) and _is_token_character(text[end]))
    )


@dataclass(frozen=True)
class _Candidate:
    field: Field
    start: int
    end: int
    kind: ObservationKind
    namespace: Namespace | None = None


@dataclass(frozen=True)
class _Word:
    start: int
    end: int
    text: str


def _word_matches(text: str) -> list[_Word]:
    """Tokenize name words without splitting combining marks from letters."""
    matches: list[_Word] = []
    index = 0
    connectors = "&'’.-"
    while index < len(text):
        if not _is_token_character(text[index]):
            index += 1
            continue
        start = index
        index += 1
        while index < len(text):
            if _is_token_character(text[index]):
                index += 1
                continue
            if (
                text[index] in connectors
                and index + 1 < len(text)
                and _is_token_character(text[index - 1])
                and _is_token_character(text[index + 1])
            ):
                index += 1
                continue
            break
        matches.append(_Word(start, index, text[start:index]))
    return matches


def _field_text(document: NormalizedDocument, field: Field) -> str | None:
    return document.normalized_title if field == "title" else document.normalized_body


def _organization_candidates(text: str, field: Field) -> list[_Candidate]:
    """Find suffix-bearing name phrases using conservative lexical boundaries.

    A preceding legal suffix and hard punctuation delimit candidates. Clause
    words and grammatical prepositions delimit the name where their use is
    clear. Capitalization is only a weak cue within a phrase, never proof of
    its start. A clause-vocabulary word can also be a legitimate name word;
    it is a boundary only when grammar makes that use clear. If it leaves a
    prefix without a grammatical separator or organization-name cue, the
    start is ambiguous and the candidate is skipped. Leading name words are
    never stripped to manufacture a boundary.
    """
    results: list[_Candidate] = []
    suffixes = list(_SUFFIX_RE.finditer(text))
    completed_suffix_floor = 0
    for suffix in suffixes:
        suffix_start = suffix.start()
        if suffix_start == 0 or not text[suffix_start - 1].isspace() or not _has_token_boundaries(text, suffix.start(), suffix.end()):
            continue
        prefix_end = suffix_start
        while prefix_end > 0 and text[prefix_end - 1].isspace():
            prefix_end -= 1

        # A previous completed legal-suffix candidate is a hard boundary.
        floor = completed_suffix_floor
        # Punctuation also establishes a source-local phrase boundary. This
        # preserves apostrophes, hyphens, ampersands, and periods inside words.
        for boundary in _HARD_NAME_BOUNDARY_RE.finditer(text, floor, prefix_end):
            floor = boundary.end()
        segment = text[floor:prefix_end]
        words = [
            _Word(word.start + floor, word.end + floor, word.text)
            for word in _word_matches(segment)
        ]
        if not words or words[-1].end != prefix_end:
            continue

        chosen: list[_Word] = [words[-1]]
        ambiguous_start = False
        for previous, current in zip(reversed(words[:-1]), reversed(words[1:])):
            gap = text[previous.end:current.start]
            if not gap or not gap.isspace():
                break
            previous_token = previous.text.casefold()
            # Do not absorb a clause noun through a connector: "Results of
            # Synthetic Alpha Limited" begins at Synthetic, while "Bank of
            # India Limited" keeps "of" because Bank is not a clause boundary.
            if previous_token in _NAME_CONNECTORS:
                left = words[words.index(previous) - 1] if words.index(previous) > 0 else None
                if (
                    left is not None
                    and left.text.casefold() in _CLAUSE_BOUNDARY_WORDS
                    and left.text.casefold() not in _CLEAR_CLAUSE_BOUNDARIES
                ):
                    break
                chosen.append(previous)
                continue
            if previous_token in _GRAMMATICAL_NAME_BOUNDARIES:
                break
            if previous_token in _CLAUSE_BOUNDARY_WORDS:
                # Clause vocabulary is evidence, not a stop list. A structural
                # organization cue supports names such as "Strong Holdings";
                # without a grammatical separator or such a cue, the phrase
                # could include a clause prefix, so abstain.
                if any(word.text.casefold() in _ORGANIZATION_NAME_CUES for word in chosen):
                    chosen.append(previous)
                    continue
                if previous_token in _CLEAR_CLAUSE_BOUNDARIES:
                    break
                ambiguous_start = True
                break

            # Capitalization may extend a candidate only after a known name
            # token or connector; it cannot override a clause marker above.
            if previous.text[0].isupper():
                chosen.append(previous)
                continue

            earlier_index = words.index(previous) - 1
            anchored = False
            while earlier_index >= 0:
                earlier = words[earlier_index]
                next_word = words[earlier_index + 1]
                if text[earlier.end:next_word.start].strip():
                    break
                earlier_token = earlier.text.casefold()
                if earlier_token in _CLAUSE_BOUNDARY_WORDS:
                    break
                if earlier.text[0].isupper():
                    anchored = True
                    break
                earlier_index -= 1
            if anchored:
                chosen.append(previous)
                continue
            break

        if ambiguous_start:
            logger.warning("ambiguous_organization_boundary_skipped")
            continue

        chosen.reverse()
        # A conjunction immediately after a completed suffix joins distinct
        # candidates. Other leading connectors, especially "the", may be
        # part of the observed name and are preserved.
        if floor > 0 and len(chosen) > 1 and chosen[0].text.casefold() == "and":
            chosen.pop(0)
        start = chosen[0].start
        # A wholly lower-case prefix has no reliable lexical start cue. Skip
        # it rather than guessing whether it is a name or preceding prose.
        if not any(word.text[0].isupper() for word in chosen):
            logger.warning("ambiguous_organization_boundary_skipped")
            continue
        if start > 0 and unicodedata.category(text[start - 1]).startswith("M"):
            logger.warning("ambiguous_organization_boundary_skipped")
            continue
        if not text[start:prefix_end].strip():
            continue
        results.append(_Candidate(field, start, suffix.end(), "organization_name_candidate"))
        completed_suffix_floor = suffix.end()
    return results


def _is_abbreviation(token: str) -> bool:
    return len(token) >= 2 and any(character.isalpha() for character in token) and token.isascii() and token.isupper()


def _abbreviation_definitions(text: str, field: Field, organizations: list[_Candidate]) -> list[tuple[str, _Candidate]]:
    definitions: list[tuple[str, _Candidate]] = []
    for organization in organizations:
        tail = text[organization.end:]
        parenthetical = re.match(r"\s*\((?P<abbr>[A-Z0-9]{2,})\)(?![\w])", tail)
        if parenthetical and _is_abbreviation(parenthetical.group("abbr")):
            start = organization.end + parenthetical.start("abbr")
            end = organization.end + parenthetical.end("abbr")
            definitions.append((parenthetical.group("abbr"), _Candidate(field, start, end, "abbreviation_candidate")))

    for match in _TEXTUAL_DEFINITION_RE.finditer(text):
        token = match.group("abbr")
        if _is_abbreviation(token) and _has_token_boundaries(text, match.start("abbr"), match.end("abbr")):
            definitions.append((token, _Candidate(field, match.start("abbr"), match.end("abbr"), "abbreviation_candidate")))
    return definitions


def _abbreviation_occurrences(
    texts: dict[Field, str | None],
    definitions: list[tuple[str, _Candidate]],
) -> list[_Candidate]:
    order = {"title": 0, "body": 1}
    earliest: dict[str, tuple[int, int]] = {}
    result: list[_Candidate] = [candidate for _, candidate in definitions]
    for abbreviation, candidate in definitions:
        position = (order[candidate.field], candidate.start)
        earliest[abbreviation] = min(position, earliest.get(abbreviation, position))

    for field in ("title", "body"):
        text = texts[field]
        if text is None:
            continue
        for abbreviation, definition_position in earliest.items():
            for match in re.finditer(re.escape(abbreviation), text):
                if _has_token_boundaries(text, match.start(), match.end()) and (order[field], match.start()) > definition_position:
                    result.append(_Candidate(field, match.start(), match.end(), "abbreviation_candidate"))
    return result


def _security_candidates(text: str, field: Field) -> list[_Candidate]:
    results: list[_Candidate] = []
    labels = list(_SECURITY_LABEL_RE.finditer(text))
    for label_index, label in enumerate(labels):
        value_start = label.end()
        value_limit = labels[label_index + 1].start() if label_index + 1 < len(labels) else len(text)
        if value_start >= value_limit:
            logger.warning("malformed_security_identifier_value")
            continue
        value_context = text[value_start:value_limit]
        token_match = re.match(r"[^\s,;!?()]+", value_context)
        if token_match is None:
            logger.warning("malformed_security_identifier_value")
            continue
        token = token_match.group(0).rstrip(".,:}")
        if not token:
            logger.warning("malformed_security_identifier_value")
            continue
        label_key = re.sub(r"\s+", " ", label.group("label")).casefold()
        namespace = _SECURITY_NAMESPACE[label_key]
        valid = _valid_security_value(namespace, token)
        if not valid:
            logger.warning("malformed_security_identifier_value")
            continue
        results.append(_Candidate(field, value_start, value_start + len(token), "security_identifier_candidate", namespace))
    return results


def _valid_security_value(namespace: Namespace, value: str) -> bool:
    if namespace == "NSE":
        return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9&_-]{0,30}[A-Za-z0-9])?", value)) and len(value) <= 32
    if namespace == "BSE":
        return bool(re.fullmatch(r"[0-9]{1,10}", value))
    return bool(re.fullmatch(r"[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]", value))


def _all_candidates(document: NormalizedDocument) -> list[_Candidate]:
    texts: dict[Field, str | None] = {"title": document.normalized_title, "body": document.normalized_body}
    results: list[_Candidate] = []
    definitions: list[tuple[str, _Candidate]] = []
    for field in ("title", "body"):
        text = texts[field]
        if text is None:
            continue
        organizations = _organization_candidates(text, field)
        results.extend(organizations)
        definitions.extend(_abbreviation_definitions(text, field, organizations))
        for security_candidate in _security_candidates(text, field):
            if _security_context_has_linebreak(document, security_candidate):
                logger.warning("malformed_security_identifier_value")
                continue
            results.append(security_candidate)
        for match in _REFERENCE_RE.finditer(text):
            if _has_token_boundaries(text, match.start(), match.end()):
                results.append(_Candidate(field, match.start(), match.end(), "other_company_reference"))
    results.extend(_abbreviation_occurrences(texts, definitions))
    # Exact identity deduplication only. Repeated positions and alternate kinds
    # or namespaces remain distinct candidates.
    unique = {
        (item.field, item.start, item.end, item.kind, item.namespace): item
        for item in results
    }
    return sorted(
        unique.values(),
        key=lambda item: (
            0 if item.field == "title" else 1,
            item.start,
            item.end,
            _KIND_ORDER[item.kind],
            item.namespace or "",
        ),
    )


def _security_context_has_linebreak(document: NormalizedDocument, candidate: _Candidate) -> bool:
    """Reject label/value constructions separated by a source line break.

    Stage 1 collapses internal whitespace, so inspect the mapped original
    label-to-value slice to retain the source's line boundary semantics.
    """
    text = _field_text(document, candidate.field)
    original = document.original_title if candidate.field == "title" else document.original_body
    if text is None or original is None:
        return True
    label = next((match for match in _SECURITY_LABEL_RE.finditer(text) if match.end() == candidate.start), None)
    if label is None:
        return True
    mapped = map_normalized_span(document, candidate.field, label.start(), candidate.start)
    return "\n" in original[mapped.start:mapped.end] or "\r" in original[mapped.start:mapped.end]


def _map_candidate(
    candidate: _Candidate,
    *,
    normalized_document: NormalizedDocument,
    extractor_version: str,
) -> EntityMention | None:
    normalized = _field_text(normalized_document, candidate.field)
    original = normalized_document.original_title if candidate.field == "title" else normalized_document.original_body
    if normalized is None or original is None:
        raise ValueError("candidate field is absent from normalized input")
    mapped = map_normalized_span(normalized_document, candidate.field, candidate.start, candidate.end)
    surface = original[mapped.start:mapped.end]
    if mapped.ambiguous:
        normalized_source, _ = normalize_text(surface)
        expected = normalized[candidate.start:candidate.end]
        if normalized_source != expected:
            logger.warning("ambiguous_candidate_boundary_skipped")
            return None
    evidence = EvidenceSpan(
        field=candidate.field,
        start=mapped.start,
        end=mapped.end,
        quote=surface,
        role="entity",
        alignment_ambiguous=mapped.ambiguous,
    )
    factory = DeterministicIdFactory()
    identifier = factory.mention_id(
        document_ref=normalized_document.document_ref,
        field=candidate.field,
        start=mapped.start,
        end=mapped.end,
        observation_kind=candidate.kind,
        security_namespace=candidate.namespace,
        extractor_version=extractor_version,
    )
    return EntityMention(
        mention_id=identifier,
        document_ref=normalized_document.document_ref,
        surface_text=surface,
        field=candidate.field,
        start=mapped.start,
        end=mapped.end,
        observation_kind=candidate.kind,
        evidence=evidence,
        extractor_version=extractor_version,
        security_namespace=candidate.namespace,
    )


def extract_entity_mentions(
    analysis_input: AnalysisInput,
    *,
    extractor_version: str,
) -> tuple[EntityMention, ...]:
    """Extract deterministic textual candidates without resolving identities."""
    if not isinstance(analysis_input, AnalysisInput):
        raise TypeError("analysis_input must be an AnalysisInput")
    if not isinstance(extractor_version, str) or not extractor_version.strip():
        raise ValueError("extractor_version must be non-empty text")
    normalized_document = normalize_document(analysis_input)
    mentions: list[EntityMention] = []
    for candidate in _all_candidates(normalized_document):
        mapped = _map_candidate(
            candidate,
            normalized_document=normalized_document,
            extractor_version=extractor_version,
        )
        if mapped is not None:
            mentions.append(mapped)
    result = tuple(mentions)
    validate_entity_source(
        analysis_input,
        result,
        normalized_document=normalize_document(analysis_input),
    )
    return result
