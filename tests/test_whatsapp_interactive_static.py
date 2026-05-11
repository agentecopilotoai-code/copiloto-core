from pathlib import Path

import pytest

from app.services.whatsapp import (
    MAX_INTERACTIVE_BUTTONS,
    MAX_INTERACTIVE_LIST_ROWS,
    build_interactive_button_payload,
    build_interactive_list_payload,
    build_whatsapp_message_payload,
    parse_interactive_reply,
)

WHATSAPP = Path('app/services/whatsapp.py')
EVENT_WORKER = Path('app/workers/event_worker.py')
API_ROUTES = Path('app/api/v1/routes.py')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')


def test_build_interactive_button_payload_meets_meta_contract():
    payload = build_interactive_button_payload(
        body_text='¿Quieres confirmar tu cita?',
        buttons=[
            {'id': 'confirm_yes', 'title': 'Sí'},
            {'id': 'confirm_no', 'title': 'No'},
        ],
        header_text='Confirmación',
        footer_text='Equipo de soporte',
    )

    assert payload['type'] == 'button'
    assert payload['body'] == {'text': '¿Quieres confirmar tu cita?'}
    assert payload['header'] == {'type': 'text', 'text': 'Confirmación'}
    assert payload['footer'] == {'text': 'Equipo de soporte'}
    assert payload['action'] == {
        'buttons': [
            {'type': 'reply', 'reply': {'id': 'confirm_yes', 'title': 'Sí'}},
            {'type': 'reply', 'reply': {'id': 'confirm_no', 'title': 'No'}},
        ],
    }


def test_build_interactive_button_payload_rejects_more_than_three_buttons():
    too_many = [{'id': f'b_{i}', 'title': f'b{i}'} for i in range(4)]
    with pytest.raises(ValueError):
        build_interactive_button_payload(body_text='Pick one', buttons=too_many)
    assert MAX_INTERACTIVE_BUTTONS == 3


def test_build_interactive_button_payload_validates_required_fields():
    with pytest.raises(ValueError):
        build_interactive_button_payload(body_text='', buttons=[{'id': 'x', 'title': 'X'}])
    with pytest.raises(ValueError):
        build_interactive_button_payload(body_text='Hola', buttons=[])
    with pytest.raises(ValueError):
        build_interactive_button_payload(body_text='Hola', buttons=[{'id': '', 'title': 'X'}])
    with pytest.raises(ValueError):
        build_interactive_button_payload(
            body_text='Hola',
            buttons=[{'id': 'x', 'title': 'A title that is way too long for whatsapp'}],
        )


def test_build_interactive_list_payload_supports_up_to_ten_rows():
    rows = [{'id': f'svc_{i}', 'title': f'Servicio {i}'} for i in range(10)]
    payload = build_interactive_list_payload(
        body_text='Elige un servicio',
        button_label='Ver servicios',
        sections=[{'title': 'Catálogo', 'rows': rows}],
    )

    assert payload['type'] == 'list'
    assert payload['action']['button'] == 'Ver servicios'
    assert payload['action']['sections'][0]['title'] == 'Catálogo'
    assert len(payload['action']['sections'][0]['rows']) == MAX_INTERACTIVE_LIST_ROWS == 10


def test_build_interactive_list_payload_validates_required_fields():
    with pytest.raises(ValueError):
        build_interactive_list_payload(body_text='', button_label='Ver', sections=[{'rows': [{'id': 'x', 'title': 'X'}]}])
    with pytest.raises(ValueError):
        build_interactive_list_payload(body_text='Elige', button_label='', sections=[{'rows': [{'id': 'x', 'title': 'X'}]}])
    with pytest.raises(ValueError):
        build_interactive_list_payload(body_text='Elige', button_label='Ver', sections=[])
    with pytest.raises(ValueError):
        build_interactive_list_payload(body_text='Elige', button_label='Ver', sections=[{'rows': []}])


def test_build_whatsapp_message_payload_wraps_interactive_block():
    interactive_block = build_interactive_button_payload(
        body_text='Pick',
        buttons=[{'id': 'yes', 'title': 'Sí'}],
    )
    payload = build_whatsapp_message_payload(
        to='+573001112222',
        message_type='interactive',
        interactive_payload=interactive_block,
    )
    assert payload == {
        'messaging_product': 'whatsapp',
        'to': '+573001112222',
        'type': 'interactive',
        'interactive': interactive_block,
    }


def test_build_whatsapp_message_payload_requires_interactive_dict():
    with pytest.raises(ValueError):
        build_whatsapp_message_payload(to='+573001112222', message_type='interactive')


def test_parse_interactive_reply_button():
    parsed = parse_interactive_reply({
        'type': 'interactive',
        'interactive': {
            'type': 'button_reply',
            'button_reply': {'id': 'confirm_yes', 'title': 'Sí'},
        },
    })
    assert parsed == {
        'interactive_type': 'button_reply',
        'interactive_id': 'confirm_yes',
        'interactive_title': 'Sí',
    }


def test_parse_interactive_reply_list_with_description():
    parsed = parse_interactive_reply({
        'type': 'interactive',
        'interactive': {
            'type': 'list_reply',
            'list_reply': {
                'id': 'svc_corte',
                'title': 'Corte',
                'description': 'Corte de cabello clásico',
            },
        },
    })
    assert parsed['interactive_type'] == 'list_reply'
    assert parsed['interactive_id'] == 'svc_corte'
    assert parsed['interactive_title'] == 'Corte'
    assert parsed['interactive_description'] == 'Corte de cabello clásico'


def test_parse_interactive_reply_returns_none_for_non_interactive():
    assert parse_interactive_reply({'type': 'text'}) is None
    assert parse_interactive_reply({'type': 'interactive'}) is None
    assert parse_interactive_reply({'type': 'interactive', 'interactive': {'type': 'foo'}}) is None


def test_whatsapp_module_exports_interactive_helpers():
    source = WHATSAPP.read_text()
    assert "'interactive'" in source
    assert 'SUPPORTED_OUTBOUND_MESSAGE_TYPES' in source
    assert 'async def send_interactive_buttons(' in source
    assert 'async def send_interactive_list(' in source
    assert 'def parse_interactive_reply(' in source
    assert 'MAX_INTERACTIVE_BUTTONS = 3' in source
    assert 'MAX_INTERACTIVE_LIST_ROWS = 10' in source


def test_event_worker_forwards_interactive_payload():
    source = EVENT_WORKER.read_text()
    assert "message_payload.get('interactive')" in source


def test_webhook_parses_interactive_reply_into_body_text():
    source = API_ROUTES.read_text()
    assert 'parse_interactive_reply' in source
    assert 'interactive_reply = parse_interactive_reply(message)' in source
    assert "if interactive_reply:" in source
    assert "body_text = interactive_reply['interactive_title']" in source


def test_operations_desk_renders_interactive_messages():
    source = OPERATIONS_DESK.read_text()
    assert 'interactivePayload' in source
    assert 'interactiveSelection' in source
    assert 'renderInteractiveOutbound' in source
    assert 'renderInteractiveInbound' in source
    assert 'interactive-chip' in source
    assert "interactive: 'Interactivo'" in source
