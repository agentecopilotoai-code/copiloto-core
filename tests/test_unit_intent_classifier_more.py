"""Additional unit tests for app/services/intent_classifier.py to push coverage."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace


def _run(coro):
    return asyncio.run(coro)


# ─── _compile_tenant_rules ────────────────────────────────────────────────


def test_compile_tenant_rules_skips_unknown_intent():
    from app.services.intent_classifier import _compile_tenant_rules
    rules = _compile_tenant_rules({'totally_made_up': ['foo']})
    assert rules == []


def test_compile_tenant_rules_skips_empty_list():
    from app.services.intent_classifier import _compile_tenant_rules
    rules = _compile_tenant_rules({'faq': []})
    assert rules == []


def test_compile_tenant_rules_strips_and_skips_blank():
    from app.services.intent_classifier import _compile_tenant_rules
    rules = _compile_tenant_rules({'faq': ['  ', 'hola']})
    assert len(rules) == 1
    pat, intent, conf = rules[0]
    assert intent == 'faq'
    assert conf == 0.85
    assert pat.search('hola mundo') is not None


def test_compile_tenant_rules_escapes_special_chars():
    from app.services.intent_classifier import _compile_tenant_rules
    # special regex chars in the keyword shouldn't blow up
    rules = _compile_tenant_rules({'faq': ['hello.world+']})
    assert len(rules) == 1


# ─── _rule_classify ───────────────────────────────────────────────────────


def test_rule_classify_returns_none_when_no_match():
    from app.services.intent_classifier import _rule_classify, ALL_INTENTS
    out = _rule_classify('xyz random gibberish 123', set(ALL_INTENTS), [])
    assert out is None


def test_rule_classify_skips_disabled_intents():
    from app.services.intent_classifier import _rule_classify
    out = _rule_classify('hola', set(), [])
    assert out is None


def test_rule_classify_prefers_highest_confidence():
    from app.services.intent_classifier import _rule_classify, ALL_INTENTS
    # 'cancelar cita' should hit the high-confidence cancel rule
    out = _rule_classify('quiero cancelar cita ya mismo', set(ALL_INTENTS), [])
    assert out is not None
    assert out.intent == 'cancel_appointment'


def test_rule_classify_tenant_rules_apply():
    from app.services.intent_classifier import _rule_classify, _compile_tenant_rules, ALL_INTENTS
    tenant_rules = _compile_tenant_rules({'book_appointment': ['agéndame']})
    out = _rule_classify('agéndame por favor', set(ALL_INTENTS), tenant_rules)
    assert out is not None
    assert out.intent == 'book_appointment'


# ─── _llm_classify ────────────────────────────────────────────────────────


def test_llm_classify_no_provider_no_api_key_no_ollama(monkeypatch):
    """When cloud is gated and Ollama fails, returns None."""
    from app.services import intent_classifier

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise RuntimeError('connection refused')

    import httpx
    monkeypatch.setattr(httpx, 'AsyncClient', _FakeClient)

    settings = SimpleNamespace(
        cloud_llm_provider=None,
        cloud_llm_api_key=None,
        local_llm_base_url='http://x:11434',
        local_llm_model='m',
        local_llm_timeout_seconds=1,
        cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hola', {'faq', 'greeting'}, settings, tenant_no_train=True))
    assert out is None


def test_llm_classify_cloud_blocked_by_no_train(monkeypatch):
    """tenant_no_train=True blocks cloud and falls back to ollama (which we make fail)."""
    from app.services import intent_classifier

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise RuntimeError('boom')

    import httpx
    monkeypatch.setattr(httpx, 'AsyncClient', _FakeClient)

    settings = SimpleNamespace(
        cloud_llm_provider='claude',
        cloud_llm_api_key='sk-...',
        local_llm_base_url='http://x:11434',
        local_llm_model='m',
        local_llm_timeout_seconds=1,
        cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hola', {'faq'}, settings, tenant_no_train=True))
    assert out is None


def test_llm_classify_ollama_returns_intent(monkeypatch):
    """Patch httpx.AsyncClient to simulate a successful Ollama response."""
    from app.services import intent_classifier

    class _FakeResponse:
        def json(self):
            return {'message': {'content': 'faq'}}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return _FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, 'AsyncClient', _FakeClient)

    settings = SimpleNamespace(
        cloud_llm_provider=None,
        cloud_llm_api_key=None,
        local_llm_base_url='http://x:11434',
        local_llm_model='m',
        local_llm_timeout_seconds=1,
        cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hi', {'faq', 'greeting'}, settings, tenant_no_train=True))
    assert out is not None
    assert out.intent == 'faq'
    assert out.resolved_by == 'llm'


def test_llm_classify_ollama_returns_unknown_intent(monkeypatch):
    """An intent not in ALL_INTENTS returns None."""
    from app.services import intent_classifier

    class _FakeResponse:
        def json(self):
            return {'message': {'content': 'random_unknown_intent'}}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return _FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, 'AsyncClient', _FakeClient)

    settings = SimpleNamespace(
        cloud_llm_provider=None, cloud_llm_api_key=None,
        local_llm_base_url='http://x:11434', local_llm_model='m',
        local_llm_timeout_seconds=1, cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hi', {'faq', 'greeting'}, settings, tenant_no_train=True))
    assert out is None


def test_llm_classify_cloud_claude_success(monkeypatch):
    """Patch anthropic.AsyncAnthropic to simulate a successful claude response."""
    from app.services import intent_classifier

    class _FakeMessage:
        def __init__(self, text):
            self.content = [SimpleNamespace(text=text)]

    class _FakeMessages:
        async def create(self, **kw):
            return _FakeMessage('faq')

    class _FakeClient:
        def __init__(self, **kw):
            self.messages = _FakeMessages()

    import sys
    fake_anthropic = SimpleNamespace(AsyncAnthropic=_FakeClient)
    monkeypatch.setitem(sys.modules, 'anthropic', fake_anthropic)

    settings = SimpleNamespace(
        cloud_llm_provider='claude',
        cloud_llm_api_key='sk',
        cloud_llm_model='claude-x',
        cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hi', {'faq'}, settings, tenant_no_train=False))
    assert out is not None
    assert out.intent == 'faq'


def test_llm_classify_cloud_openai_success(monkeypatch):
    from app.services import intent_classifier

    class _FakeChoice:
        def __init__(self, c):
            self.message = SimpleNamespace(content=c)

    class _FakeResp:
        def __init__(self, c):
            self.choices = [_FakeChoice(c)]

    class _FakeCompletions:
        async def create(self, **kw):
            return _FakeResp('greeting')

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kw):
            self.chat = _FakeChat()

    import sys
    fake_openai = SimpleNamespace(AsyncOpenAI=_FakeClient)
    monkeypatch.setitem(sys.modules, 'openai', fake_openai)

    settings = SimpleNamespace(
        cloud_llm_provider='openai',
        cloud_llm_api_key='sk',
        cloud_llm_model='gpt-x',
        cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hi', {'greeting'}, settings, tenant_no_train=False))
    assert out is not None
    assert out.intent == 'greeting'


def test_llm_classify_cloud_provider_raises(monkeypatch):
    """An exception from the SDK is caught and returns None."""
    from app.services import intent_classifier

    class _Boom:
        def __init__(self, **kw):
            raise RuntimeError('boom')

    import sys
    fake_anthropic = SimpleNamespace(AsyncAnthropic=_Boom)
    monkeypatch.setitem(sys.modules, 'anthropic', fake_anthropic)

    settings = SimpleNamespace(
        cloud_llm_provider='claude', cloud_llm_api_key='sk',
        cloud_llm_model='m', cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hi', {'faq'}, settings, tenant_no_train=False))
    assert out is None


def test_llm_classify_cloud_timeout(monkeypatch):
    """asyncio.TimeoutError from the SDK returns None."""
    from app.services import intent_classifier

    class _FakeMessages:
        async def create(self, **kw):
            raise asyncio.TimeoutError()

    class _FakeClient:
        def __init__(self, **kw):
            self.messages = _FakeMessages()

    import sys
    fake_anthropic = SimpleNamespace(AsyncAnthropic=_FakeClient)
    monkeypatch.setitem(sys.modules, 'anthropic', fake_anthropic)

    settings = SimpleNamespace(
        cloud_llm_provider='claude', cloud_llm_api_key='sk',
        cloud_llm_model='m', cloud_llm_timeout_seconds=1,
    )
    out = _run(intent_classifier._llm_classify('hi', {'faq'}, settings, tenant_no_train=False))
    assert out is None


# ─── classify_intent (orchestrator) ───────────────────────────────────────


def test_classify_intent_rule_high_confidence_returns_immediately():
    from app.services.intent_classifier import classify_intent
    settings = SimpleNamespace()
    # 'agendar' matches book_appointment with conf 0.93 (>= 0.78)
    out = _run(classify_intent('agendar', settings=settings))
    assert out.intent == 'book_appointment'
    assert out.resolved_by == 'rule'


def test_classify_intent_complaint_forced_for_high_conf():
    from app.services.intent_classifier import classify_intent
    settings = SimpleNamespace()
    out = _run(classify_intent('esto es un fraude horrible', settings=settings))
    assert out.intent == 'complaint_or_risk'


def test_classify_intent_no_rule_no_llm_falls_back_to_faq(monkeypatch):
    """When nothing matches and Ollama is unreachable, fall back to faq."""
    from app.services import intent_classifier
    from app.services.intent_classifier import classify_intent

    async def _none_llm(*a, **kw):
        return None

    monkeypatch.setattr(intent_classifier, '_llm_classify', _none_llm)

    settings = SimpleNamespace()
    out = _run(classify_intent('xyz 123 random gibberish', settings=settings, tenant_no_train=True))
    assert out.intent == 'faq'
    assert out.resolved_by == 'fallback'


def test_classify_intent_uses_custom_tenant_keywords():
    from app.services.intent_classifier import classify_intent
    settings = SimpleNamespace()
    out = _run(classify_intent(
        'hellokeyword random',
        settings=settings,
        tenant_config={'custom_keywords': {'book_appointment': ['hellokeyword']}},
    ))
    # custom keyword conf is 0.85 (>= 0.78)
    assert out.intent == 'book_appointment'


def test_classify_intent_empty_enabled_intents_falls_back_to_all():
    from app.services.intent_classifier import classify_intent
    settings = SimpleNamespace()
    out = _run(classify_intent('hola', settings=settings, tenant_config={'enabled_intents': []}))
    assert out.intent in {'greeting'}


def test_classify_intent_falls_back_to_complaint_when_llm_says_so(monkeypatch):
    from app.services import intent_classifier
    from app.services.intent_classifier import classify_intent

    async def _fake_llm(text, enabled, settings, *, tenant_no_train=None):
        return intent_classifier.IntentResult(
            intent='complaint_or_risk',
            confidence=0.40,  # below min
            resolved_by='llm',
        )

    monkeypatch.setattr(intent_classifier, '_llm_classify', _fake_llm)

    settings = SimpleNamespace()
    out = _run(classify_intent('xyz unrecognized text', settings=settings))
    assert out.intent == 'complaint_or_risk'
    assert out.resolved_by == 'fallback'


def test_classify_intent_rule_meets_min_conf_below_llm_threshold(monkeypatch):
    """Rule layer returns a match between min_conf and LLM threshold; LLM returns None.
    Rule result wins as 'rule_min'."""
    from app.services import intent_classifier
    from app.services.intent_classifier import classify_intent, IntentResult

    # Mock _rule_classify to return mid-confidence result on first call (full set),
    # and None on second call (complaint check).
    calls = {'n': 0}

    def fake_rule(text, enabled, tenant_rules):
        calls['n'] += 1
        if calls['n'] == 1:
            return IntentResult(intent='faq', confidence=0.72, resolved_by='rule', layer_detail='x')
        return None

    async def _fake_llm(text, enabled, settings, *, tenant_no_train=None):
        return None

    monkeypatch.setattr(intent_classifier, '_rule_classify', fake_rule)
    monkeypatch.setattr(intent_classifier, '_llm_classify', _fake_llm)

    settings = SimpleNamespace()
    out = _run(classify_intent('???', settings=settings))
    assert out.intent == 'faq'


def test_classify_intent_llm_result_above_min_conf(monkeypatch):
    """LLM returns a high-confidence result and we don't have a high-conf rule match."""
    from app.services import intent_classifier
    from app.services.intent_classifier import classify_intent, IntentResult

    async def _fake_llm(text, enabled, settings, *, tenant_no_train=None):
        return IntentResult(
            intent='check_availability', confidence=0.80, resolved_by='llm',
        )

    monkeypatch.setattr(intent_classifier, '_llm_classify', _fake_llm)

    settings = SimpleNamespace()
    out = _run(classify_intent('uniquegibberishstring', settings=settings))
    assert out.intent == 'check_availability'
    assert out.resolved_by == 'llm'
