import logging
import re
import structlog

_PHONE_RE = re.compile(r'\+\d{7,15}')
_EMAIL_RE = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
_PII_KEYS = frozenset({'phone_e164', 'phone', 'email', 'display_name', 'wa_id', 'actor_id'})


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        value = _PHONE_RE.sub('[PHONE]', value)
        value = _EMAIL_RE.sub('[EMAIL]', value)
        return value
    if isinstance(value, dict):
        return {k: '[REDACTED]' if k in _PII_KEYS else _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v) for v in value)
    return value


def _redact_pii(logger: object, method: str, event_dict: dict) -> dict:
    return {k: '[REDACTED]' if k in _PII_KEYS else _redact_value(v) for k, v in event_dict.items()}


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
