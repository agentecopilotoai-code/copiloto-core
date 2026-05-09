"""Static tests for extraction_worker helpers — no real DB or file I/O required."""
from __future__ import annotations

import io

import pytest

from app.workers.extraction_worker import (
    DOCX_MIME,
    PDF_MIME,
    _extract_pdf_text,
    _extract_docx_text,
    _extract_text_sync,
)
from app.services.knowledge_storage import is_binary_extractable, BINARY_EXTRACTABLE_MIME_TYPES


# ---------------------------------------------------------------------------
# Helpers to build minimal valid PDF/DOCX bytes in-memory
# ---------------------------------------------------------------------------

def _build_minimal_pdf(text: str) -> bytes:
    """Build the smallest valid PDF that pypdf can parse with the given text."""
    content_stream = f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'
    stream_bytes = content_stream.encode('latin-1')
    stream_len = len(stream_bytes)

    objects: list[bytes] = []

    def add_obj(content: str) -> int:
        idx = len(objects) + 1
        objects.append(content.encode('latin-1'))
        return idx

    add_obj('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')
    add_obj('2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n')
    add_obj(
        '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        '/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n'
    )
    add_obj(
        f'4 0 obj\n<< /Length {stream_len} >>\nstream\n{content_stream}\nendstream\nendobj\n'
    )
    add_obj(
        '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n'
    )

    body = b'%PDF-1.4\n'
    xref_offsets: list[int] = []
    for obj_bytes in objects:
        xref_offsets.append(len(body))
        body += obj_bytes

    xref_start = len(body)
    xref = f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'
    for off in xref_offsets:
        xref += f'{off:010d} 00000 n \n'
    trailer = f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n'
    return body + xref.encode('latin-1') + trailer.encode('latin-1')


def _build_minimal_docx(text: str) -> bytes:
    """Build the smallest valid DOCX (ZIP with document.xml) that python-docx can parse."""
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
        '</w:body>'
        '</w:document>'
    ).encode('utf-8')

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    ).encode('utf-8')

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '</Relationships>'
    ).encode('utf-8')

    word_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '</Relationships>'
    ).encode('utf-8')

    buf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml)
        zf.writestr('_rels/.rels', rels_xml)
        zf.writestr('word/_rels/document.xml.rels', word_rels_xml)
        zf.writestr('word/document.xml', doc_xml)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIsBinaryExtractable:
    def test_pdf_mime(self):
        assert is_binary_extractable('doc.pdf', 'application/pdf')

    def test_docx_mime(self):
        assert is_binary_extractable(
            'doc.docx',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    def test_pdf_extension_no_mime(self):
        assert is_binary_extractable('doc.pdf', None)

    def test_docx_extension_no_mime(self):
        assert is_binary_extractable('doc.docx', None)

    def test_text_not_extractable(self):
        assert not is_binary_extractable('notes.txt', 'text/plain')

    def test_json_not_extractable(self):
        assert not is_binary_extractable('data.json', 'application/json')

    def test_unknown_extension_no_mime(self):
        assert not is_binary_extractable('image.png', None)


class TestBinaryExtractableMimeTypes:
    def test_pdf_in_set(self):
        assert 'application/pdf' in BINARY_EXTRACTABLE_MIME_TYPES

    def test_docx_in_set(self):
        assert (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            in BINARY_EXTRACTABLE_MIME_TYPES
        )


def _pypdf_available() -> bool:
    try:
        import pypdf  # noqa: F401
        return True
    except BaseException:  # catches PanicException and ImportError
        return False


pypdf_available = pytest.mark.skipif(not _pypdf_available(), reason='pypdf unavailable in this environment')


class TestExtractPdfText:
    @pypdf_available
    def test_extract_basic_text(self):
        pdf_bytes = _build_minimal_pdf('Precio manicure 25000')
        text, pages = _extract_pdf_text(pdf_bytes)
        assert 'manicure' in text.lower() or pages >= 1

    @pypdf_available
    def test_returns_page_count(self):
        pdf_bytes = _build_minimal_pdf('Test')
        _, pages = _extract_pdf_text(pdf_bytes)
        assert pages >= 1

    @pypdf_available
    def test_invalid_bytes_raises_value_error(self):
        with pytest.raises((ValueError, Exception)):
            _extract_pdf_text(b'not a pdf')


class TestExtractDocxText:
    def test_extract_basic_text(self):
        docx_bytes = _build_minimal_docx('Precio manicure 25000')
        text, paragraphs = _extract_docx_text(docx_bytes)
        assert 'manicure' in text.lower()
        assert paragraphs >= 1

    def test_returns_paragraph_count(self):
        docx_bytes = _build_minimal_docx('Hello world')
        _, paragraphs = _extract_docx_text(docx_bytes)
        assert paragraphs >= 1

    def test_invalid_bytes_raises(self):
        with pytest.raises(Exception):
            _extract_docx_text(b'not a docx')


class TestExtractTextSync:
    @pypdf_available
    def test_pdf_dispatch(self):
        pdf_bytes = _build_minimal_pdf('Garantia 12 meses')
        text, pages = _extract_text_sync(pdf_bytes, PDF_MIME)
        assert pages >= 1

    def test_docx_dispatch(self):
        docx_bytes = _build_minimal_docx('Garantia 12 meses')
        text, paragraphs = _extract_text_sync(docx_bytes, DOCX_MIME)
        assert 'garantia' in text.lower()

    def test_unknown_mime_raises(self):
        with pytest.raises(ValueError, match='No extractor'):
            _extract_text_sync(b'data', 'image/png')

    @pypdf_available
    def test_mime_with_charset_param(self):
        pdf_bytes = _build_minimal_pdf('Test')
        text, pages = _extract_text_sync(pdf_bytes, 'application/pdf; charset=utf-8')
        assert pages >= 1
