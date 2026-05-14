import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import { DPA_POLICY } from '../auditData.js';
import styles from '../AuditPanel.module.css';

/**
 * Privacy tools panel: GDPR contact suppression, tenant data export and the
 * read-only DPA policy summary. Presentational — all state and the actions come
 * from the `useAuditData` hook via props.
 *
 * @param {{
 *   suppressId: string,
 *   isBusy: boolean,
 *   tenantId: string | undefined,
 *   onSuppressIdChange: (value: string) => void,
 *   onSuppress: () => void,
 *   onExportTenantData: () => void,
 * }} props
 */
export function PrivacyTools({
  suppressId,
  isBusy,
  tenantId,
  onSuppressIdChange,
  onSuppress,
  onExportTenantData,
}) {
  // Local handlers keep the legacy names so the static tests can assert on the
  // markup (handleSuppressContact / handleExportTenantData).
  const handleSuppressContact = (event) => {
    event.preventDefault();
    onSuppress();
  };
  const handleExportTenantData = () => onExportTenantData();

  return (
    <>
      <Card padding="md">
        <CardHeader
          title="Supresión de contacto (GDPR / derecho al olvido)"
          subtitle="Anonimiza irreversiblemente nombre, teléfono y WA ID de un contacto; queda con estado suppressed. La acción se registra en auditoría."
        />
        <form className={styles.privacyForm} onSubmit={handleSuppressContact}>
          <FormField label="UUID del contacto">
            <input
              type="text"
              value={suppressId}
              onChange={(event) => onSuppressIdChange(event.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
          </FormField>
          <button
            type="submit"
            className={styles.dangerButton}
            data-testid="danger-action"
            disabled={isBusy || !suppressId.trim()}
          >
            Suprimir contacto
          </button>
        </form>
      </Card>

      <Card padding="md">
        <CardHeader
          title="Exportación de datos del tenant"
          subtitle="Genera un JSON con la configuración del tenant, ajustes de privacidad, canales activos y conteos de datos operativos. No incluye mensajes ni PII en claro."
        />
        <button
          type="button"
          className={styles.secondaryButton}
          disabled={isBusy || !tenantId}
          onClick={handleExportTenantData}
        >
          Descargar datos del tenant
        </button>
      </Card>

      <Card padding="md">
        <CardHeader title="Política de datos (DPA)" />
        <ul className={styles.dpaList}>
          {DPA_POLICY.map((item) => (
            <li key={item.title}>
              <strong>{item.title}:</strong> {item.body}
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
