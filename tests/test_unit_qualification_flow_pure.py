"""Pure-helper tests for `app/services/qualification_flow.py`."""
from __future__ import annotations



# ───────── _parse_json ────────────────────────────────────────────────────


def test_parse_json_dict_passthrough():
    from app.services.qualification_flow import _parse_json
    d = {'k': 'v'}
    assert _parse_json(d, {}) is d


def test_parse_json_json_string():
    from app.services.qualification_flow import _parse_json
    assert _parse_json('{"k": 1}', {}) == {'k': 1}


def test_parse_json_invalid_falls_back():
    from app.services.qualification_flow import _parse_json
    assert _parse_json('not json', ['fb']) == ['fb']


def test_parse_json_none_falls_back():
    from app.services.qualification_flow import _parse_json
    assert _parse_json(None, []) == []


# ───────── _qualification_state ──────────────────────────────────────────


def test_qualification_state_empty():
    from app.services.qualification_flow import _qualification_state
    assert _qualification_state({'metadata': {}}) == {}


def test_qualification_state_returns_persisted():
    from app.services.qualification_flow import _qualification_state
    conv = {'metadata': {'qualification': {'step': 'q1'}}}
    assert _qualification_state(conv) == {'step': 'q1'}


def test_qualification_state_json_string_metadata():
    from app.services.qualification_flow import _qualification_state
    conv = {'metadata': '{"qualification": {"answered": {}}}'}
    assert _qualification_state(conv) == {'answered': {}}


def test_qualification_state_non_dict_returns_empty():
    from app.services.qualification_flow import _qualification_state
    assert _qualification_state({'metadata': {'qualification': 'not a dict'}}) == {}


# ───────── _interactive_id ────────────────────────────────────────────────


def test_interactive_id_extracts_prefix_value():
    from app.services.qualification_flow import _interactive_id
    msg = {'payload': {'interactive_id': 'q:answer-1'}}
    assert _interactive_id(msg) == ('q', 'answer-1')


def test_interactive_id_none_for_missing():
    from app.services.qualification_flow import _interactive_id
    assert _interactive_id({'payload': {}}) == (None, None)
    assert _interactive_id({'payload': {'interactive_id': 'no-colon'}}) == (None, None)


# ───────── _option_for_value ─────────────────────────────────────────────


def test_option_for_value_match():
    from app.services.qualification_flow import _option_for_value
    q = {'options': [
        {'value': 'low', 'label': 'Bajo'},
        {'value': 'high', 'label': 'Alto'},
    ]}
    assert _option_for_value(q, 'high') == {'value': 'high', 'label': 'Alto'}


def test_option_for_value_no_match():
    from app.services.qualification_flow import _option_for_value
    q = {'options': [{'value': 'low', 'label': 'Bajo'}]}
    assert _option_for_value(q, 'medium') is None


def test_option_for_value_none_value():
    from app.services.qualification_flow import _option_for_value
    q = {'options': [{'value': 'low'}]}
    assert _option_for_value(q, None) is None


# ───────── _question_with_preset ─────────────────────────────────────────


def test_question_with_preset_finds():
    from app.services.qualification_flow import _question_with_preset
    questions = [
        {'preset': 'budget_tier', 'id': 'q1'},
        {'preset': None, 'id': 'q2'},
    ]
    assert _question_with_preset(questions, 'budget_tier') == questions[0]


def test_question_with_preset_returns_none_for_missing():
    from app.services.qualification_flow import _question_with_preset
    assert _question_with_preset([{'preset': 'urgency_level'}], 'budget_tier') is None


# ───────── _budget_tier_summary ──────────────────────────────────────────


def test_budget_tier_summary_with_match():
    from app.services.qualification_flow import _budget_tier_summary
    questions = [{
        'id': 'q1', 'preset': 'budget_tier',
        'options': [{'value': 'mid', 'label': 'Mid', 'tier_value': 100.0}],
    }]
    answered = {'q1': 'mid'}
    out = _budget_tier_summary(questions, answered)
    assert out == {'tier_label': 'Mid', 'tier_value': 100.0, 'option_value': 'mid'}


def test_budget_tier_summary_no_preset_question():
    from app.services.qualification_flow import _budget_tier_summary
    assert _budget_tier_summary([], {}) is None


