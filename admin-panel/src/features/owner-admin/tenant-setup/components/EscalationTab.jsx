import { Button, Card, FormField } from '../../../../components/ui/index.js';
import styles from '../TenantSetupWizard.module.css';

export function EscalationTab({ state, actions }) {
  const { escalationForm, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setEscalationForm } = actions;

  return (
    <Card padding="md">
      <form className={styles.formGrid} onSubmit={handleSaveSettings}>
        <label className={`${styles.inlineCheck} ${styles.wide}`}>
          <input
            checked={escalationForm.enabled}
            onChange={(event) => setEscalationForm({ ...escalationForm, enabled: event.target.checked })}
            type="checkbox"
          />
          Habilitar escalamiento humano
        </label>
        <FormField label="Cola">
          <input
            value={escalationForm.queue}
            onChange={(event) => setEscalationForm({ ...escalationForm, queue: event.target.value })}
          />
        </FormField>
        <FormField label="Prioridad">
          <select
            value={escalationForm.priority}
            onChange={(event) => setEscalationForm({ ...escalationForm, priority: event.target.value })}
          >
            <option>low</option>
            <option>normal</option>
            <option>high</option>
          </select>
        </FormField>
        <FormField label="Máximo de turnos del bot antes de escalar (triggers.after_bot_turns)">
          <input
            min="1"
            max="50"
            value={escalationForm.afterBotTurns}
            onChange={(event) => setEscalationForm({ ...escalationForm, afterBotTurns: event.target.value })}
            type="number"
          />
        </FormField>
        <FormField label="Respuestas sin contexto antes de escalar">
          <input
            min="1"
            max="20"
            value={escalationForm.consecutiveNoContextLimit}
            onChange={(event) =>
              setEscalationForm({ ...escalationForm, consecutiveNoContextLimit: event.target.value })
            }
            type="number"
          />
        </FormField>
        <FormField label="Confianza menor a">
          <input
            max="1"
            min="0"
            step="0.01"
            value={escalationForm.confidenceBelow}
            onChange={(event) => setEscalationForm({ ...escalationForm, confidenceBelow: event.target.value })}
            type="number"
          />
        </FormField>
        <FormField
          label="Keywords de escalamiento — fuerzan handoff inmediato (separadas por coma)"
          className={styles.wide}
        >
          <input
            placeholder="humano, asesor, demanda, fraude"
            value={escalationForm.keywords}
            onChange={(event) => setEscalationForm({ ...escalationForm, keywords: event.target.value })}
          />
        </FormField>
        <label className={`${styles.inlineCheck} ${styles.wide}`}>
          <input
            type="checkbox"
            checked={escalationForm.enforceServiceWindow}
            onChange={(event) =>
              setEscalationForm({ ...escalationForm, enforceServiceWindow: event.target.checked })
            }
          />
          Forzar handoff si la ventana de servicio WhatsApp (24 h) expiró
        </label>
        <FormField label="Mensaje de handoff" className={styles.wide}>
          <textarea
            value={escalationForm.handoffMessage}
            onChange={(event) => setEscalationForm({ ...escalationForm, handoffMessage: event.target.value })}
          />
        </FormField>
        <FormField
          label="Self-service: horas mínimas antes de la cita"
          hint="Si el cliente pide cancelar o reagendar a menos horas de inicio que esto, el bot escala a un humano en lugar de actuar (default 2h)."
        >
          <input
            type="number"
            min="0"
            max="72"
            step="0.5"
            value={escalationForm.selfServiceMinHoursBeforeStart}
            onChange={(event) =>
              setEscalationForm({
                ...escalationForm,
                selfServiceMinHoursBeforeStart: event.target.value,
              })
            }
          />
        </FormField>
        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar escalamiento
          </Button>
        </div>
      </form>
    </Card>
  );
}
