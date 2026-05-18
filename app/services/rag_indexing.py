import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

# Real embedding providers are imported lazily to keep the module usable
# without optional dependencies installed.
SUPPORTED_REAL_PROVIDERS = ('openai', 'anthropic', 'ollama')
_PROVIDER_DEFAULT_DIMS = {
    'openai': 1536,
    'anthropic': 1024,
    'ollama': 768,
    'local_hash': 1536,
}

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
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
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


def is_semantic_provider(provider: str) -> bool:
    """Return True when the provider generates real ML embeddings (not local_hash)."""
    return provider in SUPPORTED_REAL_PROVIDERS


async def real_embedding_async(
    text: str,
    *,
    provider: str,
    model: str,
    api_key: str | None,
    dimensions: int,
) -> list[float]:
    """Call a real embedding API and return a normalised float vector.

    Raises `RuntimeError` when the provider call fails so the caller can surface
    a clear configuration or availability error to the operator. Raises
    `ValueError` when the provider is unknown.
    """
    if provider == 'openai':
        try:
            import openai  # noqa: PLC0415
            client = openai.AsyncOpenAI(api_key=api_key)
            response = await client.embeddings.create(
                input=text[:8191],
                model=model or 'text-embedding-3-small',
                dimensions=dimensions if dimensions != 1536 else None,  # type: ignore[arg-type]
            )
            return response.data[0].embedding
        except Exception as exc:
            raise RuntimeError(f'OpenAI embedding failed: {exc}') from exc

    if provider == 'anthropic':
        # Anthropic embeddings are served via Voyage AI; use httpx directly.
        try:
            import httpx  # noqa: PLC0415
            voyage_model = model or 'voyage-3-lite'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            }
            payload = {'input': [text[:16000]], 'model': voyage_model}
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post('https://api.voyageai.com/v1/embeddings', headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data['data'][0]['embedding']
        except Exception as exc:
            raise RuntimeError(f'Anthropic/Voyage embedding failed: {exc}') from exc

    if provider == 'ollama':
        try:
            import httpx  # noqa: PLC0415
            ollama_model = model or 'nomic-embed-text'
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    'http://localhost:11434/api/embeddings',
                    json={'model': ollama_model, 'prompt': text},
                )
                resp.raise_for_status()
                return resp.json()['embedding']
        except Exception as exc:
            raise RuntimeError(f'Ollama embedding failed: {exc}') from exc

    raise ValueError(f'Unknown embedding provider: {provider!r}')


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


_PRICE_COLS = re.compile(r'precio|price|costo|cost|valor|tarifa|rate', re.IGNORECASE)
_DURATION_COLS = re.compile(r'duraci[oó]n|minutos|minutes|duration|tiempo|time', re.IGNORECASE)
_CATEGORY_COLS = re.compile(r'categor[ií]a|category|tipo|type|grupo|group', re.IGNORECASE)
_NOTES_COLS = re.compile(r'nota|note|observaci[oó]n|comentario|descripci[oó]n|description|detalle', re.IGNORECASE)
_BOOL_AFFIRMATIVE = {'si', 'sí', 'yes', 'true', '1', 'verdadero'}


def _format_csv_value(header: str, value: str) -> str:
    """Format a single CSV cell as a human-readable phrase."""
    value = value.strip()
    if not value:
        return ''
    if _PRICE_COLS.search(header):
        try:
            amount = int(float(value.replace(',', '').replace('.', '')))
            return f'Precio: ${amount:,} COP'
        except (ValueError, TypeError):
            pass
    if _DURATION_COLS.search(header):
        return f'Duración: {value} min'
    if header.lower().startswith('requiere') or 'diagn' in header.lower():
        human = 'Sí' if value.lower() in _BOOL_AFFIRMATIVE else 'No'
        return f'{header.replace("_", " ").capitalize()}: {human}'
    return f'{header.replace("_", " ").capitalize()}: {value}'


