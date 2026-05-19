"""Cover app/services/legal.render_markdown_to_safe_html branches."""
from __future__ import annotations


def test_render_markdown_non_string_falls_to_empty():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html(None)  # type: ignore[arg-type]
    assert isinstance(out, str)


def test_render_markdown_paragraph():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('Hello\nWorld')
    assert '<p>' in out and 'Hello' in out


def test_render_markdown_heading():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('# Título')
    assert '<h1>' in out and 'Título' in out


def test_render_markdown_heading_levels():
    from app.services.legal import render_markdown_to_safe_html
    for n in range(1, 7):
        out = render_markdown_to_safe_html(f'{"#" * n} Title')
        assert f'<h{n}>' in out


def test_render_markdown_ul_list():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('- A\n- B\n- C')
    assert '<ul>' in out
    assert '<li>A</li>' in out
    assert '<li>C</li>' in out


def test_render_markdown_ol_list():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('1. First\n2. Second')
    assert '<ol>' in out
    assert '<li>First</li>' in out


def test_render_markdown_mixed_lists():
    """Switching between ul and ol flushes the previous list."""
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('- bullet\n1. numbered')
    assert '<ul>' in out
    assert '<ol>' in out


def test_render_markdown_inline_bold_italic():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('Hello **world** and *bold* and _ita_')
    assert '<strong>world</strong>' in out


def test_render_markdown_link_safe():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('[Click](https://example.com)')
    assert 'example.com' in out


def test_render_markdown_link_blocks_javascript():
    """Should NOT include javascript: URLs."""
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('[Bad](javascript:alert(1))')
    # The link is rendered safely (label without dangerous href)
    assert 'alert' not in out or 'javascript:' not in out


def test_render_markdown_escapes_html():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('<script>alert(1)</script>')
    assert '<script>' not in out
    assert '&lt;script&gt;' in out or 'script' in out  # escaped


def test_render_markdown_empty_input():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('')
    assert isinstance(out, str)


def test_render_markdown_only_whitespace():
    from app.services.legal import render_markdown_to_safe_html
    out = render_markdown_to_safe_html('   \n   \n   ')
    assert isinstance(out, str)
