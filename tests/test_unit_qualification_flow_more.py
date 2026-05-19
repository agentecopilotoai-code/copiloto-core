"""Extra tests for app/services/qualification_flow.py pure helpers."""
from __future__ import annotations



def test_parse_json_invalid_returns_fallback():
    from app.services.qualification_flow import _parse_json
    assert _parse_json('not-json', {'a': 1}) == {'a': 1}


def test_parse_json_string_decodes():
    from app.services.qualification_flow import _parse_json
    assert _parse_json('{"x":1}', {}) == {'x': 1}


def test_parse_json_none_returns_fallback():
    from app.services.qualification_flow import _parse_json
    assert _parse_json(None, 'default') == 'default'


def test_parse_json_passthrough_dict():
    from app.services.qualification_flow import _parse_json
    assert _parse_json({'a': 1}, {}) == {'a': 1}


def test_qualification_state_non_dict_metadata():
    from app.services.qualification_flow import _qualification_state
    # metadata is a list
    conv = {'metadata': '[1,2,3]'}
    out = _qualification_state(conv)
    assert out == {}


def test_qualification_state_state_not_dict():
    from app.services.qualification_flow import _qualification_state
    conv = {'metadata': '{"qualification": "not-a-dict"}'}
    out = _qualification_state(conv)
    assert out == {}


def test_qualification_state_returns_state_dict():
    from app.services.qualification_flow import _qualification_state
    conv = {'metadata': {'qualification': {'answered': {'q1': True}}}}
    out = _qualification_state(conv)
    assert out['answered'] == {'q1': True}


def test_interactive_id_payload_not_dict():
    from app.services.qualification_flow import _interactive_id
    out = _interactive_id({'payload': '[1,2,3]'})
    assert out == (None, None)


def test_interactive_id_no_colon():
    from app.services.qualification_flow import _interactive_id
    out = _interactive_id({'payload': {'interactive_id': 'no-colon'}})
    assert out == (None, None)


def test_interactive_id_valid():
    from app.services.qualification_flow import _interactive_id
    out = _interactive_id({'payload': {'interactive_id': 'qualify:q1:value'}})
    assert out == ('qualify', 'q1:value')


def test_option_for_value_match():
    from app.services.qualification_flow import _option_for_value
    q = {'options': [{'value': '1', 'label': 'A'}, {'value': '2', 'label': 'B'}]}
    out = _option_for_value(q, '2')
    assert out == {'value': '2', 'label': 'B'}


def test_option_for_value_no_match():
    from app.services.qualification_flow import _option_for_value
    q = {'options': [{'value': '1'}]}
    assert _option_for_value(q, '99') is None


def test_option_for_value_none_value():
    from app.services.qualification_flow import _option_for_value
    q = {'options': [{'value': '1'}]}
    assert _option_for_value(q, None) is None


def test_question_with_preset_match():
    from app.services.qualification_flow import _question_with_preset
    qs = [{'preset': 'budget_tier'}, {'preset': 'other'}]
    assert _question_with_preset(qs, 'budget_tier') == qs[0]


def test_question_with_preset_no_match():
    from app.services.qualification_flow import _question_with_preset
    assert _question_with_preset([], 'budget_tier') is None


def test_budget_tier_summary_no_question():
    from app.services.qualification_flow import _budget_tier_summary
    assert _budget_tier_summary([], {}) is None


def test_budget_tier_summary_no_answer():
    from app.services.qualification_flow import _budget_tier_summary
    qs = [{'preset': 'budget_tier', 'id': 'q1', 'options': []}]
    assert _budget_tier_summary(qs, {}) is None


def test_budget_tier_summary_no_option_match():
    from app.services.qualification_flow import _budget_tier_summary
    qs = [{'preset': 'budget_tier', 'id': 'q1',
           'options': [{'value': '1', 'tier_value': 100}]}]
    # answered uses 'q1' but the answer doesn't match any option
    assert _budget_tier_summary(qs, {'q1': '99'}) is None