def csv_rows_to_natural_language(text: str) -> str:
    """Convert CSV text to one readable sentence per row for better retrieval."""
    try:
        reader = csv.DictReader(io.StringIO(text.strip()))
        if not reader.fieldnames or len(reader.fieldnames) < 2:
            return text
        headers = list(reader.fieldnames)
        rows = list(reader)
    except Exception:
        return text

    if not rows:
        return text

    # Identify key column roles
    name_col = headers[0]
    category_col = next((h for h in headers if _CATEGORY_COLS.search(h)), None)
    notes_cols = [h for h in headers if _NOTES_COLS.search(h) and h != name_col]
    skip_cols = {name_col, category_col} if category_col else {name_col}

    sentences: list[str] = []
    for row in rows:
        name = (row.get(name_col) or '').strip()
        if not name:
            continue

        category = (row.get(category_col) or '').strip() if category_col else ''
        entity = f'{name} (categoría: {category})' if category else name

        parts: list[str] = []
        for header in headers:
            if header in skip_cols:
                continue
            value = (row.get(header) or '').strip()
            if not value:
                continue
            if header in notes_cols:
                parts.append(value)
            else:
                formatted = _format_csv_value(header, value)
                if formatted:
                    parts.append(formatted)

        sentences.append(f'{entity}: {". ".join(parts)}.')

    return '\n'.join(sentences) if sentences else text


