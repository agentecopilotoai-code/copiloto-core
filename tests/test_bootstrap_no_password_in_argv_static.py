"""SEC-010 (DATABASE_URL password exposed in bootstrap process args) —
defienden que ningún script de bootstrap/backup/restore pase
``$DATABASE_URL_VALUE`` (que contiene el password embebido) como argv a
``psql`` / ``pg_dump`` / ``pg_restore``.

Antes: ``scripts/bootstrap.sh``, ``scripts/backup-local.sh`` y
``scripts/restore-local.sh`` hacían ``psql "$DATABASE_URL_VALUE" ...``.
Durante la ejecución (los dumps y restores tardan minutos), CUALQUIER
otro usuario del host podía hacer ``ps aux | grep psql`` y ver el URL
completo con password embebido — ventana lo suficientemente larga para
que un proceso adversarial (ej. un container hostil en el mismo host,
un agente de monitoring mal configurado) muestree el cmdline.

Fix: separar password del URL via ``parse_db_url`` (en
``scripts/lib/postgres-url.sh``), exportar como ``PGPASSWORD`` en el
shell padre, y pasar ``-e PGPASSWORD`` (sin valor) a ``docker compose
exec`` — el ``-e VAR`` sin valor inherita del shell padre, así que el
password tampoco aparece en el argv de ``docker``.

Si alguno de estos scripts re-introduce el patrón viejo, este suite
falla.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

LIB_URL = Path('scripts/lib/postgres-url.sh')
BOOTSTRAP = Path('scripts/bootstrap.sh')
BACKUP_LOCAL = Path('scripts/backup-local.sh')
RESTORE_LOCAL = Path('scripts/restore-local.sh')

ALL_SCRIPTS = (BOOTSTRAP, BACKUP_LOCAL, RESTORE_LOCAL)


# ───── Helper compartido existe y tiene la firma esperada ────────────────


def test_postgres_url_helper_exists():
    assert LIB_URL.is_file()
    body = LIB_URL.read_text()
    # La función principal debe estar declarada con el nombre exacto que
    # los scripts importan.
    assert 'parse_db_url()' in body
    # Debe setear las dos variables que los scripts consumen.
    assert 'DB_PASSWORD=' in body
    assert 'DB_URL_NO_PASSWORD=' in body


def test_parse_db_url_actually_works():
    """Test dinámico — invoca el helper real con bash y verifica el output.
    Si el parser se rompe (ej. alguien cambia un parameter expansion), los
    scripts seguirían "pareciendo seguros" en el AST pero pasarían un URL
    mal-formado a psql.
    """
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://copiloto_app:s3cr3t@postgres:5432/copilotoia"
        echo "$DB_PASSWORD"
        echo "$DB_URL_NO_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.strip().split('\n')
    assert lines[0] == 's3cr3t'
    assert lines[1] == 'postgresql://copiloto_app@postgres:5432/copilotoia'


def test_parse_db_url_handles_no_password():
    """Sin password en URL → DB_PASSWORD vacío + URL pasa intacto."""
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://copiloto_app@postgres:5432/copilotoia"
        echo "len:${#DB_PASSWORD}"
        echo "$DB_URL_NO_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.strip().split('\n')
    assert lines[0] == 'len:0'
    assert lines[1] == 'postgresql://copiloto_app@postgres:5432/copilotoia'


def test_parse_db_url_preserves_query_string():
    """Para connections con `sslmode=require` etc., el query string debe
    sobrevivir el roundtrip — psql falla en SSL si lo perdemos."""
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://u:p@h:5432/db?sslmode=require&application_name=cpi"
        echo "$DB_URL_NO_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout.strip()
    assert 'sslmode=require' in out
    assert 'application_name=cpi' in out


def test_parse_db_url_decodes_url_encoded_password():
    """SEC-010.8 codex P2 review: el password puede venir URL-encoded
    (`%40` para `@`, `%3A` para `:`, etc.) porque el .env tiene que
    encodear caracteres reservados de URI. libpq decodifica los `%XX`
    cuando parsea la URL COMPLETA pero NO los decodifica cuando lee
    `PGPASSWORD` (lo trata como literal). Sin la decodificación, exportar
    los bytes encoded comparía contra el password real `p@ss` el string
    `p%40ss` y fallaría auth.

    El parser DEBE decodificar el password antes de exportar.
    """
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://u:p%40ss@host:5432/db"
        echo "$DB_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    # `p%40ss` URL-encoded → `p@ss` literal en PGPASSWORD.
    assert result.stdout.strip() == 'p@ss'


def test_parse_db_url_decodes_multiple_special_chars_in_password():
    """Caso más complejo del bot: password con `@`, `:`, `/` URL-encoded."""
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://u:p%40ss%3Aword%2Fextra@host/db"
        echo "$DB_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == 'p@ss:word/extra'


def test_parse_db_url_decodes_literal_percent_in_password():
    """Password con `%` literal debe venir como `%25` URL-encoded. Decodear
    debe devolver el `%` literal."""
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://u:abc%25def@host/db"
        echo "$DB_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == 'abc%def'


def test_parse_db_url_leaves_user_encoded_in_url():
    """Defense en profundidad: cuando un user tiene caracteres URL-encoded
    (ej. `user%40org` = `user@org`), DB_URL_NO_PASSWORD debe mantenerlo
    encoded porque libpq decodificará la URL completa que pasamos a psql.
    Si lo decodificáramos acá, libpq vería un `@` literal en el medio del
    user y se confundiría con un nuevo separator de userinfo."""
    script = """
        set -euo pipefail
        source scripts/lib/postgres-url.sh
        parse_db_url "postgresql://user%40org:p%40ss@host:5432/db"
        echo "$DB_URL_NO_PASSWORD"
    """
    result = subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    # User sigue encoded; password ya no aparece.
    assert result.stdout.strip() == 'postgresql://user%40org@host:5432/db'


def test_url_decode_helper_exists_and_is_invoked():
    """Anti-regression AST: si alguien borra la decodificación pensando
    que es legacy, el test falla. Verificamos que el helper existe Y que
    parse_db_url lo invoca para el password."""
    body = LIB_URL.read_text()
    assert 'url_decode()' in body, 'helper url_decode no existe'
    # parse_db_url debe invocar url_decode sobre el password.
    assert 'url_decode "$password_only"' in body, (
        'parse_db_url no invoca url_decode sobre el password — el codex P2 '
        'de SEC-010.8 regresaría. PGPASSWORD se lee como literal por libpq, '
        'no decodifica %XX.'
    )


# ───── Scripts no pasan DATABASE_URL_VALUE a psql/pg_dump/pg_restore ─────


def test_no_script_passes_database_url_value_to_psql():
    """Caso central del fix: ``psql "$DATABASE_URL_VALUE"`` exponía el
    password en ``ps aux``. Después del fix, ningún script puede tener
    ese patrón."""
    forbidden_patterns = [
        # psql con DATABASE_URL_VALUE como argv positional.
        r'psql\s+"\$DATABASE_URL_VALUE"',
        r"psql\s+'\$DATABASE_URL_VALUE'",
        r'psql\s+\$DATABASE_URL_VALUE',
        # pg_dump idem.
        r'pg_dump\s+"\$DATABASE_URL_VALUE"',
        r"pg_dump\s+'\$DATABASE_URL_VALUE'",
        r'pg_dump\s+\$DATABASE_URL_VALUE',
        # pg_restore con --dbname=$DATABASE_URL_VALUE.
        r'pg_restore[^\n]*--dbname="?\$DATABASE_URL_VALUE',
    ]
    for script_path in ALL_SCRIPTS:
        body = script_path.read_text()
        for pattern in forbidden_patterns:
            assert not re.search(pattern, body), (
                f'{script_path}: re-introduce el patrón `{pattern}` que SEC-010 '
                'removió — el password queda visible en `ps aux`. Usar '
                '`docker compose exec -e PGPASSWORD ... "$DB_URL_NO_PASSWORD"` '
                'después de `parse_db_url`.'
            )


def test_scripts_use_db_url_no_password_variable():
    """Después del fix, los tres scripts deben referenciar
    ``$DB_URL_NO_PASSWORD`` (la variable que setea parse_db_url) en lugar
    de ``$DATABASE_URL_VALUE`` para los comandos psql/pg_dump/pg_restore."""
    for script_path in ALL_SCRIPTS:
        body = script_path.read_text()
        assert 'DB_URL_NO_PASSWORD' in body, (
            f'{script_path}: no usa la variable DB_URL_NO_PASSWORD del helper. '
            'Sin ella, alguna ruta sigue pasando el URL con password.'
        )


def test_scripts_source_postgres_url_helper():
    """Los tres scripts deben source-ar el helper. Sin esto, las variables
    DB_PASSWORD / DB_URL_NO_PASSWORD no existirían y el comando crashearía
    o (peor) pasaría una variable vacía a psql.
    """
    for script_path in ALL_SCRIPTS:
        body = script_path.read_text()
        assert 'lib/postgres-url.sh' in body, (
            f'{script_path}: no source-a `lib/postgres-url.sh`. Sin el helper, '
            'la función `parse_db_url` no existe y el script crashea.'
        )
        assert 'parse_db_url' in body, (
            f'{script_path}: no invoca `parse_db_url`. El helper está '
            'source-ado pero nadie lo llama → DB_PASSWORD/DB_URL_NO_PASSWORD '
            'quedan unset.'
        )


def test_scripts_export_pgpassword_before_docker_exec():
    """``docker compose exec -e PGPASSWORD`` (sin valor) inherita del
    shell padre — requiere `export PGPASSWORD=$DB_PASSWORD` previo. Sin
    el export, el flag `-e PGPASSWORD` inherita un valor vacío y psql
    crashea con "authentication failed"."""
    for script_path in ALL_SCRIPTS:
        body = script_path.read_text()
        assert 'export PGPASSWORD=' in body, (
            f'{script_path}: no exporta PGPASSWORD antes del docker exec. '
            'El flag `-e PGPASSWORD` inheritaría un valor vacío.'
        )


def test_scripts_use_inherited_pgpassword_not_inline_value():
    """Defense en profundidad: usar `-e PGPASSWORD` SIN ``=valor`` — la
    forma con valor (``-e PGPASSWORD=$DB_PASSWORD``) reintroduce el
    password en el argv de ``docker`` (visible en ps aux). La forma sin
    valor inherita del shell padre, donde solo es visible via
    /proc/<pid>/environ (mismo uid o root)."""
    bad_pattern = re.compile(r'-e\s+PGPASSWORD=')
    for script_path in ALL_SCRIPTS:
        body = script_path.read_text()
        matches = bad_pattern.findall(body)
        assert not matches, (
            f'{script_path}: usa `-e PGPASSWORD=valor` que reintroduce el '
            'password en el argv de docker. Usar `-e PGPASSWORD` (sin '
            'valor) que inherita del shell padre.'
        )


# ───── psql_app helper en los 3 scripts usa el patrón seguro ─────────────


def test_psql_app_helper_uses_inherited_pgpassword_in_all_three_scripts():
    """Los tres scripts definen una función `psql_app()` con el mismo
    patrón. Verificamos que las tres usen el patrón seguro."""
    expected_pattern = re.compile(
        r'psql_app\(\)\s*\{\s*\n\s*docker\s+compose\s+exec\s+-T\s+-e\s+PGPASSWORD\s+postgres\s+psql\s+"\$DB_URL_NO_PASSWORD"',
        re.MULTILINE,
    )
    for script_path in ALL_SCRIPTS:
        body = script_path.read_text()
        assert expected_pattern.search(body), (
            f'{script_path}: `psql_app()` no usa el patrón seguro '
            '`docker compose exec -T -e PGPASSWORD postgres psql '
            '"$DB_URL_NO_PASSWORD" ...`. Posible regresión a la forma '
            'que exponía el password en argv.'
        )
