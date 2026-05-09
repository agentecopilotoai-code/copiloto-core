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


def test_restore_script_requires_clean_database_and_validates_counts():
    script = (ROOT / 'scripts' / 'restore-local.sh').read_text(encoding='utf-8')

    assert '--allow-non-empty' in script
    assert 'la DB local no está limpia' in script
    assert 'pg_restore' in script
    assert '--clean' in script
    assert 'diff -u "$BACKUP_DIR/table-counts.tsv"' in script
    assert 'tenants, documentos, chunks y audit logs' in script