def is_csv_content(text: str) -> bool:
    """Heuristic: first non-empty line has ≥2 commas and most lines are consistent."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    first_commas = lines[0].count(',')
    if first_commas < 2:
        return False
    consistent = sum(1 for ln in lines[1:5] if abs(ln.count(',') - first_commas) <= 1)
    return consistent >= min(2, len(lines) - 1)


def split_line_by_token_budget(line: str, max_tokens: int) -> list[str]:
    words = WORD_RE.findall(line)
    if not words:
        return []

    segments: list[str] = []
    current_words: list[str] = []
    for word in words:
        candidate_words = [*current_words, word]
        candidate = ' '.join(candidate_words)
        if current_words and estimate_token_count(candidate) > max_tokens:
            segments.append(' '.join(current_words))
            current_words = [word]
        else:
            current_words = candidate_words

    if current_words:
        segments.append(' '.join(current_words))
    return segments


def chunk_document_text(
    text: str,
    *,
    max_tokens: int = 500,
    overlap_tokens: int = 80,
    embedding_dimensions: int = 1536,
    embedding_provider: str = 'local_hash',
    embedding_model: str = 'copilotoia-local-hash-v1',
    precomputed_embeddings: list[list[float]] | None = None,
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
        idx = len(chunks)
        if precomputed_embeddings is not None and idx < len(precomputed_embeddings):
            embedding = precomputed_embeddings[idx]
        else:
            embedding = deterministic_embedding(chunk_text, embedding_dimensions)
        chunks.append(
            KnowledgeChunkDraft(
                chunk_index=idx,
                section_path=section_path,
                chunk_text=chunk_text,
                token_count=estimate_token_count(chunk_text),
                embedding=embedding,
                metadata={
                    'embedding_provider': embedding_provider,
                    'embedding_model': embedding_model,
                    'embedding_dimensions': embedding_dimensions,
                },
            )
        )
        overlap_words = WORD_RE.findall(chunk_text)[-overlap_tokens:] if overlap_tokens else []
        while overlap_words and estimate_token_count(' '.join(overlap_words)) > max_tokens:
            overlap_words.pop(0)
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

        for line_segment in split_line_by_token_budget(line, max_tokens):
            line_tokens = estimate_token_count(line_segment)
            if current_lines and current_tokens + line_tokens > max_tokens:
                flush()
            if current_lines and current_tokens + line_tokens > max_tokens:
                current_lines = []
                current_tokens = 0
            current_lines.append(line_segment)
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
    embedding_api_key: str | None = None,
) -> IndexingResult:
    """Synchronous indexing — only supports the `local_hash` provider.

    For real ML embeddings call `build_indexing_result_async` instead, which
    dispatches to the configured provider API. Calling this with a semantic
    provider raises `ValueError` so callers cannot silently downgrade.
    """
    if is_semantic_provider(embedding_provider):
        raise ValueError(
            f'Provider {embedding_provider!r} requires async indexing. '
            'Call build_indexing_result_async instead.'
        )
    extracted_text = extract_document_text(document)
    mime_type = (document.get('mime_type') or '').lower()
    if mime_type == 'text/csv' or is_csv_content(extracted_text):
        extracted_text = csv_rows_to_natural_language(extracted_text)
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


async def build_indexing_result_async(
    document: dict[str, Any],
    *,
    max_tokens: int = 500,
    overlap_tokens: int = 80,
    embedding_dimensions: int = 1536,
    embedding_provider: str = 'local_hash',
    embedding_model: str = 'copilotoia-local-hash-v1',
    embedding_api_key: str | None = None,
    tenant_no_train: bool | None = None,
) -> IndexingResult:
    """Async indexing that calls real ML embedding APIs when the provider is not local_hash.

    For `openai`, `anthropic`, and `ollama` providers this calls the respective API
    for each chunk. Provider failures propagate as `RuntimeError` so the caller
    can surface a clear 5xx error to the operator instead of producing chunks
    with deterministic SHA256 vectors that look healthy but are not searchable.

    AUDIT-49 / re-audit §1.6 (2026-05-18): si el tenant tiene
    `tenant_settings.no_train=True` (default), forzar `local_hash` aunque la
    config global pida un provider cloud (`openai`/`anthropic`). Esto cierra
    el path por el que los KB documents salían a Anthropic/OpenAI para
    embeddings sin opt-in explícito del tenant. `ollama` no cuenta como
    cloud (corre on-prem), así que NO se gatea. Fail-closed: `None` /`True`
    bloquean cloud, solo `False` permite.
    """
    extracted_text = extract_document_text(document)
    mime_type = (document.get('mime_type') or '').lower()
    if mime_type == 'text/csv' or is_csv_content(extracted_text):
        extracted_text = csv_rows_to_natural_language(extracted_text)
    sanitized_text, sanitized_warning_count = sanitize_document_text(extracted_text)

    # AUDIT-49: gate por tenant_no_train antes de salir al provider cloud.
    if embedding_provider in {'openai', 'anthropic'} and tenant_no_train is not False:
        log.info(
            'rag_indexing.cloud_provider_blocked_by_tenant_no_train',
            requested_provider=embedding_provider,
            fallback='local_hash',
            hint='tenant_settings.no_train=true (default) — embeddings se generan localmente',
        )
        embedding_provider = 'local_hash'
        embedding_model = 'copilotoia-local-hash-v1'

    if not is_semantic_provider(embedding_provider):
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

    # First, produce chunks with placeholder embeddings to learn the texts.
    draft_chunks = chunk_document_text(
        sanitized_text,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        embedding_dimensions=embedding_dimensions,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )

    # Then fetch real embeddings for every chunk text. Provider failures
    # propagate up so the indexing endpoint can return a clear error instead of
    # silently writing useless SHA256 vectors.
    real_embeddings: list[list[float]] = []
    for draft in draft_chunks:
        vec = await real_embedding_async(
            draft.chunk_text,
            provider=embedding_provider,
            model=embedding_model,
            api_key=embedding_api_key,
            dimensions=embedding_dimensions,
        )
        real_embeddings.append(vec)

    chunks = chunk_document_text(
        sanitized_text,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        embedding_dimensions=embedding_dimensions,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        precomputed_embeddings=real_embeddings,
    )
    return IndexingResult(
        chunks=chunks,
        sanitized_warning_count=sanitized_warning_count,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )
