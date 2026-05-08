from pathlib import Path

POOL = Path('app/db/pool.py')


def test_record_to_dict_converts_bytea_values_before_fastapi_encoding():
    source = POOL.read_text()

    assert 'def _json_safe_value' in source
    assert 'isinstance(value, bytes)' in source
    assert 'return value.hex()' in source
    assert 'return {key: _json_safe_value(value) for key, value in dict(record).items()}' in source
