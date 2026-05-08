from pathlib import Path

ADMIN_ROUTES = Path('app/admin/routes.py')


def _core_api_headers_source() -> str:
    source = ADMIN_ROUTES.read_text()
    start = source.index('def _core_api_headers(')
    end = source.index('\ndef _namespaced_claim', start)
    return source[start:end]


def _admin_session_source() -> str:
    source = ADMIN_ROUTES.read_text()
    start = source.index("@router.get('/admin/api/session')")
    end = source.index("@router.api_route(", start)
    return source[start:end]


def test_admin_proxy_does_not_forward_browser_authorization_header():
    source = _core_api_headers_source()

    assert "request.headers.get('authorization')" not in source
    assert "request.headers.get(\"authorization\")" not in source
    assert 'session[\'access_token\']' in source


def test_admin_session_payload_does_not_expose_access_token_to_javascript():
    source = _admin_session_source()

    assert 'accessToken' not in source
    assert "session['access_token']" not in source
