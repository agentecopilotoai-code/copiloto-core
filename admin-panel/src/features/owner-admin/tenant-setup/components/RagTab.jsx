import { Button, Card } from '../../../../components/ui/index.js';
import { embeddingProviderOptions } from '../tenantSetupData.js';
import styles from '../TenantSetupWizard.module.css';

export function RagTab({ state, actions }) {
  const { ragForm, reindexResult, isBusy, currentTenantId } = state;
  const { handleProviderChange, handleReindexAll } = actions;

  return (
    <>
      <Card padding="md">
        <h3 className={styles.sectionTitle}>Configuración de IA y RAG</h3>
        <p className={styles.hint}>
          El proveedor activo se configura en las variables de entorno del servidor
          (<code>RAG_EMBEDDING_PROVIDER</code>, <code>RAG_EMBEDDING_MODEL</code>).
          Desde aquí puedes re-indexar todos los documentos activos con el proveedor en uso.
        </p>

        <h4 className={styles.sectionTitle}>Proveedores disponibles</h4>
        <div className={styles.optionGrid}>
          {embeddingProviderOptions.map((opt) => (
            <div
              key={opt.value}
              className={`${styles.providerCard} ${ragForm.provider === opt.value ? styles.selected : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => handleProviderChange(opt.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleProviderChange(opt.value)}
            >
              <div className={styles.providerCardTitle}>
                <strong>{opt.label}</strong>
                <span className={`status-badge ${opt.value === 'local_hash' ? 'trial' : 'active'}`}>
                  {opt.value === 'local_hash' ? 'Léxico (hash)' : 'Semántico (real)'}
                </span>
              </div>
              <p className={styles.hint}>{opt.description}</p>
              <small className={styles.hint}>
                Modelo sugerido: <code>{opt.defaultModel}</code> · {opt.defaultDims} dims
              </small>
            </div>
          ))}
        </div>

        <h4 className={styles.sectionTitle}>Estado del proveedor activo en servidor</h4>
        <p className={styles.hint}>
          El badge refleja el proveedor configurado en el servidor. Para cambiar el proveedor
          activo actualiza <code>RAG_EMBEDDING_PROVIDER</code> y <code>RAG_EMBEDDING_API_KEY</code>
          en el entorno del servidor y reinicia el servicio.
        </p>
        <p className={styles.hint}>
          <span className="status-badge active">Semántico (real)</span>{' '}
          cuando provider ≠ local_hash{' '}
          <span className="status-badge suspended">Léxico (hash)</span>{' '}
          cuando provider = local_hash
        </p>
      </Card>

      <Card padding="md">
        <form className={styles.formGrid} onSubmit={handleReindexAll}>
          <div className={styles.wide}>
            <h4 className={styles.sectionTitle}>Re-indexar todos los documentos</h4>
            <p className={styles.hint}>
              Re-procesa todos los documentos activos y draft del tenant con el proveedor de
              embeddings configurado actualmente en el servidor. Los chunks anteriores serán
              reemplazados. La operación puede tardar según el número de documentos.
            </p>
          </div>
          <div className={`${styles.actions} ${styles.wide}`}>
            <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
              {isBusy ? 'Re-indexando…' : 'Re-indexar todos los documentos'}
            </Button>
          </div>
          {reindexResult && (
            <div className={`${styles.builderPreview} ${styles.wide}`}>
              <strong>Resultado de re-indexación</strong>
              <pre>{JSON.stringify(reindexResult, null, 2)}</pre>
            </div>
          )}
        </form>
      </Card>
    </>
  );
}
