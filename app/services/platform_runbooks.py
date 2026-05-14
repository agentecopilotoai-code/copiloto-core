"""UI-006.6 — Platform runbooks catalogue.

The runbooks live as static Markdown files in ``docs/runbooks/`` (one per
incident type, indexed by ``docs/runbooks/README.md``). This module lists them
and reads individual files for the platform-owner "Runbooks" view. Rendering to
safe HTML is delegated to ``app.services.legal.render_markdown_to_safe_html``
(TASK-0076) — the same limited, fully-escaped Markdown subset used for public
legal pages.

Path-traversal defense: slugs are matched against a strict
``^[a-z0-9][a-z0-9-]*$`` pattern and the resolved path is verified to live
inside ``docs/runbooks/`` before any file read.
"""

from __future__ import annotations

import re
from pathlib import Path

# app/services/platform_runbooks.py -> parents[2] is the repo root.
RUNBOOKS_DIR = Path(__file__).resolve().parents[2] / 'docs' / 'runbooks'

RUNBOOK_SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]*$')

# Coarse categories derived from the slug — the runbook files carry no explicit
# category metadata, so keyword rules keep the derivation honest and testable.
_CATEGORY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (('meta-', 'whatsapp'), 'Meta · WhatsApp'),
    (('llm', 'circuit-breaker'), 'LLM · Breakers'),
    (('postgres', 'worker', 'scheduler'), 'Infraestructura'),
    (('webhook', 'rate-limit'), 'Tráfico · Rate limit'),
    (('consent',), 'Compliance'),
)


def categorize_runbook(slug: str | None) -> str:
    """Derive a coarse category from the runbook slug. Falls back to 'General'."""
    lowered = (slug or '').lower()
    for keywords, category in _CATEGORY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    return 'General'


def extract_title(content_md: str | None) -> str:
    """Return the first level-1 Markdown heading of a runbook, or a fallback."""
    for raw_line in (content_md or '').splitlines():
        match = re.match(r'^#\s+(.+)$', raw_line.strip())
        if match:
            return match.group(1).strip()
    return 'Runbook'


def is_valid_slug(slug: str | None) -> bool:
    """True when `slug` is a safe runbook identifier (no dots, no separators)."""
    if not slug or '..' in slug or '/' in slug or '\\' in slug:
        return False
    return bool(RUNBOOK_SLUG_PATTERN.match(slug))


def runbook_path(slug: str | None) -> Path | None:
    """Resolve a slug to a path *inside* the runbooks dir, or None.

    Returns None when the slug is invalid, the resolved path escapes the
    runbooks directory, or the file does not exist — never raises.
    """
    if not is_valid_slug(slug):
        return None
    base = RUNBOOKS_DIR.resolve()
    candidate = (base / f'{slug}.md').resolve()
    if base != candidate.parent:
        return None
    if not candidate.is_file():
        return None
    return candidate


def list_runbooks() -> list[dict]:
    """List the runbook files in ``docs/runbooks/`` (README excluded).

    Each entry carries `slug`, `filename`, `title`, `category` and
    `size_bytes`. Sorted by title.
    """
    base = RUNBOOKS_DIR.resolve()
    if not base.is_dir():
        return []
    items: list[dict] = []
    for path in base.glob('*.md'):
        if path.name.lower() == 'readme.md':
            continue
        content = path.read_text(encoding='utf-8', errors='replace')
        items.append({
            'slug': path.stem,
            'filename': path.name,
            'title': extract_title(content),
            'category': categorize_runbook(path.stem),
            'size_bytes': path.stat().st_size,
        })
    items.sort(key=lambda item: item['title'].lower())
    return items


def read_runbook(slug: str | None) -> dict | None:
    """Return ``{slug, filename, title, category, content_md}`` for a runbook,
    or None when the slug is invalid / the file does not exist."""
    path = runbook_path(slug)
    if path is None:
        return None
    content = path.read_text(encoding='utf-8', errors='replace')
    return {
        'slug': path.stem,
        'filename': path.name,
        'title': extract_title(content),
        'category': categorize_runbook(path.stem),
        'content_md': content,
    }
