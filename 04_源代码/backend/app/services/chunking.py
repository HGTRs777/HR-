from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .file_parser import TextBlock


HEADING_RE = re.compile(r"^(?:#{1,6}\s*)?(第[一二三四五六七八九十百零〇0-9]+[章节篇]\s*.+)$")
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百零〇0-9]+条)(?:[\s　、：:]+)?(.*)$")
NUMBERED_RE = re.compile(r"^((?:\d+(?:\.\d+)*)|(?:[一二三四五六七八九十]+、))[\s　]+(.+)$")


@dataclass(frozen=True)
class ClauseDraft:
    stable_anchor: str
    section_path: str
    clause_number: str | None
    page_number: int | None
    paragraph_index: int | None
    text: str
    text_sha256: str
    token_count: int


def split_clauses(blocks: list[TextBlock], policy_code: str, version: str) -> list[ClauseDraft]:
    section_path = ""
    collected: list[tuple[str, str | None, str, int | None, int | None]] = []
    current: tuple[str | None, list[str], int | None, int | None] | None = None

    def flush() -> None:
        nonlocal current
        if current:
            number, parts, page, paragraph = current
            text = "\n".join(parts).strip()
            if text:
                collected.append((section_path, number, text, page, paragraph))
        current = None

    for block in blocks:
        text = block.text.strip()
        heading = HEADING_RE.match(text) or MARKDOWN_HEADING_RE.match(text)
        if heading:
            flush()
            section_path = heading.group(1).lstrip("#").strip()
            continue
        article = ARTICLE_RE.match(text)
        numbered = NUMBERED_RE.match(text)
        if article or numbered:
            flush()
            match = article or numbered
            assert match is not None
            number = match.group(1)
            body = match.group(2).strip()
            current = (number, [f"{number} {body}".strip()], block.page_number, block.paragraph_index)
        elif current:
            current[1].append(text)
        else:
            current = (None, [text], block.page_number, block.paragraph_index)
    flush()

    drafts: list[ClauseDraft] = []
    for index, (section, number, text, page, paragraph) in enumerate(collected, start=1):
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        anchor_seed = f"{policy_code}|{version}|{number or index}|{section}|{text_hash}"
        anchor_hash = hashlib.sha1(anchor_seed.encode("utf-8")).hexdigest()[:20]
        drafts.append(
            ClauseDraft(
                stable_anchor=f"{policy_code.lower()}-{version.lower()}-{anchor_hash}",
                section_path=section,
                clause_number=number,
                page_number=page,
                paragraph_index=paragraph,
                text=text,
                text_sha256=text_hash,
                token_count=len(text),
            )
        )
    return drafts