def test_budget_tier_summary_invalid_tier_value():
    from app.services.qualification_flow import _budget_tier_summary
    qs = [{'preset': 'budget_tier', 'id': 'q1',
           'options': [{'value': '1', 'tier_value': 'not-a-number', 'label': 'Low'}]}]
    out = _budget_tier_summary(qs, {'q1': '1'})
    assert out['tier_value'] is None


def test_budget_tier_summary_returns_summary():
    from app.services.qualification_flow import _budget_tier_summary
    qs = [{'preset': 'budget_tier', 'id': 'q1',
           'options': [{'value': '1', 'tier_value': 500, 'label': 'Bajo'}]}]
    out = _budget_tier_summary(qs, {'q1': '1'})
    assert out['tier_value'] == 500.0
    assert out['tier_label'] == 'Bajo'


def test_urgency_summary_no_question():
    from app.services.qualification_flow import _urgency_summary
    assert _urgency_summary([], {}) is None


def test_urgency_summary_no_answer():
    from app.services.qualification_flow import _urgency_summary
    qs = [{'preset': 'urgency_level', 'id': 'q1', 'options': []}]
    assert _urgency_summary(qs, {}) is None


def test_urgency_summary_yes_no_emergency():
    from app.services.qualification_flow import _urgency_summary
    qs = [{'preset': 'urgency_level', 'id': 'q1', 'kind': 'yes_no'}]
    out = _urgency_summary(qs, {'q1': True})
    assert out['level'] == 'emergency'


def test_urgency_summary_yes_no_normal():
    from app.services.qualification_flow import _urgency_summary
    qs = [{'preset': 'urgency_level', 'id': 'q1', 'kind': 'yes_no'}]
    out = _urgency_summary(qs, {'q1': False})
    assert out['level'] == 'normal'


def test_urgency_summary_no_option_match():
    from app.services.qualification_flow import _urgency_summary
    qs = [{'preset': 'urgency_level', 'id': 'q1', 'kind': 'single_choice', 'options': []}]
    assert _urgency_summary(qs, {'q1': '99'}) is None


def test_urgency_summary_unknown_normalized_falls_back():
    from app.services.qualification_flow import _urgency_summary
    qs = [{
        'preset': 'urgency_level', 'id': 'q1', 'kind': 'single_choice',
        'options': [{'value': '1', 'urgency_normalized': 'invalid_value'}],
    }]
    out = _urgency_summary(qs, {'q1': '1'})
    assert out['level'] == 'normal'


def test_urgency_summary_valid_normalized():
    from app.services.qualification_flow import _urgency_summary
    qs = [{
        'preset': 'urgency_level', 'id': 'q1', 'kind': 'single_choice',
        'options': [{'value': '1', 'urgency_normalized': 'high'}],
    }]
    out = _urgency_summary(qs, {'q1': '1'})
    assert out['level'] == 'high'


def test_vip_budget_threshold_invalid_string_returns_default():
    from app.services.qualification_flow import _vip_budget_threshold, DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold('not-json') == DEFAULT_VIP_BUDGET_THRESHOLD


def test_vip_budget_threshold_non_dict():
    from app.services.qualification_flow import _vip_budget_threshold, DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold([1, 2]) == DEFAULT_VIP_BUDGET_THRESHOLD


def test_vip_budget_threshold_no_key():
    from app.services.qualification_flow import _vip_budget_threshold, DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold({}) == DEFAULT_VIP_BUDGET_THRESHOLD


def test_vip_budget_threshold_invalid_value():
    from app.services.qualification_flow import _vip_budget_threshold, DEFAULT_VIP_BUDGET_THRESHOLD
    assert _vip_budget_threshold({'vip_budget_threshold': 'xx'}) == DEFAULT_VIP_BUDGET_THRESHOLD


def test_vip_budget_threshold_from_string():
    from app.services.qualification_flow import _vip_budget_threshold
    assert _vip_budget_threshold('{"vip_budget_threshold": 1000}') == 1000.0


def test_vip_budget_threshold_returns_float():
    from app.services.qualification_flow import _vip_budget_threshold
    assert _vip_budget_threshold({'vip_budget_threshold': 500}) == 500.0