def test_budget_tier_summary_no_answer():
    from app.services.qualification_flow import _budget_tier_summary
    questions = [{'id': 'q1', 'preset': 'budget_tier', 'options': []}]
    assert _budget_tier_summary(questions, {}) is None


def test_budget_tier_summary_invalid_tier_value_becomes_none():
    from app.services.qualification_flow import _budget_tier_summary
    questions = [{
        'id': 'q1', 'preset': 'budget_tier',
        'options': [{'value': 'mid', 'label': 'Mid', 'tier_value': 'abc'}],
    }]
    answered = {'q1': 'mid'}
    out = _budget_tier_summary(questions, answered)
    assert out['tier_value'] is None


# ───────── _urgency_summary ───────────────────────────────────────────────


def test_urgency_summary_with_match():
    from app.services.qualification_flow import _urgency_summary
    questions = [{
        'id': 'q1', 'preset': 'urgency_level', 'kind': 'single_choice',
        'options': [{'value': 'asap', 'urgency_normalized': 'high'}],
    }]
    out = _urgency_summary(questions, {'q1': 'asap'})
    assert out == {'level': 'high', 'option_value': 'asap'}


def test_urgency_summary_normalizes_unknown_to_normal():
    from app.services.qualification_flow import _urgency_summary
    questions = [{
        'id': 'q1', 'preset': 'urgency_level', 'kind': 'single_choice',
        'options': [{'value': 'maybe', 'urgency_normalized': 'unknown_value'}],
    }]
    out = _urgency_summary(questions, {'q1': 'maybe'})
    assert out['level'] == 'normal'


def test_urgency_summary_yes_no_kind_maps_to_emergency():
    from app.services.qualification_flow import _urgency_summary
    questions = [{'id': 'q1', 'preset': 'urgency_level', 'kind': 'yes_no'}]
    assert _urgency_summary(questions, {'q1': True}) == {
        'level': 'emergency', 'option_value': True,
    }
    assert _urgency_summary(questions, {'q1': False}) == {
        'level': 'normal', 'option_value': False,
    }


def test_urgency_summary_returns_none_for_missing():
    from app.services.qualification_flow import _urgency_summary
    assert _urgency_summary([], {}) is None


# ───────── _vip_budget_threshold ─────────────────────────────────────────


def test_vip_budget_threshold_default():
    from app.services.qualification_flow import (
        DEFAULT_VIP_BUDGET_THRESHOLD,
        _vip_budget_threshold,
    )
    assert _vip_budget_threshold(None) == DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold('not json') == DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold('{}') == DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold({'vip_budget_threshold': None}) == DEFAULT_VIP_BUDGET_THRESHOLD


def test_vip_budget_threshold_reads_from_dict():
    from app.services.qualification_flow import _vip_budget_threshold
    assert _vip_budget_threshold({'vip_budget_threshold': 500000}) == 500000.0


def test_vip_budget_threshold_reads_from_json_string():
    from app.services.qualification_flow import _vip_budget_threshold
    assert _vip_budget_threshold('{"vip_budget_threshold": 100}') == 100.0


def test_vip_budget_threshold_invalid_value_falls_back():
    from app.services.qualification_flow import (
        DEFAULT_VIP_BUDGET_THRESHOLD,
        _vip_budget_threshold,
    )
    assert _vip_budget_threshold(
        {'vip_budget_threshold': 'not a number'},
    ) == DEFAULT_VIP_BUDGET_THRESHOLD


# ───────── _is_vip ────────────────────────────────────────────────────────


def test_is_vip_true_when_above_threshold():
    from app.services.qualification_flow import _is_vip
    budget = {'tier_value': 1500.0}
    assert _is_vip(budget, 1000.0) is True


def test_is_vip_false_when_below_threshold():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 100.0}, 1000.0) is False


def test_is_vip_false_when_no_budget():
    from app.services.qualification_flow import _is_vip
    assert _is_vip(None, 100.0) is False


def test_is_vip_false_when_zero_threshold():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 5000.0}, 0.0) is False


def test_is_vip_false_when_tier_value_none():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': None}, 100.0) is False


