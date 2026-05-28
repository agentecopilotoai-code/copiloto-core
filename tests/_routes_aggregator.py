"""Aggregator helper for static tests after the routes.py refactor.

Historical context: `app/api/v1/routes.py` was a 15K-LOC monolith and ~96
static tests asserted on its source via `Path('copiloto_core/api/v1/routes.py').read_text()`.
The refactor extracts pure helpers to `app/api/v1/_helpers/` and handlers to
`app/api/v1/handlers/`, so a single `read_text()` call no longer sees the
whole API surface.

This helper concatenates the source of all the refactored modules so static
tests can keep doing substring asserts without caring which file the symbol
lives in. The order is deterministic (alphabetical within each tier) so test
output (line numbers, slice offsets) is stable across runs.

Usage:
    from tests._routes_aggregator import routes_aggregated_source
    src = routes_aggregated_source()
    assert "@platform_admin_router.get('/platform/incidents')" in src
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


_ROUTES_FILE = Path('copiloto_core/api/v1/routes.py')
_HELPERS_DIR = Path('copiloto_core/api/v1/_helpers')
_HANDLERS_DIR = Path('copiloto_core/api/v1/handlers')


@lru_cache(maxsize=1)
def routes_aggregated_source() -> str:
    """Concatenated source of routes.py + all refactored modules.

    Cached at module load to avoid hitting disk N times across a test run.
    Use `invalidate_aggregated_source_cache()` if you mutate files at runtime
    (rare — only relevant for the refactor's own test scaffolding).
    """
    parts: list[str] = []
    if _ROUTES_FILE.exists():
        parts.append(_ROUTES_FILE.read_text(encoding='utf-8'))
    for directory in (_HELPERS_DIR, _HANDLERS_DIR):
        if not directory.exists():
            continue
        for path in sorted(directory.rglob('*.py')):
            if path.name == '__init__.py':
                # __init__.py is usually just re-exports; skip to keep the
                # aggregate close to the original routes.py shape.
                continue
            parts.append(path.read_text(encoding='utf-8'))
    return '\n'.join(parts)


def invalidate_aggregated_source_cache() -> None:
    """Test scaffolding only — drop the cache so the next call re-reads disk."""
    routes_aggregated_source.cache_clear()
