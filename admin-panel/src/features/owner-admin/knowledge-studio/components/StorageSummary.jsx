import { Card, CardHeader, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../KnowledgeStudio.module.css';

/**
 * Format a byte size as a short human-readable string for the Storage summary
 * card. Returns `—` if the value is missing or non-finite. Uses MB / GB once
 * past 1 MiB; otherwise falls back to KB.
 */
export function formatStorageSize(bytes) {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes >= 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(0)} KB`;
  }
  return `${bytes} B`;
}

/**
 * Derive a backend label + tone for the Storage summary tile. `s3` reads as
 * "S3 dedicado" (matching the designer HTML); anything else falls back to
 * "Local develop".
 */
export function backendLabel(backend) {
  if (backend === 's3') return { label: 'S3 dedicado', tone: 'success' };
  return { label: 'Local develop', tone: 'neutral' };
}

/**
 * Storage summary card — embedded read-only inside `KnowledgeStudio` per the
 * UI-016.2 design. Shows backend, bucket/prefix, document count and total
 * size. The full editable form remains in the dedicated `knowledge-storage`
 * module (separate route + capability `knowledge_storage.write`).
 *
 * @param {{
 *   storage: { backend?: string, bucket?: string, effective_bucket?: string, prefix?: string,
 *              secret_configured?: boolean, total_bytes?: number, document_count?: number } | null,
 *   documentCount: number,
 *   isLoading?: boolean,
 *   error?: string | null,
 * }} props
 */
export function StorageSummary({ storage, documentCount, isLoading = false, error = null }) {
  const backend = storage?.backend || (isLoading ? null : 'local');
  const backendInfo = backend ? backendLabel(backend) : null;
  // Always combine bucket + prefix when a prefix is configured. The backend's
  // `effective_bucket` exposes just the bucket name (or the global default);
  // the `prefix` lives in a separate field. Short-circuiting on
  // `effective_bucket` alone dropped the prefix for S3 tenants with a
  // configured prefix, which defeats the "Bucket / prefix" summary operators
  // use to verify where uploads are stored. (codex P2 review, UI-016.2.)
  const bucketBase = storage?.effective_bucket || storage?.bucket || null;
  const prefix = storage?.prefix || '';
  const bucket = bucketBase
    ? prefix
      ? `${bucketBase}${prefix.startsWith('/') ? '' : '/'}${prefix}`
      : bucketBase
    : prefix
    ? `storage local${prefix.startsWith('/') ? '' : '/'}${prefix}`
    : '—';
  const totalBytes = typeof storage?.total_bytes === 'number' ? storage.total_bytes : null;
  const docs =
    typeof storage?.document_count === 'number' ? storage.document_count : documentCount;

  return (
    <Card padding="md">
      <CardHeader
        title="Storage"
        subtitle="Backend que respalda los documentos. Las credenciales viven fuera de la base de datos."
        actions={
          backendInfo ? (
            <StatusBadge tone={backendInfo.tone}>{backendInfo.label}</StatusBadge>
          ) : null
        }
      />

      {error ? <p className={styles.docError}>{error}</p> : null}
      {isLoading ? <p className={styles.hint}>Cargando configuración de storage…</p> : null}

      <dl className={styles.storageGrid}>
        <div className={styles.storageItem}>
          <dt>Backend</dt>
          <dd>
            <strong>{backendInfo?.label || '—'}</strong>
            <span className={styles.storageHint}>
              {storage?.secret_configured
                ? 'Credenciales fuera de DB'
                : backend === 's3'
                ? 'Falta configurar el secreto'
                : 'Volumen local — pilotos y desarrollo'}
            </span>
          </dd>
        </div>
        <div className={styles.storageItem}>
          <dt>Bucket / prefix</dt>
          <dd>
            <code className={styles.storageBucket}>{bucket}</code>
          </dd>
        </div>
        <div className={styles.storageItem}>
          <dt>Documentos</dt>
          <dd>
            <strong>{docs}</strong>
          </dd>
        </div>
        <div className={styles.storageItem}>
          <dt>Tamaño</dt>
          <dd>
            <strong>{formatStorageSize(totalBytes)}</strong>
          </dd>
        </div>
      </dl>
    </Card>
  );
}