def test_is_vip_false_when_tier_value_garbage():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 'abc'}, 100.0) is False


# ───────── _options_for_render ───────────────────────────────────────────


def test_options_for_render_basic():
    from app.services.qualification_flow import _options_for_render
    q = {'options': [
        {'value': 'a', 'label': 'A'},
        {'value': 'b', 'label': 'B-long-name-that-may-truncate' * 2},
    ]}
    out = _options_for_render(q)
    assert out[0]['value'] == 'a'
    assert len(out[1]['label']) <= 24


def test_options_for_render_skips_invalid():
    from app.services.qualification_flow import _options_for_render
    q = {'options': [
        'not-a-dict',
        {'value': '', 'label': 'empty-value'},  # value blank → skipped
        {'value': 'ok'},  # no label → label defaults to value
    ]}
    out = _options_for_render(q)
    assert len(out) == 1
    assert out[0]['value'] == 'ok'
    assert out[0]['label'] == 'ok'


def test_options_for_render_no_options():
    from app.services.qualification_flow import _options_for_render
    assert _options_for_render({}) == []
    assert _options_for_render({'options': []}) == []


# ───────── _next_pending_question ────────────────────────────────────────


def test_next_pending_question_returns_first_unanswered():
    from app.services.qualification_flow import _next_pending_question
    questions = [{'id': 'q1'}, {'id': 'q2'}, {'id': 'q3'}]
    assert _next_pending_question(questions, {'q1': 'a'}) == {'id': 'q2'}


def test_next_pending_question_returns_none_when_all_answered():
    from app.services.qualification_flow import _next_pending_question
    questions = [{'id': 'q1'}]
    assert _next_pending_question(questions, {'q1': 'a'}) is None


def test_next_pending_question_skips_optional_with_false_marker():
    """Optional questions that the user explicitly skipped (`answered[qid]=False`)
    are not re-presented."""
    from app.services.qualification_flow import _next_pending_question
    questions = [{'id': 'q1', 'required': False}, {'id': 'q2'}]
    out = _next_pending_question(questions, {'q1': False})
    assert out == {'id': 'q2'}


# ───────── _validate_text_reply ──────────────────────────────────────────


def test_validate_text_reply_empty():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'free_text'}, '   ') is None


def test_validate_text_reply_free_text():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'free_text'}, '  hola  ') == 'hola'


def test_validate_text_reply_number_valid():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'number'}, '42') == 42.0
    assert _validate_text_reply({'kind': 'number'}, '3,14') == 3.14
    assert _validate_text_reply({'kind': 'number'}, '-10.5') == -10.5


def test_validate_text_reply_number_invalid():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'number'}, 'abc') is None


# ───────── _match_choice ─────────────────────────────────────────────────


def test_match_choice_exact_value():
    from app.services.qualification_flow import _match_choice
    q = {'options': [{'value': 'mid', 'label': 'Medio'}]}
    assert _match_choice(q, 'mid') == 'mid'


def test_match_choice_label_match_case_insensitive():
    from app.services.qualification_flow import _match_choice
    q = {'options': [{'value': 'mid', 'label': 'Medio'}]}
    assert _match_choice(q, 'MEDIO') == 'mid'
    assert _match_choice(q, 'medio') == 'mid'


def test_match_choice_no_match():
    from app.services.qualification_flow import _match_choice
    q = {'options': [{'value': 'mid', 'label': 'Medio'}]}
    assert _match_choice(q, 'unknown') is None


def test_match_choice_no_options():
    from app.services.qualification_flow import _match_choice
    assert _match_choice({'options': []}, 'x') is None


# ───────── _coerce_answer_value ──────────────────────────────────────────


def test_coerce_answer_value_yes_no_bool():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'yes_no'}
    assert _coerce_answer_value(q, True) is True
    assert _coerce_answer_value(q, False) is False


def test_coerce_answer_value_yes_no_string_variants():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'yes_no'}
    assert _coerce_answer_value(q, 'true') is True
    assert _coerce_answer_value(q, 'sí') is True
    assert _coerce_answer_value(q, 'Si') is True
    assert _coerce_answer_value(q, '1') is True
    assert _coerce_answer_value(q, 'false') is False
    assert _coerce_answer_value(q, 'no') is False
    assert _coerce_answer_value(q, '0') is False


