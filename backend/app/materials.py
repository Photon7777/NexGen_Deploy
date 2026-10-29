"""Course materials: PDF pages into overlapping chunks, and chunks into embeddings.

This is classic chunk RAG, the baseline the Phase 2 benchmark measures the OKF study
guide against. Chunks follow the text rather than the page, so one chunk can span a page
break; each records the pages it covers so answers can cite them.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

MAX_UPLOAD_BYTES = 20_000_000
MAX_DOCUMENT_PAGES = 300
MAX_COURSE_PAGES = 600
CHUNK_CHARS = 1800  # about 450 tokens
OVERLAP_CHARS = 250  # carried into the next chunk, so a sentence is never cut off from its context
EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_BATCH = 96

Embedder = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class Chunk:
    page_from: int
    page_to: int
    text: str


def clean(text: str) -> str:
    """Collapse the runs of spaces and blank lines PDF extraction leaves, keeping line breaks."""
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _pieces(pages: list[str], size: int) -> list[tuple[int, str]]:
    """(page number, line) for every non-empty line, with lines longer than `size` split at spaces."""
    pieces = []
    for page_no, text in enumerate(pages, 1):
        for line in clean(text).split("\n"):
            line = line.strip()
            while len(line) > size:
                cut = line.rfind(" ", 0, size)
                cut = cut if cut > size // 2 else size
                pieces.append((page_no, line[:cut]))
                line = line[cut:].strip()
            if line:
                pieces.append((page_no, line))
    return pieces


def chunk_pages(pages: list[str], size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Pack lines into chunks of about `size` characters. Each chunk after the first starts
    with up to `overlap` characters of whole lines from the end of the one before."""
    def emit(lines: list[tuple[int, str]]) -> Chunk:
        return Chunk(lines[0][0], lines[-1][0], "\n".join(text for _, text in lines))

    chunks: list[Chunk] = []
    current: list[tuple[int, str]] = []
    length = 0
    for piece in _pieces(pages, size):
        if current and length + len(piece[1]) + 1 > size:
            chunks.append(emit(current))
            carried: list[tuple[int, str]] = []
            for line in reversed(current):
                if sum(len(t) + 1 for _, t in carried) + len(line[1]) > overlap:
                    break
                carried.insert(0, line)
            current, length = carried, sum(len(t) + 1 for _, t in carried)
        current.append(piece)
        length += len(piece[1]) + 1
    if current:
        chunks.append(emit(current))
    return chunks


@lru_cache(maxsize=4)
def openai_embedder(api_key: str) -> Embedder:
    client = OpenAI(api_key=api_key, timeout=60, max_retries=2)

    def embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts[start : start + EMBED_BATCH])
            vectors += [d.embedding for d in sorted(response.data, key=lambda d: d.index)]
        return vectors

    return embed


def to_vector(values: list[float]) -> str:
    """pgvector's text form, cast with ::vector in SQL (no extra driver package needed)."""
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"
