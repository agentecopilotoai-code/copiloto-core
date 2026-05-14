import { FormField, Modal, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../KnowledgeStudio.module.css';

/**
 * RAG smoke-test drawer. Sends a user message through `POST /v1/intents/evaluate`
 * and shows the detected intent + the RAG answer + the retrieved chunks.
 * Presentational — all state and the evaluate action come from the
 * `useKnowledgeStudioData` hook via props.
 *
 * @param {{
 *   open: boolean,
 *   question: string,
 *   includeAgentsOnly: boolean,
 *   result: object | null,
 *   isEvaluating: boolean,
 *   onQuestionChange: (value: string) => void,
 *   onIncludeAgentsOnlyChange: (value: boolean) => void,
 *   onEvaluate: () => void,
 *   onClose: () => void,
 * }} props
 */
export function RagSmokeTest({
  open,
  question,
  includeAgentsOnly,
  result,
  isEvaluating,
  onQuestionChange,
  onIncludeAgentsOnlyChange,
  onEvaluate,
  onClose,
}) {
  if (!open) return null;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Probar clasificador + RAG"
      description="Escribe un mensaje del usuario para ver la intención detectada y la respuesta RAG generada a partir de los documentos activos. Consume POST /v1/intents/evaluate."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cerrar
          </button>
          <button
            type="submit"
            form="knowledge-rag-form"
            className={styles.primaryButton}
            disabled={isEvaluating || !question.trim()}
          >
            {isEvaluating ? 'Clasificando…' : 'Clasificar'}
          </button>
        </div>
      }
    >
      <form
        id="knowledge-rag-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onEvaluate();
        }}
      >
        <FormField label="Pregunta de prueba">
          <textarea
            rows={3}
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            placeholder="Ej. ¿Cuánto dura la garantía del servicio?"
          />
        </FormField>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={includeAgentsOnly}
            onChange={(event) => onIncludeAgentsOnlyChange(event.target.checked)}
          />
          Incluir documentos «Solo agentes» (vista interna; nunca se envía al cliente)
        </label>
      </form>

      {result ? (
        <div className={styles.ragResult}>
          {result.intent ? (
            <div className={styles.ragBadges}>
              <StatusBadge tone="accent">Intención: {result.intent}</StatusBadge>
              <StatusBadge tone="neutral">
                Confianza:{' '}
                {result.confidence?.toFixed ? result.confidence.toFixed(2) : result.confidence}
              </StatusBadge>
              <StatusBadge tone="neutral">Capa: {result.resolved_by}</StatusBadge>
            </div>
          ) : null}
          <div className={styles.ragAnswer}>
            <StatusBadge tone={result.sufficient_context ? 'success' : 'danger'}>
              {result.status}
            </StatusBadge>
            <p>{result.answer || result.reason}</p>
            {result.handoff?.required ? (
              <strong>Escalar a humano: {result.handoff.reason}</strong>
            ) : null}
          </div>
          <div className={styles.ragChunks}>
            <h4>Chunks recuperados</h4>
            {(result.chunks || []).length === 0 ? (
              <p className={styles.hint}>
                No se recuperaron chunks activos para esta pregunta.
              </p>
            ) : (
              result.chunks.map((chunk) => (
                <article className={styles.ragChunk} key={chunk.id}>
                  <div className={styles.ragChunkMeta}>
                    <span>score {chunk.score}</span>
                    <span>{chunk.visibility}</span>
                    <span>{chunk.source_type}</span>
                  </div>
                  <strong>{chunk.document_title}</strong>
                  <small>
                    {chunk.section_path || 'Documento'} ·{' '}
                    {chunk.source_uri || 'fuente manual'} · chunk #{chunk.chunk_index}
                  </small>
                  <p>{chunk.excerpt}</p>
                </article>
              ))
            )}
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
