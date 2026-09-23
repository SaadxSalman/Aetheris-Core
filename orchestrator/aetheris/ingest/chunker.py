"""Contextual Chunk-Header Injector + heading-aware chunker.

Before embedding, every child chunk is prefixed with its parent heading
breadcrumb ("Guide > Retrieval > Fusion"), eliminating the context loss that
plagues naive fixed-size splitters. The raw text and the breadcrumb are stored
separately so citations stay clean while embeddings carry the context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from aetheris.config import settings
from aetheris.textutils import sha256_hex, tokenize

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_NUM_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\s*[.)-]\s+([A-Z].{2,80})$")
_CAPS_HEADING = re.compile(r"^([A-Z][A-Za-z0-9 &/\-]{2,60})\s*:\s*$")
_SENTENCE_END = re.compile(r"[.!?]\s+|\n{2,}")


@dataclass
class Chunk:
    ordinal: int
    header_path: str
    text: str
    embedded_text: str
    token_count: int
    content_sha256: str
    id: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id, "ordinal": self.ordinal, "header_path": self.header_path,
            "text": self.text, "embedded_text": self.embedded_text,
            "token_count": self.token_count, "content_sha256": self.content_sha256,
        }


def _split_long(paragraph: str, size: int, overlap: int) -> list[str]:
    if len(paragraph) <= size:
        return [paragraph]
    pieces: list[str] = []
    start = 0
    while start < len(paragraph):
        end = min(start + size, len(paragraph))
        if end < len(paragraph):
            # prefer breaking at sentence/word boundary
            window = paragraph[start:end]
            cut = max(window.rfind(". "), window.rfind(" "), window.rfind("\n"))
            if cut > size // 3:
                end = start + cut + 1
        pieces.append(paragraph[start:end].strip())
        if end >= len(paragraph):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_document(text: str, doc_id: str, title: str = "") -> list[Chunk]:
    """Heading-aware chunking with contextual header injection."""
    lines = text.replace("\r\n", "\n").split("\n")
    max_levels = settings.CHUNK_HEADER_MAX_LEVELS
    size, overlap = settings.CHUNK_SIZE, settings.CHUNK_OVERLAP
    heading_stack: list[tuple[int, str]] = []
    if title:
        heading_stack.append((1, title))

    blocks: list[tuple[str, str]] = []  # (header_path, paragraph)
    buf: list[str] = []

    def flush() -> None:
        if buf:
            para = "\n".join(buf).strip()
            if para:
                path = " > ".join(h for _, h in heading_stack[:max_levels])
                blocks.append((path, para))
            buf.clear()

    for line in lines:
        m = (_MD_HEADING.match(line) or _NUM_HEADING.match(line) or _CAPS_HEADING.match(line))
        if m:
            flush()
            if len(m.groups()) == 2 and line.lstrip().startswith("#"):
                level = len(m.group(1))
                title_h = m.group(2)
            else:
                level = 2 if _NUM_HEADING.match(line) else 2
                title_h = m.group(2) if _NUM_HEADING.match(line) else m.group(1)
            heading_stack = [(lv, h) for lv, h in heading_stack if lv < level]
            heading_stack.append((level, title_h.strip()))
            # heading itself becomes a lead-in line of the next block
            buf.append(f"{title_h.strip()}:")
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()

    chunks: list[Chunk] = []
    ordinal = 0
    for path, para in blocks:
        for piece in _split_long(para, size, overlap):
            header_prefix = f"[Section: {path}]\n" if path else ""
            embedded = header_prefix + piece
            tokens = tokenize(piece)
            ck = Chunk(
                ordinal=ordinal,
                header_path=path,
                text=piece,
                embedded_text=embedded,
                token_count=len(tokens),
                content_sha256=sha256_hex(embedded, settings.CONTENT_HASH_PEPPER),
            )
            ck.id = f"chk::{doc_id}::{ordinal}::{ck.content_sha256[:8]}"
            chunks.append(ck)
            ordinal += 1
    return chunks
