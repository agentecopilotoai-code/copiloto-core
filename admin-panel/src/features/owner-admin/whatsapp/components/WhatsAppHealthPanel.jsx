import { AlertBanner, Card, CardHeader, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../WhatsAppOnboarding.module.css';

/**
 * Channel health + identifiers panel. Surfaces the local health snapshot, the
 * Meta identifiers and the per-secret configuration checks. Presentational —
 * the `health` / `channel` records come from the `useWhatsAppData` hook.
 *
 * @param {{ health: object | null, channel: object | null }} props
 */
export function WhatsAppHealthPanel({ health, channel }) {
  const checks = health?.checks || {};
  const healthy = health?.status === 'healthy';

  const rows = [
    ['Estado local', health?.status || 'Sin health check'],
    ['Proveedor', channel?.provider || 'whatsapp_cloud_api'],
    ['Business ID', channel?.business_id || '—'],
    ['WABA ID', channel?.waba_id || '—'],
    ['Phone Number ID', channel?.phone_number_id || '—'],
    [
      'Modo de entrega',
      channel?.account_mode === 'live' ? 'Real vía WhatsApp' : 'Mock local',
    ],
    [
      'Token Meta',
      checks.meta_access_token_configured ? 'Configurado en backend' : 'Falta o es mock',
    ],
    ['App Secret', checks.app_secret_configured ? 'Configurado por tenant' : 'Falta'],
    ['Verify token', checks.verify_token_configured ? 'Configurado en secreto' : 'Falta'],
    ['Entrega real lista', checks.delivery_ready ? 'Sí' : 'No'],
    ['Calidad', channel?.quality_rating || 'Pendiente de sincronización Meta'],
    ['Límite de mensajería', channel?.messaging_limit_tier || 'Pendiente de sincronización Meta'],
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Salud del canal"
        subtitle="Snapshot local del estado del canal e identificadores de Meta."
        actions={
          <StatusBadge tone={healthy ? 'success' : 'neutral'}>
            {healthy ? 'Conectado' : health?.status || 'Sin health check'}
          </StatusBadge>
        }
      />

      {checks.delivery_ready === false ? (
        <AlertBanner
          tone="warning"
          title="El canal está en modo real pero el secreto meta_access_token del tenant falta o no es real."
          description="Pega el Meta access token, el App Secret y el Verify token, guarda el canal y reinicia el worker antes de esperar mensajes en WhatsApp."
        />
      ) : null}

      <dl className={styles.healthGrid}>
        {rows.map(([label, value]) => (
          <div key={label} className={styles.healthRow}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