def test_is_vip_no_summary():
    from app.services.qualification_flow import _is_vip
    assert _is_vip(None, 100) is False


def test_is_vip_zero_threshold():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 1000}, 0) is False


def test_is_vip_no_tier_value():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': None}, 100) is False


def test_is_vip_invalid_tier_value():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 'not-a-number'}, 100) is False


def test_is_vip_below_threshold():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 50}, 100) is False


def test_is_vip_above_threshold():
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 200}, 100) is True


def test_options_for_render_skips_non_dict():
    from app.services.qualification_flow import _options_for_render
    out = _options_for_render({'options': ['just-a-string', None, {'value': 'v', 'label': 'L'}]})
    assert len(out) == 1
    assert out[0]['value'] == 'v'


def test_options_for_render_skips_empty_value():
    from app.services.qualification_flow import _options_for_render
    out = _options_for_render({'options': [{'value': '', 'label': 'X'}]})
    assert out == []


def test_options_for_render_uses_id_fallback():
    from app.services.qualification_flow import _options_for_render
    out = _options_for_render({'options': [{'id': 'idkey'}]})
    assert out[0]['value'] == 'idkey'
    assert out[0]['label'] == 'idkey'


def test_options_for_render_truncates_label():
    from app.services.qualification_flow import _options_for_render
    out = _options_for_render({'options': [{'value': 'v', 'label': 'x' * 50}]})
    assert len(out[0]['label']) == 24


def test_next_pending_question_skips_answered():
    from app.services.qualification_flow import _next_pending_question
    qs = [{'id': '1', 'required': True}, {'id': '2', 'required': True}]
    out = _next_pending_question(qs, {'1': 'a'})
    assert out['id'] == '2'


def test_next_pending_question_skips_optional_declined():
    from app.services.qualification_flow import _next_pending_question
    qs = [{'id': '1', 'required': False}]
    out = _next_pending_question(qs, {'1': False})
    assert out is None


def test_next_pending_question_returns_first_pending():
    from app.services.qualification_flow import _next_pending_question
    qs = [{'id': '1', 'required': True}]
    out = _next_pending_question(qs, {})
    assert out['id'] == '1'


def test_next_pending_question_all_answered():
    from app.services.qualification_flow import _next_pending_question
    qs = [{'id': '1', 'required': True}]
    out = _next_pending_question(qs, {'1': 'a'})
    assert out is None


def test_validate_text_reply_empty():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'free_text'}, '') is None
    assert _validate_text_reply({'kind': 'free_text'}, '   ') is None


def test_validate_text_reply_number_invalid():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'number'}, 'abc') is None


def test_validate_text_reply_number_valid():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'number'}, '3.5') == 3.5


def test_validate_text_reply_number_with_comma():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'number'}, '3,5') == 3.5


def test_validate_text_reply_free_text():
    from app.services.qualification_flow import _validate_text_reply
    assert _validate_text_reply({'kind': 'free_text'}, '  hello  ') == 'hello'


def test_match_choice_no_options():
    from app.services.qualification_flow import _match_choice
    assert _match_choice({'options': []}, 'x') is None


def test_match_choice_exact_value():
    from app.services.qualification_flow import _match_choice
    q = {'options': [{'value': 'A', 'label': 'Alpha'}]}
    assert _match_choice(q, 'A') == 'A'


def test_match_choice_label_case_insensitive():
    from app.services.qualification_flow import _match_choice
    q = {'options': [{'value': 'A', 'label': 'Alpha'}]}
    assert _match_choice(q, 'alpha') == 'A'


def test_match_choice_no_match():
    from app.services.qualification_flow import _match_choice
    q = {'options': [{'value': 'A', 'label': 'Alpha'}]}
    assert _match_choice(q, 'Bravo') is None


def test_coerce_answer_value_none():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'yes_no'}, None) is None


def test_coerce_answer_value_yesno_bool():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'yes_no'}, True) is True


