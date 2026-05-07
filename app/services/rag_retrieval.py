import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

WORD_RE = re.compile(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", re.UNICODE)
SPANISH_STOPWORDS = {
    'a', 'al', 'algo', 'ante', 'como', 'con', 'contra', 'cual', 'cuando', 'de', 'del',
    'desde', 'donde', 'dos', 'el', 'ella', 'ellos', 'en', 'entre', 'es', 'esa', 'ese',
    'eso', 'esta', 'este', 'esto', 'hay', 'la', 'las', 'le', 'lo', 'los', 'mas', 'me',
    'mi', 'mis', 'no', 'o', 'para', 'pero', 'por', 'porque', 'que', 'se', 'si', 'sin',
    'sobre', 'son', 'su', 'sus', 'te', 'tu', 'un', 'una', 'uno', 'y', 'ya', 'qué',
    'cuál', 'cuándo', 'dónde', 'cómo', 'tiene', 'tienen', 'puedo', 'puede', 'hacer',
}
DEFAULT_MIN_SCORE = 0.12
DEFAULT_MAX_CHUNKS = 5


@dataclass(frozen=True)
class RetrievalMatch:
    id: UUID | str
    document_id: UUID | str
    document_title: str
    source_uri: str | None
    source_type: str
    document_type: str
    visibility: str
    chunk_index: int
    section_path: str | None
    chunk_text: str
    token_count: int
    score: float
    matched_terms: list[str]
    metadata: dict[str, Any]



def strip_accents(value: str) -> str:
    return ''.join(
        character
        for character in unicodedata.normalize('NFKD', value)
        if not unicodedata.combining(character)
    )


def term_variants(term: str) -> set[str]:
    variants = {term}
    if len(term) > 4 and term.endswith('ciones'):
        variants.add(f'{term[:-6]}cion')
    if len(term) > 4 and term.endswith('ces'):
        variants.add(f'{term[:-3]}z')
    if len(term) > 4 and term.endswith('es'):
        variants.add(term[:-2])
    if len(term) > 3 and term.endswith('s'):
        variants.add(term[:-1])
    return {variant for variant in variants if len(variant) >= 3}


def expanded_term_set(terms: list[str]) -> set[str]:
    expanded: set[str] = set()
    for term in terms:
        expanded.update(term_variants(term))
    return expanded


def normalize_query_terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw_term in WORD_RE.findall(strip_accents(text.lower())):
        term = raw_term.strip('_')
        if len(term) < 3 or term in SPANISH_STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def score_chunk(question_terms: list[str], chunk: dict[str, Any]) -> tuple[float, list[str]]:
    if not question_terms:
        return 0.0, []

    searchable = ' '.join(
        str(value or '')
        for value in (
            chunk.get('chunk_text'),
            chunk.get('document_title'),
            chunk.get('section_path'),
            chunk.get('source_uri'),
        )
    ).lower()
    chunk_terms = normalize_query_terms(searchable)
    if not chunk_terms:
        return 0.0, []

    chunk_term_set = set(chunk_terms)
    chunk_variant_set = expanded_term_set(chunk_terms)
    matched_terms = [term for term in question_terms if term_variants(term) & chunk_variant_set]
    if not matched_terms:
        return 0.0, []

    coverage = len(matched_terms) / len(question_terms)
    density = len(matched_terms) / max(len(chunk_term_set), 1)
    section_terms = expanded_term_set(normalize_query_terms(str(chunk.get('section_path') or '')))
    title_terms = expanded_term_set(normalize_query_terms(str(chunk.get('document_title') or '')))
    section_boost = 0.05 if any(term_variants(term) & section_terms for term in matched_terms) else 0.0
    title_boost = 0.05 if any(term_variants(term) & title_terms for term in matched_terms) else 0.0
    score = min(1.0, (coverage * 0.75) + (density * 0.15) + section_boost + title_boost)
    return round(score, 4), matched_terms


def rank_chunks(question: str, chunks: list[dict[str, Any]], *, max_chunks: int = DEFAULT_MAX_CHUNKS) -> list[RetrievalMatch]:
    question_terms = normalize_query_terms(question)
    scored: list[RetrievalMatch] = []
    for chunk in chunks:
        score, matched_terms = score_chunk(question_terms, chunk)
        if score <= 0:
            continue
        scored.append(
            RetrievalMatch(
                id=chunk['id'],
                document_id=chunk['document_id'],
                document_title=chunk.get('document_title') or 'Documento sin título',
                source_uri=chunk.get('source_uri'),
                source_type=chunk.get('source_type') or 'manual',
                document_type=chunk.get('document_type') or 'reference',
                visibility=chunk.get('visibility') or 'tenant',
                chunk_index=chunk.get('chunk_index') or 0,
                section_path=chunk.get('section_path'),
                chunk_text=chunk.get('chunk_text') or '',
                token_count=chunk.get('token_count') or 0,
                score=score,
                matched_terms=matched_terms,
                metadata=chunk.get('metadata') or {},
            )
        )

    return sorted(scored, key=lambda match: (-match.score, match.document_title, match.chunk_index))[:max_chunks]


def chunk_excerpt(text: str, *, limit: int = 520) -> str:
    normalized = re.sub(r'\s+', ' ', text).strip()
    if len(normalized) <= limit:
        return normalized
    return f'{normalized[: limit - 1].rstrip()}…'


def build_grounded_answer(question: str, matches: list[RetrievalMatch], *, min_score: float = DEFAULT_MIN_SCORE) -> dict[str, Any]:
    sufficient_context = bool(matches) and matches[0].score >= min_score
    if not sufficient_context:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': None,
            'reason': 'No hay evidencia activa suficiente en la base de conocimiento para responder con trazabilidad.',
            'handoff': {'required': True, 'reason': 'knowledge_context_insufficient'},
        }

    best = matches[0]
    source_label = best.source_uri or best.document_title
    answer = (
        f"Con la evidencia disponible en \"{best.document_title}\", la respuesta sugerida es: "
        f"{chunk_excerpt(best.chunk_text)} Fuente: {source_label}."
    )
    return {
        'status': 'answered',
        'sufficient_context': True,
        'answer': answer,
        'reason': 'Respuesta generada únicamente con chunks activos recuperados.',
        'handoff': {'required': False, 'reason': None},
    }


def retrieval_match_to_dict(match: RetrievalMatch) -> dict[str, Any]:
    return {
        'id': str(match.id),
        'document_id': str(match.document_id),
        'document_title': match.document_title,
        'source_uri': match.source_uri,
        'source_type': match.source_type,
        'document_type': match.document_type,
        'visibility': match.visibility,
        'chunk_index': match.chunk_index,
        'section_path': match.section_path,
        'chunk_text': match.chunk_text,
        'excerpt': chunk_excerpt(match.chunk_text),
        'token_count': match.token_count,
        'score': match.score,
        'matched_terms': match.matched_terms,
        'metadata': match.metadata,
    }
