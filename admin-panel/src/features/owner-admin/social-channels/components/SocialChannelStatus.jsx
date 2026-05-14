import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { channelRecipientId, providerMeta, statusLabel, statusTone } from '../socialChannelsData.js';
import styles from '../SocialChannelsModule.module.css';

/**
 * Current-state panel for the active social channel. Shows the identifiers and
 * the per-secret configuration checks returned by `listMessengerChannels`.
 * Presentational — the `channel` record comes from the `useSocialChannelsData`
 * hook.
 *
 * @param {{ channel: object | null, providerId: string }} props
 */
export function SocialChannelStatus({ channel, providerId }) {
  const meta = providerMeta(providerId);

  if (!channel) {
    return (
      <Card padding="md">
        <CardHeader title={`Identificadores Meta · ${meta?.label || ''}`.trim()} />
        <EmptyState
          title="Sin configurar"
          description="Aún no se ha configurado este canal. Completa el formulario para activarlo."
        />
      </Card>
    );
  }

  const rows = [
    ['Estado', <StatusBadge key="s" tone={statusTone(channel)}>{statusLabel(channel)}</StatusBadge>],
    [meta?.recipientLabel || 'Identificador', channelRecipientId(channel)],
    ['Business ID', channel.business_id || '—'],
    ['Account mode', channel.account_mode || '—'],
    ['Ventana de servicio', `${channel.service_window_hours ?? 24}h`],
    ['Token configurado', channel.token_configured ? 'sí' : 'no'],
    ['App secret configurado', channel.app_secret_configured ? 'sí' : 'no'],
    ['Verify token configurado', channel.verify_token_configured ? 'sí' : 'no'],
  ];

  return (
    <Card padding="md">
      <CardHeader title={`Identificadores Meta · ${meta?.label || ''}`.trim()} />
      <dl className={styles.statusGrid}>
        {rows.map(([label, value]) => (
          <div key={label} className={styles.statusRow}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