def test_coerce_answer_value_yesno_string_true():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'yes_no'}, 'sí') is True
    assert _coerce_answer_value({'kind': 'yes_no'}, 'yes') is True
    assert _coerce_answer_value({'kind': 'yes_no'}, '1') is True


def test_coerce_answer_value_yesno_string_false():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'yes_no'}, 'no') is False
    assert _coerce_answer_value({'kind': 'yes_no'}, '0') is False


def test_coerce_answer_value_yesno_unknown_string():
    from app.services.qualification_flow import _coerce_answer_value
    out = _coerce_answer_value({'kind': 'yes_no'}, 'maybe')
    # Falls through to return raw
    assert out == 'maybe'


def test_coerce_answer_value_number_int():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'number'}, 7) == 7


def test_coerce_answer_value_number_float():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'number'}, 3.5) == 3.5


def test_coerce_answer_value_number_string_int():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'number'}, '12') == 12


def test_coerce_answer_value_number_string_float():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'number'}, '3,5') == 3.5


def test_coerce_answer_value_number_invalid_string():
    from app.services.qualification_flow import _coerce_answer_value
    out = _coerce_answer_value({'kind': 'number'}, 'abc')
    assert out == 'abc'


def test_coerce_answer_value_other_kind_returns_raw():
    from app.services.qualification_flow import _coerce_answer_value
    assert _coerce_answer_value({'kind': 'free_text'}, 'hello') == 'hello'


def test_build_qualification_facts_empty():
    from app.services.qualification_flow import build_qualification_facts
    assert build_qualification_facts([], {}) == {}


def test_build_qualification_facts_with_keys():
    from app.services.qualification_flow import build_qualification_facts
    qs = [
        {'id': '1', 'kind': 'free_text', 'key': 'name'},
        {'id': '2', 'kind': 'yes_no', 'key': ''},  # empty key skipped
    ]
    facts = build_qualification_facts(qs, {'1': 'Pepito', '2': True})
    assert facts == {'name': 'Pepito'}


def test_build_qualification_facts_includes_presets():
    from app.services.qualification_flow import build_qualification_facts
    qs = [
        {'id': '1', 'preset': 'budget_tier', 'kind': 'single_choice',
         'options': [{'value': 'high', 'tier_value': 1000, 'label': 'High'}]},
        {'id': '2', 'preset': 'urgency_level', 'kind': 'yes_no'},
    ]
    facts = build_qualification_facts(qs, {'1': 'high', '2': True})
    assert facts['budget_tier'] == 1000.0
    assert facts['budget_label'] == 'High'
    assert facts['urgency_level'] == 'emergency'


def test_derive_recommended_service_no_choice_questions():
    from app.services.qualification_flow import _derive_recommended_service
    out = _derive_recommended_service([{'kind': 'free_text', 'id': '1'}], {'1': 'x'})
    assert out is None


def test_derive_recommended_service_no_string_answer():
    from app.services.qualification_flow import _derive_recommended_service
    qs = [{'kind': 'single_choice', 'id': '1', 'options': [{'value': 'a', 'service_id': 's1'}]}]
    out = _derive_recommended_service(qs, {'1': True})
    assert out is None


def test_derive_recommended_service_match():
    from app.services.qualification_flow import _derive_recommended_service
    qs = [{'kind': 'single_choice', 'id': '1', 'options': [{'value': 'a', 'service_id': 's1'}]}]
    out = _derive_recommended_service(qs, {'1': 'a'})
    assert out == 's1'


def test_derive_recommended_service_no_service_id_field():
    from app.services.qualification_flow import _derive_recommended_service
    qs = [{'kind': 'single_choice', 'id': '1', 'options': [{'value': 'a'}]}]
    out = _derive_recommended_service(qs, {'1': 'a'})
    assert out is None


def test_derive_recommended_service_options_not_dict():
    from app.services.qualification_flow import _derive_recommended_service
    qs = [{'kind': 'single_choice', 'id': '1', 'options': ['not-dict']}]
    out = _derive_recommended_service(qs, {'1': 'a'})
    assert out is None