def test_coerce_answer_value_number_int():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'number'}
    assert _coerce_answer_value(q, '42') == 42
    assert _coerce_answer_value(q, '3.14') == 3.14
    assert _coerce_answer_value(q, '3,14') == 3.14
    assert _coerce_answer_value(q, 100) == 100
    assert _coerce_answer_value(q, 3.5) == 3.5


def test_coerce_answer_value_none_returns_none():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'yes_no'}
    assert _coerce_answer_value(q, None) is None


def test_coerce_answer_value_number_invalid_string():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'number'}
    # Falls back to raw value when the string isn't numeric
    assert _coerce_answer_value(q, 'abc') == 'abc'


def test_coerce_answer_value_free_text_passthrough():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'free_text'}
    assert _coerce_answer_value(q, 'hola') == 'hola'


# ───────── build_qualification_facts ─────────────────────────────────────


def test_build_qualification_facts_basic():
    from app.services.qualification_flow import build_qualification_facts
    questions = [
        {'id': 'q1', 'key': 'first_visit', 'kind': 'yes_no'},
        {'id': 'q2', 'key': 'age', 'kind': 'number'},
    ]
    answered = {'q1': 'sí', 'q2': '35'}
    facts = build_qualification_facts(questions, answered)
    assert facts['first_visit'] is True
    assert facts['age'] == 35


def test_build_qualification_facts_skips_no_key():
    from app.services.qualification_flow import build_qualification_facts
    questions = [{'id': 'q1', 'key': None, 'kind': 'free_text'}]
    facts = build_qualification_facts(questions, {'q1': 'hola'})
    assert facts == {}


def test_build_qualification_facts_skips_unanswered():
    from app.services.qualification_flow import build_qualification_facts
    questions = [{'id': 'q1', 'key': 'k', 'kind': 'free_text'}]
    facts = build_qualification_facts(questions, {})
    assert facts == {}


def test_build_qualification_facts_includes_budget_and_urgency():
    from app.services.qualification_flow import build_qualification_facts
    questions = [
        {
            'id': 'b', 'preset': 'budget_tier',
            'options': [{'value': 'high', 'label': 'Alto', 'tier_value': 500.0}],
        },
        {
            'id': 'u', 'preset': 'urgency_level', 'kind': 'single_choice',
            'options': [{'value': 'now', 'urgency_normalized': 'emergency'}],
        },
    ]
    answered = {'b': 'high', 'u': 'now'}
    facts = build_qualification_facts(questions, answered)
    assert facts['budget_tier'] == 500.0
    assert facts['budget_label'] == 'Alto'
    assert facts['urgency_level'] == 'emergency'


# ───────── _derive_recommended_service ───────────────────────────────────


def test_derive_recommended_service_returns_service_id():
    from app.services.qualification_flow import _derive_recommended_service
    questions = [{
        'id': 'q1', 'kind': 'single_choice',
        'options': [
            {'value': 'a', 'service_id': 'svc-1'},
            {'value': 'b', 'service_id': 'svc-2'},
        ],
    }]
    out = _derive_recommended_service(questions, {'q1': 'b'})
    assert out == 'svc-2'


def test_derive_recommended_service_no_match():
    from app.services.qualification_flow import _derive_recommended_service
    questions = [{'id': 'q1', 'kind': 'single_choice', 'options': []}]
    assert _derive_recommended_service(questions, {'q1': 'x'}) is None


def test_derive_recommended_service_skips_non_choice():
    from app.services.qualification_flow import _derive_recommended_service
    questions = [{
        'id': 'q1', 'kind': 'free_text',
        'options': [{'value': 'a', 'service_id': 'svc'}],
    }]
    assert _derive_recommended_service(questions, {'q1': 'a'}) is None


def test_derive_recommended_service_non_string_answer():
    from app.services.qualification_flow import _derive_recommended_service
    questions = [{
        'id': 'q1', 'kind': 'single_choice',
        'options': [{'value': 'a', 'service_id': 'svc'}],
    }]
    # answer is not a string → returns None
    assert _derive_recommended_service(questions, {'q1': True}) is None
