from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_PATTERN = re.compile(r"[\w\u3400-\u9fff]{2,}", re.UNICODE)
_BOUNDARY_PATTERN = re.compile(r"\n{2,}|(?<=[。！？.!?])\s+")


@dataclass(frozen=True, slots=True)
class EvidenceSegment:
    evidence_id: str
    start: int
    end: int
    text: str
    reason: str

    def manifest(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "start": self.start,
            "end": self.end,
            "reason": self.reason,
            "preview": self.text[:180].strip(),
        }


@dataclass(frozen=True, slots=True)
class ReviewEvidencePack:
    segments: tuple[EvidenceSegment, ...]
    source_length: int
    covered_characters: int

    @property
    def full_coverage(self) -> bool:
        return self.covered_characters >= self.source_length

    def prompt_text(self) -> str:
        return "\n\n".join(
            (
                f"[{segment.evidence_id}] 原文位置 {segment.start + 1}"
                f"–{segment.end}；选取原因：{segment.reason}\n{segment.text}"
            )
            for segment in self.segments
        )

    def manifest(self) -> tuple[dict[str, object], ...]:
        return tuple(segment.manifest() for segment in self.segments)


def build_review_evidence_pack(
    *,
    source_text: str,
    request: str,
    character_budget: int,
) -> ReviewEvidencePack:
    """Select traceable evidence without reducing a long work to its opening."""
    normalized = source_text.strip()
    if not normalized or character_budget <= 0:
        return ReviewEvidencePack(segments=(), source_length=len(normalized), covered_characters=0)
    if len(normalized) <= character_budget:
        segment = EvidenceSegment(
            evidence_id="E001",
            start=0,
            end=len(normalized),
            text=normalized,
            reason="全文",
        )
        return ReviewEvidencePack(
            segments=(segment,),
            source_length=len(normalized),
            covered_characters=len(normalized),
        )

    chunks = _source_chunks(normalized)
    request_terms = {term.casefold() for term in _TOKEN_PATTERN.findall(request)}
    scored: list[tuple[float, int, int, str]] = []
    total = len(normalized)
    for start, end, text in chunks:
        terms = {term.casefold() for term in _TOKEN_PATTERN.findall(text)}
        lexical_score = float(len(request_terms & terms) * 8)
        relative = start / max(total, 1)
        coverage_score = 2.5 if relative < 0.08 or relative > 0.92 else 0.0
        scored.append((lexical_score + coverage_score, start, end, text))

    selected: list[tuple[int, int, str, str]] = []
    anchors = (
        (0, "开篇锚点"),
        (total // 2, "中段锚点"),
        (max(total - 1, 0), "结尾锚点"),
    )
    for position, reason in anchors:
        candidate = min(chunks, key=lambda item: abs(item[0] - position))
        selected.append((*candidate, reason))

    for score, start, end, text in sorted(scored, key=lambda item: (-item[0], item[1])):
        if score <= 0:
            continue
        if any(existing_start == start for existing_start, *_ in selected):
            continue
        selected.append((start, end, text, "与本轮评审要求相关"))

    # Fill remaining capacity with evenly distributed source evidence.
    for start, end, text in chunks:
        if any(existing_start == start for existing_start, *_ in selected):
            continue
        selected.append((start, end, text, "分层覆盖"))

    result: list[EvidenceSegment] = []
    used = 0
    for start, _end, text, reason in selected:
        remaining = character_budget - used
        if remaining <= 0:
            break
        excerpt = text[:remaining].strip()
        if not excerpt:
            continue
        actual_end = start + len(excerpt)
        result.append(
            EvidenceSegment(
                evidence_id=f"E{len(result) + 1:03d}",
                start=start,
                end=actual_end,
                text=excerpt,
                reason=reason,
            )
        )
        used += len(excerpt)

    result.sort(key=lambda segment: segment.start)
    # Stable IDs follow reading order, not ranking order.
    ordered = tuple(
        EvidenceSegment(
            evidence_id=f"E{index:03d}",
            start=segment.start,
            end=segment.end,
            text=segment.text,
            reason=segment.reason,
        )
        for index, segment in enumerate(result, start=1)
    )
    return ReviewEvidencePack(
        segments=ordered,
        source_length=len(normalized),
        covered_characters=sum(len(segment.text) for segment in ordered),
    )


def _source_chunks(source_text: str) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    cursor = 0
    for match in _BOUNDARY_PATTERN.finditer(source_text):
        end = match.start()
        text = source_text[cursor:end].strip()
        if text:
            start = source_text.find(text, cursor, end + 1)
            chunks.append((start, start + len(text), text))
        cursor = match.end()
    tail = source_text[cursor:].strip()
    if tail:
        start = source_text.find(tail, cursor)
        chunks.append((start, start + len(tail), tail))
    if not chunks:
        chunks.append((0, len(source_text), source_text))
    return chunks
