import logging
import re
import structlog

_PHONE_RE = re.compile(r'\+\d{7,15}')
_EMAIL_RE = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
_PII_KEYS = frozenset({'phone_e164', 'phone', 'email', 'display_name', 'wa_id', 'actor_id'})


def _redact_pii(logger: object, method: str, event_dict: dict) -> dict:
    event = event_dict.get('event', '')
    if isinstance(event, str):
        event = _PHONE_RE.sub('[PHONE]', event)
        event = _EMAIL_RE.sub('[EMAIL]', event)
        event_dict['event'] = event
    for key in _PII_KEYS:
        if key in event_dict:
            event_dict[key] = '[REDACTED]'
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(format='%(message)s', level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt='iso'),
            _redact_pii,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
