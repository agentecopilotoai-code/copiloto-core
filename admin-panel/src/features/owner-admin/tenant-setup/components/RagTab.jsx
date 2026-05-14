import { embeddingProviderOptions } from '../tenantSetupData.js';

export function RagTab({ state, actions }) {
  const { ragForm, reindexResult, isBusy, currentTenantId } = state;
  const { handleProviderChange, handleReindexAll } = actions;

  return (
    <div className="wizard-panel">
      <div className="ia-rag-header">
        <h3>Configuración de IA y RAG</h3>
        <p className="hint">
          El proveedor activo se configura en las variables de entorno del servidor
          (<code>RAG_EMBEDDING_PROVIDER</code>, <code>RAG_EMBEDDING_MODEL</code>).
          Desde aquí puedes re-indexar todos los documentos activos con el proveedor en uso.
        </p>
      </div>

      <div className="ia-rag-provider-info">
        <h4>Proveedores disponibles</h4>
        {embeddingProviderOptions.map((opt) => (
          <div
            key={opt.value}
            className={`provider-card ${ragForm.provider === opt.value ? 'selected' : ''}`}
            role="button"
            tabIndex={0}
            onClick={() => handleProviderChange(opt.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleProviderChange(opt.value)}
          >
            <div className="provider-card-title">
              <strong>{opt.label}</strong>
              <span className={`status-badge ${opt.value === 'local_hash' ? 'trial' : 'active'}`}>
                {opt.value === 'local_hash' ? 'Léxico (hash)' : 'Semántico (real)'}
              </span>
            </div>
            <p className="hint">{opt.description}</p>
            <small>Modelo sugerido: <code>{opt.defaultModel}</code> · {opt.defaultDims} dims</small>
          </div>
        ))}
      </div>

      <div className="ia-rag-status">
        <h4>Estado del proveedor activo en servidor</h4>
        <p className="hint">
          El badge refleja el proveedor configurado en el servidor. Para cambiar el proveedor
          activo actualiza <code>RAG_EMBEDDING_PROVIDER</code> y <code>RAG_EMBEDDING_API_KEY</code>
          en el entorno del servidor y reinicia el servicio.
        </p>
        <div className="provider-status-badge">
          <span className="status-badge active">Semántico (real)</span>
          <span className="hint"> cuando provider ≠ local_hash</span>
          <span className="status-badge suspended" style={{ marginLeft: '0.5rem' }}>Léxico (hash)</span>
          <span className="hint"> cuando provider = local_hash</span>
        </div>
      </div>

      <form className="ia-rag-reindex form-grid" onSubmit={handleReindexAll}>
        <div className="wide">
          <h4>Re-indexar todos los documentos</h4>
          <p className="hint">
            Re-procesa todos los documentos activos y draft del tenant con el proveedor de
            embeddings configurado actualmente en el servidor. Los chunks anteriores serán
            reemplazados. La operación puede tardar según el número de documentos.
          </p>
        </div>
        <div className="form-actions wide">
          <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
            {isBusy ? 'Re-indexando…' : 'Re-indexar todos los documentos'}
          </button>
        </div>
        {reindexResult && (
          <div className="builder-preview wide">
            <strong>Resultado de re-indexación</strong>
            <pre>{JSON.stringify(reindexResult, null, 2)}</pre>
          </div>
        )}
      </form>
    </div>
  );
}
