import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backup_script_creates_required_artifacts():
    script = (ROOT / 'scripts' / 'backup-local.sh').read_text(encoding='utf-8')

    assert 'pg_dump' in script
    assert '--format=custom' in script
    assert 'table-counts.tsv' in script
    assert 'knowledge-documents.tsv' in script
    assert 'knowledge-files.tar' in script
    assert 'manifest.json' in script
    assert 'sha256sum' in script


def test_backup_script_does_not_use_pg_dump_file_dash():
    # `pg_dump --file=-` writes to a literal file named "-" inside the
    # container instead of stdout, producing a 0-byte local dump. The drill
    # for TASK-0029 caught this; keep the regression locked in.
    script = (ROOT / 'scripts' / 'backup-local.sh').read_text(encoding='utf-8')
    assert '--file=-' not in script
    assert 'pg_dump produjo un archivo vacío' in script


def test_restore_script_requires_clean_database_and_validates_counts():
    script = (ROOT / 'scripts' / 'restore-local.sh').read_text(encoding='utf-8')

    assert '--allow-non-empty' in script
    assert 'la DB local no está limpia' in script
    assert 'pg_restore' in script
    assert '--clean' in script
    assert 'diff -u "$BACKUP_DIR/table-counts.tsv"' in script
    assert 'tenants, documentos, chunks y audit logs' in script


def test_backup_and_restore_scripts_have_valid_bash_syntax():
    bash = shutil.which('bash')
    assert bash is not None, 'bash binary not available on PATH'
    for name in ('backup-local.sh', 'restore-local.sh'):
        path = ROOT / 'scripts' / name
        result = subprocess.run(
            [bash, '-n', str(path)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, f'{name} falló bash -n: {result.stderr}'
