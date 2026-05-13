"""TASK-0076 — Páginas legales por tenant.

Provides:

* :func:`render_markdown_to_safe_html` — pure-Python subset Markdown renderer
  that escapes every input before applying inline / block transformations.
  Only a deliberately small set of constructs is supported (headings ``#``..
  ``######``, paragraphs, ordered / unordered lists, inline ``**bold**``,
  ``*italic*``, ``` `code` ``` and ``[label](https://...)`` autolinks).
  Anything else, including raw HTML / script tags, is escaped verbatim. The
  link allowlist accepts only ``http(s)://`` and ``mailto:`` schemes; ``js:``
  /``javascript:`` and ``data:`` URIs are dropped.
* :func:`legal_public_url` — builds the public URL the bot uses in the
  consent template footer and on campaign signatures.

The renderer is intentionally tiny: legal pages are short, the corpus is
trusted (tenant admin authors it), and we want a sandboxed pure-Python
implementation we can statically audit instead of pulling in a third-party
markdown + bleach stack.
"""

from __future__ import annotations

import html
import re
from uuid import UUID

LEGAL_KINDS = ('terms', 'privacy', 'consent')
LEGAL_KIND_LABELS_ES = {
    'terms': 'Términos y Condiciones',
    'privacy': 'Política de Privacidad',
    'consent': 'Aviso de Tratamiento de Datos',
}

_ALLOWED_LINK_SCHEMES = ('http://', 'https://', 'mailto:')
_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_BOLD_RE = re.compile(r'\*\*([^*]+)\*\*')
_ITALIC_RE = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')
_CODE_RE = re.compile(r'`([^`\n]+)`')


def _safe_link(label: str, target: str) -> str:
    lowered = target.lower().strip()
    if not any(lowered.startswith(scheme) for scheme in _ALLOWED_LINK_SCHEMES):
        return html.escape(label)
    safe_target = html.escape(target, quote=True)
    safe_label = html.escape(label)
    return f'<a href="{safe_target}" rel="nofollow noopener noreferrer">{safe_label}</a>'


def _render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = _CODE_RE.sub(lambda m: f'<code>{m.group(1)}</code>', escaped)
    escaped = _BOLD_RE.sub(lambda m: f'<strong>{m.group(1)}</strong>', escaped)
    escaped = _ITALIC_RE.sub(lambda m: f'<em>{m.group(1)}</em>', escaped)

    def _link_sub(match: re.Match[str]) -> str:
        label = html.unescape(match.group(1))
        target = html.unescape(match.group(2))
        return _safe_link(label, target)

    escaped = _LINK_RE.sub(_link_sub, escaped)
    return escaped


def render_markdown_to_safe_html(content_md: str) -> str:
    """Render the limited Markdown subset to HTML, escaping everything else.

    The output is wrapped in ``<article class="legal-document">`` so the
    consumer (the public legal page) can style it.  No external CSS is
    injected — the host page provides the styles.
    """
    if not isinstance(content_md, str):
        content_md = ''
    lines = content_md.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocks: list[str] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append('<p>' + ' '.join(_render_inline(part) for part in paragraph) + '</p>')
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_kind, list_items
        if list_kind is not None and list_items:
            tag = list_kind
            body = ''.join(f'<li>{_render_inline(it)}</li>' for it in list_items)
            blocks.append(f'<{tag}>{body}</{tag}>')
        list_kind = None
        list_items = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f'<h{level}>{_render_inline(heading.group(2).strip())}</h{level}>')
            continue
        ul_item = re.match(r'^[-*+]\s+(.+)$', stripped)
        if ul_item:
            flush_paragraph()
            if list_kind not in (None, 'ul'):
                flush_list()
            list_kind = 'ul'
            list_items.append(ul_item.group(1).strip())
            continue
        ol_item = re.match(r'^\d+\.\s+(.+)$', stripped)
        if ol_item:
            flush_paragraph()
            if list_kind not in (None, 'ol'):
                flush_list()
            list_kind = 'ol'
            list_items.append(ol_item.group(1).strip())
            continue
        flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return '<article class="legal-document">' + ''.join(blocks) + '</article>'


def legal_public_url(base_url: str, tenant_id: UUID | str, kind: str) -> str:
    """Build the public URL the bot references in the consent template footer.

    Falls back to the bare path when ``base_url`` is empty so the link is
    still parseable in plain-text rendering (the WhatsApp client linkifies
    relative paths preceded by https only — that case is the operator's
    responsibility to configure).
    """
    if kind not in LEGAL_KINDS:
        raise ValueError(f'Unknown legal kind: {kind}')
    base = (base_url or '').rstrip('/')
    return f'{base}/v1/tenants/{tenant_id}/legal/{kind}'
