import { useState } from 'react';

import { Card, CardHeader, StatusBadge, useConfirm } from '../../../../components/ui/index.js';
import { TimelineEntry } from '../../../../components/domain/index.js';
import { formatDateShort } from '../contactsFormat.js';
import styles from '../ConversationsContacts.module.css';

/**
 * Treatment-packages panel of the contact drawer: the "assign package" form and
 * the list of the contact's packages with a refund action. Presentational —
 * `onAssign` / `onRefund` come from the data hook.
 *
 * Payment status (`paid` / `failed` / `refunded`) is only ever written by the
 * provider's signed webhook (TASK-0051); this panel just displays it.
 *
 * @param {{
 *   contactPackages: Array<object>,
 *   availablePackages: Array<object>,
 *   isBusy: boolean,
 *   onAssign: (packageId: string) => void,
 *   onRefund: (contactPackageId: string) => void,
 * }} props
 */
export function ContactPackagesPanel({
  contactPackages,
  availablePackages,
  isBusy,
  onAssign,
  onRefund,
}) {
  const [pendingPackageId, setPendingPackageId] = useState('');
  // BUG-115: el legacy ContactsModule pedía confirmación antes del refund
  // (acción irreversible que toca pagos). El feature redesign lo perdió y
  // disparaba el refund directo sin confirm — regresión vs spec original.
  const confirm = useConfirm();

  function handleAssign(event) {
    event.preventDefault();
    if (!pendingPackageId) return;
    onAssign(pendingPackageId);
    setPendingPackageId('');
  }

  async function handleRefund(packageId, packageName) {
    const ok = await confirm({
      title: 'Reembolsar paquete',
      body: `¿Reembolsar el paquete${packageName ? ` "${packageName}"` : ''}? Esta acción es irreversible y afecta al pago.`,
      danger: true,
      confirmLabel: 'Reembolsar',
    });
    if (!ok) return;
    onRefund(packageId);
  }

  return (
    <Card padding="md" data-testid="contact-packages-panel">
      <CardHeader
        title="Paquetes"
        subtitle="Asignar y reembolsar requieren rol admin u owner"
      />
      <form className={styles.inlineForm} onSubmit={handleAssign}>
        <select
          value={pendingPackageId}
          onChange={(event) => setPendingPackageId(event.target.value)}
          disabled={isBusy || availablePackages.length === 0}
        >
          <option value="">— Asignar paquete —</option>
          {availablePackages.map((pkg) => (
            <option key={pkg.id} value={pkg.id}>
              {pkg.name} ({pkg.total_sessions} sesiones · {pkg.price_amount} {pkg.price_currency})
            </option>
          ))}
        </select>
        <button
          type="submit"
          className={styles.primaryButton}
          disabled={!pendingPackageId || isBusy}
        >
          Asignar
        </button>
      </form>
      {contactPackages && contactPackages.length > 0 ? (
        <ul className={styles.timelineList}>
          {contactPackages.map((pkg) => (
            <TimelineEntry
              key={pkg.id}
              title={pkg.package_name || pkg.name}
              badge={
                <StatusBadge tone={pkg.status === 'active' ? 'success' : 'neutral'}>
                  {pkg.status}
                </StatusBadge>
              }
              meta={`${pkg.remaining_sessions} / ${pkg.total_sessions} sesiones · pago: ${pkg.payment_status}${
                pkg.expires_at ? ` · vence ${formatDateShort(pkg.expires_at)}` : ''
              }`}
            >
              {pkg.status === 'active' ? (
                <button
                  type="button"
                  className={styles.linkButton}
                  onClick={() => handleRefund(pkg.id, pkg.package_name || pkg.name)}
                  disabled={isBusy}
                >
                  Reembolsar
                </button>
              ) : null}
            </TimelineEntry>
          ))}
        </ul>
      ) : (
        <p className={styles.muted}>Sin paquetes asignados.</p>
      )}
    </Card>
  );
}
