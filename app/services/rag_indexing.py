import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

PROMPT_INJECTION_PATTERNS = (
    re.compile(r'(?i)\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)\b'),
    re.compile(r'(?i)\b(system|developer|assistant)\s*:\s*'),
    re.compile(r'(?i)\b(reveal|print|show|exfiltrate)\s+(the\s+)?(system\s+)?prompt\b'),
    re.compile(r'(?i)\bdo\s+not\s+follow\s+(the\s+)?(system|developer|previous)\s+(instructions|rules)\b'),
)
SECTION_HEADING_RE = re.compile(r'^(#{1,6}\s+.+|[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ /.,:-]{2,80}:)\s*$')
WORD_RE = re.compile(r'\S+')


@dataclass(frozen=True)
class KnowledgeChunkDraft:
    chunk_index: int
    section_path: str
    chunk_text: str
    token_count: int
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class IndexingResult:
    chunks: list[KnowledgeChunkDraft]
    sanitized_warning_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int


def extract_document_text(document: dict[str, Any]) -> str:
    """Extract plain text from supported KnowledgeDocument representations.

    Binary parsing and remote fetching are intentionally left out of this MVP. Upload, URL and
    integration sources can provide pre-extracted text in ``content`` or
    ``metadata.extracted_text`` so indexing remains deterministic and tenant-local.
    """
    content = document.get('content')
    if isinstance(content, str) and content.strip():
        return content

    metadata = document.get('metadata') or {}
    extracted_text = metadata.get('extracted_text')
    if isinstance(extracted_text, str) and extracted_text.strip():
        return extracted_text

    raise ValueError('Knowledge document has no extractable text in content or metadata.extracted_text')


def sanitize_document_text(text: str) -> tuple[str, int]:
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    warning_count = 0

    sanitized_lines = []
    for line in normalized.split('\n'):
        sanitized_line = line.strip()
        for pattern in PROMPT_INJECTION_PATTERNS:
            sanitized_line, replacements = pattern.subn('[removed unsafe instruction]', sanitized_line)
            warning_count += replacements
        sanitized_lines.append(sanitized_line)

    sanitized = '\n'.join(sanitized_lines)
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized).strip()
    if not sanitized:
        raise ValueError('Knowledge document has no indexable text after sanitization')
    return sanitized, warning_count


def estimate_token_count(text: str) -> int:
    # Lightweight approximation to keep indexing deterministic without tokenizer dependencies.
    words = WORD_RE.findall(text)
    return max(1, math.ceil(len(words) * 1.3))


def deterministic_embedding(text: str, dimensions: int = 1536) -> list[float]:
    if dimensions <= 0:
        raise ValueError('Embedding dimensions must be greater than zero')

    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(f'{counter}:{text}'.encode('utf-8')).digest()
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dimensions:
                break
        counter += 1

    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 8) for value in values]


def vector_literal(values: list[float]) -> str:
    return '[' + ','.join(f'{value:.8f}' for value in values) + ']'


def chunk_document_text(
    text: str,
    *,
    max_tokens: int = 500,
    overlap_tokens: int = 80,
    embedding_dimensions: int = 1536,
    embedding_provider: str = 'local_hash',
    embedding_model: str = 'copilotoia-local-hash-v1',
) -> list[KnowledgeChunkDraft]:
    if max_tokens <= 0:
        raise ValueError('max_tokens must be greater than zero')
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError('overlap_tokens must be non-negative and smaller than max_tokens')

    chunks: list[KnowledgeChunkDraft] = []
    section_path = 'Documento'
    current_lines: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_lines, current_tokens
        chunk_text = '\n'.join(current_lines).strip()
        if not chunk_text:
            current_lines = []
            current_tokens = 0
            return
        chunks.append(
            KnowledgeChunkDraft(
                chunk_index=len(chunks),
                section_path=section_path,
                chunk_text=chunk_text,
                token_count=estimate_token_count(chunk_text),
                embedding=deterministic_embedding(chunk_text, embedding_dimensions),
                metadata={
                    'embedding_provider': embedding_provider,
                    'embedding_model': embedding_model,
                    'embedding_dimensions': embedding_dimensions,
                },
            )
        )
        overlap_words = WORD_RE.findall(chunk_text)[-overlap_tokens:] if overlap_tokens else []
        current_lines = [' '.join(overlap_words)] if overlap_words else []
        current_tokens = estimate_token_count(current_lines[0]) if current_lines else 0

    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        if SECTION_HEADING_RE.match(line):
            if current_lines:
                flush()
            section_path = line.lstrip('#').strip().rstrip(':')
            continue

        line_tokens = estimate_token_count(line)
        if current_lines and current_tokens + line_tokens > max_tokens:
            flush()
        current_lines.append(line)
        current_tokens += line_tokens

    if current_lines:
        flush()

    if not chunks:
        raise ValueError('Knowledge document produced no chunks')
    return chunks


def build_indexing_result(
    document: dict[str, Any],
    *,
    max_tokens: int = 500,
    overlap_tokens: int = 80,
    embedding_dimensions: int = 1536,
    embedding_provider: str = 'local_hash',
    embedding_model: str = 'copilotoia-local-hash-v1',
) -> IndexingResult:
    extracted_text = extract_document_text(document)
    sanitized_text, sanitized_warning_count = sanitize_document_text(extracted_text)
    chunks = chunk_document_text(
        sanitized_text,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        embedding_dimensions=embedding_dimensions,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
    return IndexingResult(
        chunks=chunks,
        sanitized_warning_count=sanitized_warning_count,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )
