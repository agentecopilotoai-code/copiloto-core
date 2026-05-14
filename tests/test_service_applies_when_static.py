"""TASK-0054 — Filtrado dinámico de servicios en booking según calificación.

Cubre:
  * Schema: `service_catalog.applies_when` y `qualification_questions.key`.
  * API Pydantic: campos nuevos opt-in en `ServiceCreate/Update` y
    `QualificationQuestion*`.
  * Routes: proyección de columnas, normalización al insertar/actualizar.
  * Evaluador puro `segments.evaluate_rules` con todos los operadores.
  * Booking flow: filtrado por facts, auto-select cuando queda 1 servicio,
    return None cuando 0 servicios matchean.
  * Admin Panel: rule builder en ServiceCatalog y campo `key` en el panel
    de calificación.
"""
from __future__ import annotations

from pathlib import Path

from app.services.booking_flow import (
    _filter_services_by_qualification,
    _qualification_facts_from_conversation,
)
from app.services.qualification_flow import build_qualification_facts
from app.services.segments import (
    APPLIES_WHEN_OPS,
    evaluate_rules,
    normalize_applies_when,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
API_ROUTES = Path('app/api/v1/routes.py')
API_SCHEMAS = Path('app/api/v1/schemas.py')
SEGMENTS = Path('app/services/segments.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
QUALIFICATION_FLOW = Path('app/services/qualification_flow.py')
# UI-007.4: the ServiceCatalog monolith was split into a feature directory.
SERVICES_FEATURE = Path('admin-panel/src/features/owner-admin/services')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')


def _services_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(SERVICES_FEATURE.rglob('*.js*'))
    )


def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))


# ───── Schema ─────


def test_schema_adds_applies_when_to_service_catalog():
    schema = SCHEMA.read_text()
    assert "applies_when jsonb not null default '{}'::jsonb" in schema


def test_schema_adds_key_to_qualification_questions():
    schema = SCHEMA.read_text()
    assert "key text check (key is null or key ~ '^[a-z][a-z0-9_]{0,59}$')" in schema
    assert (
        'create unique index uq_qualification_questions_tenant_key' in schema
    )
    assert 'on app.qualification_questions(tenant_id, key) where key is not null' in schema


# ───── Pydantic ─────


def test_pydantic_service_create_includes_applies_when_default_empty():
    source = API_SCHEMAS.read_text()
    assert 'applies_when: dict[str, Any] = Field(default_factory=dict)' in source
    assert 'applies_when: dict[str, Any] | None = None' in source


def test_pydantic_qualification_includes_key_field():
    source = API_SCHEMAS.read_text()
    assert "QUALIFICATION_QUESTION_KEY_PATTERN = '^[a-z][a-z0-9_]{0,59}$'" in source
    assert 'key: str | None = Field(default=None, pattern=QUALIFICATION_QUESTION_KEY_PATTERN)' in source


# ───── Routes ─────


def test_routes_project_and_bind_applies_when():
    source = API_ROUTES.read_text()
    assert "'applies_when'," in source  # projection tuple
    assert 'normalize_applies_when' in source
    assert 'applies_when=coalesce($18::jsonb, applies_when)' in source


def test_routes_project_and_bind_question_key():
    source = API_ROUTES.read_text()
    assert "'applies_to_service_ids, preset, key, created_at, updated_at'" in source
    assert 'key=case when $12::boolean then $11 else key end' in source


# ───── Pure rule evaluator ─────


def test_evaluate_rules_empty_or_invalid_always_matches():
    assert evaluate_rules({}, {}) is True
    assert evaluate_rules(None, {'first_visit': True}) is True
    assert evaluate_rules('not-json', {}) is True
    assert evaluate_rules({'bogus': 'shape'}, {}) is True


def test_evaluate_rules_eq_coerces_strings_and_booleans():
    rule = {'all_of': [{'key': 'first_visit', 'op': 'eq', 'value': True}]}
    assert evaluate_rules(rule, {'first_visit': True}) is True
    assert evaluate_rules(rule, {'first_visit': 'sí'}) is True
    assert evaluate_rules(rule, {'first_visit': False}) is False
    assert evaluate_rules(rule, {}) is False


def test_evaluate_rules_supports_all_documented_operators():
    expected = {
        'eq', 'ne', 'in', 'not_in', 'lt', 'lte', 'gt', 'gte',
        'is_null', 'is_not_null', 'contains_any', 'contains_all',
    }
    assert expected.issubset(APPLIES_WHEN_OPS)

    # eq / ne
    assert evaluate_rules({'key': 'urgency_level', 'op': 'eq', 'value': 'high'},
                          {'urgency_level': 'high'}) is True
    assert evaluate_rules({'key': 'urgency_level', 'op': 'ne', 'value': 'high'},
                          {'urgency_level': 'normal'}) is True

    # in / not_in
    assert evaluate_rules({'key': 'k', 'op': 'in', 'value': ['a', 'b']},
                          {'k': 'a'}) is True
    assert evaluate_rules({'key': 'k', 'op': 'not_in', 'value': ['a', 'b']},
                          {'k': 'c'}) is True

    # lt / lte / gt / gte
    assert evaluate_rules({'key': 'budget_tier', 'op': 'gt', 'value': 500000},
                          {'budget_tier': 800000}) is True
    assert evaluate_rules({'key': 'budget_tier', 'op': 'gte', 'value': 800000},
                          {'budget_tier': 800000}) is True
    assert evaluate_rules({'key': 'budget_tier', 'op': 'lt', 'value': 500000},
                          {'budget_tier': 200000}) is True
    assert evaluate_rules({'key': 'budget_tier', 'op': 'lte', 'value': 200000},
                          {'budget_tier': 200000}) is True

    # is_null / is_not_null
    assert evaluate_rules({'key': 'k', 'op': 'is_null'}, {}) is True
    assert evaluate_rules({'key': 'k', 'op': 'is_not_null'}, {'k': 1}) is True

    # contains_any / contains_all (over array facts)
    assert evaluate_rules({'key': 'symptoms', 'op': 'contains_any', 'value': ['dolor', 'sangrado']},
                          {'symptoms': ['dolor', 'fiebre']}) is True
    assert evaluate_rules({'key': 'symptoms', 'op': 'contains_all', 'value': ['dolor', 'fiebre']},
                          {'symptoms': ['dolor', 'fiebre', 'tos']}) is True
    assert evaluate_rules({'key': 'symptoms', 'op': 'contains_all', 'value': ['dolor', 'fiebre']},
                          {'symptoms': ['dolor']}) is False


def test_evaluate_rules_combines_all_of_and_any_of():
    rule = {
        'all_of': [
            {'key': 'first_visit', 'op': 'eq', 'value': True},
            {'any_of': [
                {'key': 'budget_tier', 'op': 'gte', 'value': 500000},
                {'key': 'urgency_level', 'op': 'eq', 'value': 'high'},
            ]},
        ],
    }
    assert evaluate_rules(rule, {'first_visit': True, 'budget_tier': 800000}) is True
    assert evaluate_rules(rule, {'first_visit': True, 'urgency_level': 'high'}) is True
    assert evaluate_rules(rule, {'first_visit': True, 'budget_tier': 100000}) is False
    assert evaluate_rules(rule, {'first_visit': False, 'budget_tier': 900000}) is False


def test_normalize_applies_when_drops_invalid_predicates():
    normalized = normalize_applies_when({
        'all_of': [
            {'key': 'first_visit', 'op': 'eq', 'value': True},
            {'key': 'BAD KEY', 'op': 'eq', 'value': 1},  # invalid key
            {'key': 'k', 'op': 'unknown', 'value': 1},   # invalid op
            {'key': 'k2', 'op': 'is_null'},               # valid valueless
        ],
    })
    assert normalized == {
        'all_of': [
            {'key': 'first_visit', 'op': 'eq', 'value': True},
            {'key': 'k2', 'op': 'is_null'},
        ],
    }


def test_normalize_applies_when_bare_condition_wrapped_in_all_of():
    normalized = normalize_applies_when({'key': 'urgency_level', 'op': 'eq', 'value': 'high'})
    assert normalized == {'all_of': [{'key': 'urgency_level', 'op': 'eq', 'value': 'high'}]}


# ───── Booking flow integration ─────


def _service(service_id: str, *, applies_when=None):
    return {
        'id': service_id,
        'name': f'Servicio {service_id}',
        'applies_when': applies_when or {},
    }


def test_filter_services_passthrough_when_facts_empty():
    services = [_service('a'), _service('b')]
    assert _filter_services_by_qualification(services, {}) == services


def test_filter_services_drops_non_matching_rules():
    services = [
        _service('seguimiento', applies_when={
            'all_of': [{'key': 'first_visit', 'op': 'eq', 'value': False}],
        }),
        _service('primera_vez', applies_when={
            'all_of': [{'key': 'first_visit', 'op': 'eq', 'value': True}],
        }),
        _service('generico'),
    ]
    filtered = _filter_services_by_qualification(services, {'first_visit': True})
    ids = [svc['id'] for svc in filtered]
    assert 'primera_vez' in ids
    assert 'seguimiento' not in ids
    assert 'generico' in ids


def test_filter_services_returns_empty_when_no_rule_matches():
    services = [
        _service('s', applies_when={
            'all_of': [{'key': 'urgency_level', 'op': 'eq', 'value': 'emergency'}],
        }),
    ]
    filtered = _filter_services_by_qualification(services, {'urgency_level': 'low'})
    assert filtered == []


def test_qualification_facts_from_conversation_reads_facts_and_presets():
    conversation = {
        'metadata': {
            'qualification': {
                'facts': {'first_visit': True, 'motivo': 'control'},
                'budget_tier': {'tier_label': 'Premium', 'tier_value': 800000},
                'urgency_level': 'high',
            },
        },
    }
    facts = _qualification_facts_from_conversation(conversation)
    assert facts['first_visit'] is True
    assert facts['motivo'] == 'control'
    assert facts['budget_tier'] == 800000
    assert facts['urgency_level'] == 'high'


def test_qualification_facts_from_conversation_handles_missing_metadata():
    assert _qualification_facts_from_conversation({}) == {}
    assert _qualification_facts_from_conversation({'metadata': '{}'}) == {}
    assert _qualification_facts_from_conversation({'metadata': {'other': 1}}) == {}


def test_build_qualification_facts_maps_question_keys_and_coerces_yes_no():
    questions = [
        {'id': 'q1', 'key': 'first_visit', 'kind': 'yes_no', 'options': []},
        {'id': 'q2', 'key': 'sessions', 'kind': 'number', 'options': []},
        {'id': 'q3', 'key': None, 'kind': 'free_text', 'options': []},
    ]
    answered = {'q1': 'sí', 'q2': '3', 'q3': 'ignored'}
    facts = build_qualification_facts(questions, answered)
    assert facts['first_visit'] is True
    assert facts['sessions'] == 3
    assert 'q3' not in facts  # no key → not exposed
    assert 'first_visit_not_present' not in facts


# ───── Booking flow source-level wiring ─────


def test_booking_flow_imports_evaluator_and_filters_services():
    source = BOOKING_FLOW.read_text()
    assert 'from app.services.segments import evaluate_rules' in source
    assert 'def _filter_services_by_qualification(' in source
    assert 'def _qualification_facts_from_conversation(' in source
    # Auto-select when exactly one service remains
    assert 'booking_flow.auto_selected_service' in source
    # Escalate (return None) when 0 match
    assert 'booking_flow.no_services_match_qualification' in source
    # Reads applies_when in the SELECT
    assert 'applies_when' in source


def test_qualification_flow_snapshots_keyed_facts():
    source = QUALIFICATION_FLOW.read_text()
    assert 'build_qualification_facts' in source
    assert "'facts': qualification_facts" in source


# ───── Admin Panel ─────


def test_service_catalog_jsx_has_applies_when_builder():
    source = _services_feature_source()
    assert 'applies_when_rules' in source
    assert 'data-testid="applies-when-builder"' in source
    assert 'data-testid="applies-when-rule"' in source
    assert 'APPLIES_WHEN_OPS' in source
    assert 'rulesToPayload' in source
    assert 'rulesFromService' in source
    assert 'listQualificationQuestions' in source


def test_qualification_panel_jsx_has_key_input():
    source = _tenant_setup_source()
    assert 'Clave (opcional)' in source
    assert "key: question.key || ''" in source
    assert 'KEY_PATTERN' in source
    assert 'key: trimmedKey || null' in source


# ───── Review feedback fixes ─────


def test_qualification_flow_selects_key_column():
    """P1: the qualification flow must pull `key` from the DB so
    ``build_qualification_facts`` can project non-preset answers into the
    facts dict and ``applies_when`` rules can reference them."""
    source = QUALIFICATION_FLOW.read_text()
    assert "select id, position, label, kind, options, required,\n               applies_to_service_ids, preset, key\n        from app.qualification_questions" in source


def test_booking_flow_does_not_truncate_catalog_before_filter():
    """P2: the SQL list must not apply ``limit 10`` because filtering runs
    in Python after the rows arrive. The Meta interactive list cap is
    enforced post-filter."""
    source = BOOKING_FLOW.read_text()
    assert 'SERVICE_LIST_DISPLAY_CAP = 10' in source
    # The catalogue SELECT no longer caps at SQL level.
    assert 'from app.service_catalog\n        where tenant_id=$1 and is_active=true\n        order by sort_order asc, name asc\n        ' in source
    # And we never restore a ``limit 10`` in that SELECT.
    select_block = source.split('select id, name, category, description, price_amount, price_currency,', 1)[1]
    select_block = select_block.split('return [dict(row) for row in rows]', 1)[0]
    assert 'limit 10' not in select_block
    # Post-filter cap is applied.
    assert 'eligible[:SERVICE_LIST_DISPLAY_CAP]' in source


def test_booking_flow_auto_selected_service_offers_packages():
    """P2: the single-match path must call ``_present_packages`` before
    ``_present_branches``/``_present_resources`` so customers with an
    active package don't lose their pre-paid sessions."""
    source = BOOKING_FLOW.read_text()
    auto_block = source.split('booking_flow.auto_selected_service', 1)[1]
    auto_block = auto_block.split('return next_state', 1)[0]
    assert '_present_packages(' in auto_block
    # And _present_packages comes before _present_branches in this branch.
    packages_idx = auto_block.find('_present_packages(')
    branches_idx = auto_block.find('_present_branches(')
    assert packages_idx != -1 and branches_idx != -1 and packages_idx < branches_idx
    # And the maybe_run_booking_flow caller forwards the contact id.
    assert 'contact_id=contact[\'id\'],' in source


def test_evaluate_rules_does_not_truthy_compare_bool_vs_string():
    """P2: an ``eq true`` rule against a free-text answer like 'consultation'
    must NOT match (previous behaviour fell back to truthiness)."""
    rule = {'all_of': [{'key': 'reason', 'op': 'eq', 'value': True}]}
    assert evaluate_rules(rule, {'reason': 'consultation'}) is False
    assert evaluate_rules(rule, {'reason': ''}) is False

    # ``ne true`` must succeed for a non-boolean string answer.
    ne_rule = {'all_of': [{'key': 'reason', 'op': 'ne', 'value': True}]}
    assert evaluate_rules(ne_rule, {'reason': 'consultation'}) is True

    # Real boolean answers still compare cleanly in either direction.
    assert evaluate_rules(rule, {'reason': True}) is True
    assert evaluate_rules(rule, {'reason': 'sí'}) is True  # coerces to True
    assert evaluate_rules(rule, {'reason': False}) is False
