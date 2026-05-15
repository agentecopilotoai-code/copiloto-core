import { Button, Card, FormField } from '../../../../components/ui/index.js';
import styles from '../TenantSetupWizard.module.css';

export function PaymentsTab({ state, actions }) {
  const { paymentSettings, paymentForm, isBusy, currentTenantId } = state;
  const { handleSavePaymentSettings, setPaymentSettings, setPaymentForm } = actions;

  return (
    <Card padding="md">
      <form className={styles.formGrid} onSubmit={handleSavePaymentSettings}>
        <div className={styles.wide}>
          <h3 className={styles.sectionTitle}>Configuración de pagos</h3>
          <p className={styles.hint}>
            Genera links de pago para tus citas usando MercadoPago o Stripe. La API key se guarda cifrada y nunca
            se devuelve al panel. Configura el webhook del proveedor apuntando a
            <code> /v1/webhooks/payments/{paymentSettings.provider === 'none' ? '{provider}' : paymentSettings.provider}</code>.
          </p>
        </div>
        <FormField label="Proveedor">
          <select
            onChange={(event) => setPaymentSettings({ ...paymentSettings, provider: event.target.value })}
            value={paymentSettings.provider}
          >
            <option value="none">Sin pagos</option>
            <option value="mercadopago">MercadoPago</option>
            <option value="stripe">Stripe</option>
          </select>
        </FormField>
        <FormField label="Moneda por defecto">
          <input
            maxLength={3}
            onChange={(event) =>
              setPaymentSettings({ ...paymentSettings, currency: event.target.value.toUpperCase() })
            }
            placeholder="COP"
            value={paymentSettings.currency || ''}
          />
        </FormField>
        <FormField label="Monto por defecto (opcional)">
          <input
            min="0"
            onChange={(event) => setPaymentSettings({ ...paymentSettings, default_amount: event.target.value })}
            placeholder="Ej. 50000"
            step="0.01"
            type="number"
            value={paymentSettings.default_amount ?? ''}
          />
        </FormField>
        <FormField label="API key del proveedor" className={styles.wide}>
          <input
            autoComplete="off"
            disabled={paymentSettings.provider === 'none'}
            onChange={(event) => setPaymentForm({ ...paymentForm, apiKey: event.target.value })}
            placeholder={paymentSettings.api_key_configured ? '••••••• (configurada, deja vacío para conservar)' : 'Pega aquí la API key'}
            type="password"
            value={paymentForm.apiKey}
          />
        </FormField>
        <FormField label="Webhook secret (requerido)" className={styles.wide}>
          <input
            autoComplete="off"
            disabled={paymentSettings.provider === 'none'}
            onChange={(event) => setPaymentForm({ ...paymentForm, webhookSecret: event.target.value })}
            placeholder={paymentSettings.webhook_secret_configured ? '••••••• (configurado, deja vacío para conservar)' : 'Pega el secret de firma del proveedor'}
            type="password"
            value={paymentForm.webhookSecret}
          />
        </FormField>
        <div className={styles.wide}>
          <p className={styles.hint}>
            Estado: proveedor <strong>{paymentSettings.provider}</strong> ·
            API key {paymentSettings.api_key_configured ? '✅ configurada' : '⚠️ no configurada'} ·
            Webhook secret {paymentSettings.webhook_secret_configured ? '✅ configurado' : '⚠️ requerido para validar firmas del proveedor'}.
          </p>
          <p className={styles.hint}>
            <strong>Importante:</strong> el servidor rechaza los webhooks de
            pago con <code>503 payment.webhook_unconfigured</code> si no hay
            secret cargado, y con <code>401</code> si la firma no valida.
            Cualquiera de los dos rechazos queda registrado en{' '}
            <code>audit_logs</code> (<code>payment.webhook_rejected</code>).
          </p>
        </div>
        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar pagos
          </Button>
        </div>
      </form>
    </Card>
  );
}
