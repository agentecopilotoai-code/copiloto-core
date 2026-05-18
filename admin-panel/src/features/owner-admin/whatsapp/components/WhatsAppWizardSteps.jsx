import { Card, CardHeader, FormField, Stepper } from '../../../../components/ui/index.js';
import styles from '../WhatsAppOnboarding.module.css';

const SECRETS_HELP = `Meta access token: CopilotoIA lo escribe en secrets/tenants/<tenant_id>/meta_access_token para envíos outbound.
App Secret: CopilotoIA lo escribe en secrets/tenants/<tenant_id>/whatsapp_app_secret para validar X-Hub-Signature-256; si pegas APP_ID|APP_SECRET, se almacena solo APP_SECRET.
Verify token: CopilotoIA lo escribe en secrets/tenants/<tenant_id>/whatsapp_verify_token y el GET del webhook solo lee desde ahí.
Modo mock: el worker marca el mensaje como simulado y no llama a Meta.
Modo real: el worker llama a Meta usando el secreto meta_access_token del tenant; si ese secreto falta o es local-mock/change-me, el mensaje falla explícitamente.
El usuario solo pega los tres valores secretos; las referencias internas se derivan automáticamente con la misma estructura para todos los tenants.`;

/**
 * Channel setup form + onboarding checklist. Reuses `Card`, `FormField` and the
 * `Stepper` primitive. Presentational — all state and the mutation actions come
 * from the `useWhatsAppData` hook via props. The channel-upsert + health logic
 * is preserved verbatim from the legacy `WhatsAppOnboarding`.
 *
 * @param {{
 *   form: object,
 *   checklist: Array<{id: string, label: string, description: string, done: boolean}>,
 *   health: object | null,
 *   isBusy: boolean,
 *   isLoadingChannel: boolean,
 *   loadError: Error | null,
 *   tenantId: string | undefined,
 *   onFieldChange: (field: string, value: string) => void,
 *   onSubmit: () => void,
 *   onRefreshHealth: () => void,
 * }} props
 */
export function WhatsAppWizardSteps({
  form,
  checklist,
  health,
  isBusy,
  isLoadingChannel,
  loadError,
  tenantId,
  onFieldChange,
  onSubmit,
  onRefreshHealth,
}) {
  const set = (field) => (event) => onFieldChange(field, event.target.value);
  const checks = health?.checks || {};
  const steps = checklist.map((step) => ({
    key: step.id,
    label: step.label,
    description: step.description,
    status: step.done ? 'done' : 'pending',
  }));

  return (
    <div className={styles.setupGrid}>
      <Card padding="md">
        <CardHeader
          title="Configuración del canal"
          subtitle="Los tokens y app secrets nunca se almacenan en plano: solo guardamos la referencia al gestor de secretos."
        />
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <div className={styles.formRow}>
            <FormField label="Business ID" required>
              <input
                type="text"
                autoComplete="off"
                required
                value={form.business_id}
                onChange={set('business_id')}
                placeholder="ID numérico de Meta Business (≈15 dígitos)"
              />
            </FormField>
            <FormField label="WABA ID" required>
              <input
                type="text"
                autoComplete="off"
                required
                value={form.waba_id}
                onChange={set('waba_id')}
                placeholder="ID numérico del WhatsApp Business Account"
              />
            </FormField>
          </div>
          <FormField
            label="Phone Number ID"
            required
            hint="El servidor valida que este Phone Number ID no esté bound a otro tenant activo; si ya está registrado el guardado falla con 409 y debes contactar a soporte para liberarlo."
          >
            <input
              type="text"
              autoComplete="off"
              required
              value={form.phone_number_id}
              onChange={set('phone_number_id')}
              placeholder="ID numérico del Phone Number (cópialo del dashboard Meta)"
            />
          </FormField>
          <FormField label="Modo de entrega">
            <select value={form.account_mode} onChange={set('account_mode')}>
              <option value="mock">Mock local (no envía a WhatsApp)</option>
              <option value="live">Real vía WhatsApp Cloud API</option>
            </select>
          </FormField>
          <FormField
            label="Meta access token del tenant"
            hint="Requerido la primera vez o cuando quieras rotarlo; se guarda en secrets/tenants/<tenant_id>/meta_access_token."
          >
            <input
              type="password"
              autoComplete="off"
              value={form.meta_access_token}
              onChange={set('meta_access_token')}
              required={!checks.meta_access_token_configured}
              placeholder="Pega aquí el token real solo para guardarlo en el secreto del tenant"
            />
          </FormField>
          <FormField
            label="App secret del tenant"
            hint="Requerido la primera vez o cuando quieras rotarlo; se guarda en secrets/tenants/<tenant_id>/whatsapp_app_secret. Si pegas APP_ID|APP_SECRET, se almacena solo APP_SECRET."
          >
            <input
              type="password"
              autoComplete="off"
              value={form.app_secret}
              onChange={set('app_secret')}
              required={!checks.app_secret_configured}
              placeholder="App Secret o APP_ID|APP_SECRET; CopilotoIA guardará solo el secret"
            />
          </FormField>
          <FormField
            label="Verify token del webhook"
            hint="Requerido la primera vez o cuando quieras rotarlo; se guarda en secrets/tenants/<tenant_id>/whatsapp_verify_token y el GET del webhook solo lee desde ahí."
          >
            <input
              type="password"
              autoComplete="off"
              value={form.verify_token}
              onChange={set('verify_token')}
              required={!checks.verify_token_configured}
              placeholder="Pega aquí el token de verificación que configurarás en Meta Webhooks"
            />
          </FormField>
          <div className={styles.formActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={isBusy || isLoadingChannel || !tenantId}
              onClick={onRefreshHealth}
            >
              Ver health
            </button>
            <button
              type="submit"
              className={styles.primaryButton}
              disabled={isBusy || isLoadingChannel || Boolean(loadError) || !tenantId}
            >
              Registrar canal
            </button>
          </div>
        </form>
        <details className={styles.secretsHelp}>
          <summary>Variables y secretos requeridos</summary>
          <pre className={styles.secretsHelpPre}>{SECRETS_HELP}</pre>
        </details>
      </Card>

      <Card padding="md">
        <CardHeader
          title="Checklist de onboarding"
          subtitle="Cinco pasos para dejar el canal listo para pruebas controladas."
        />
        <Stepper steps={steps} />
      </Card>
    </div>
  );
}
