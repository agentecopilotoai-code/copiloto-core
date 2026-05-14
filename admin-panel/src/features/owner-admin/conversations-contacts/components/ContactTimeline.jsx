import { Card, CardHeader, StatusBadge } from '../../../../components/ui/index.js';
import { AppointmentCard, TimelineEntry } from '../../../../components/domain/index.js';
import { formatDate, formatDateShort } from '../contactsFormat.js';
import styles from '../ConversationsContacts.module.css';

/**
 * Read-only history timeline of the contact drawer: recent appointments,
 * conversations, referrals and the consent ledger. Presentational — driven by
 * the `profile` and `consent` payloads from the data hook.
 *
 * @param {{ profile: object, consent: object|null }} props
 */
export function ContactTimeline({ profile, consent }) {
  const appointments = profile?.appointments || [];
  const conversations = profile?.conversations || [];
  const referrals = profile?.referrals || {};
  const consentItems = consent?.items || [];
  const consentStatus =
    consent?.contact?.opt_in_status || profile?.contact?.opt_in_status || '—';

  return (
    <Card padding="md">
      <CardHeader title="Historial" subtitle="Citas, conversaciones, referidos y consentimiento" />

      <h4 className={styles.sectionTitle}>Últimas citas</h4>
      {appointments.length > 0 ? (
        <div className={styles.appointmentList}>
          {appointments.map((appointment) => (
            <AppointmentCard
              key={appointment.id}
              appointment={appointment}
              dateText={formatDate(appointment.starts_at)}
            />
          ))}
        </div>
      ) : (
        <p className={styles.muted}>Sin citas registradas.</p>
      )}

      <h4 className={styles.sectionTitle}>Últimas conversaciones</h4>
      {conversations.length > 0 ? (
        <ul className={styles.timelineList}>
          {conversations.map((conversation) => (
            <TimelineEntry
              key={conversation.id}
              title={`${conversation.status} · ${conversation.message_count || 0} mensajes`}
              meta={`${formatDate(conversation.updated_at)}${
                conversation.current_intent ? ` · ${conversation.current_intent}` : ''
              }`}
            />
          ))}
        </ul>
      ) : (
        <p className={styles.muted}>Sin conversaciones todavía.</p>
      )}

      <div data-testid="contact-referrals-panel">
        <h4 className={styles.sectionTitle}>Referidos</h4>
        {referrals.referred_by ? (
          <p className={styles.muted}>
            Le recomendó este negocio:{' '}
            <strong>
              {referrals.referred_by.display_name ||
                referrals.referred_by.phone_e164 ||
                referrals.referred_by.contact_id}
            </strong>
          </p>
        ) : (
          <p className={styles.muted}>Sin referidor registrado.</p>
        )}
        {referrals.referred_contacts?.length ? (
          <ul className={styles.timelineList}>
            {referrals.referred_contacts.map((ref) => (
              <TimelineEntry
                key={ref.contact_id}
                title={ref.display_name || ref.phone_e164 || '—'}
                meta={`${formatDateShort(ref.created_at)}${ref.phone_e164 ? ` · ${ref.phone_e164}` : ''}`}
              />
            ))}
          </ul>
        ) : null}
      </div>

      <div data-testid="contact-consent-panel">
        <h4 className={styles.sectionTitle}>Consentimiento (Ley 1581 / GDPR)</h4>
        <p className={styles.muted}>
          Estado actual: <strong>{consentStatus}</strong>
          {consent?.contact?.opt_in_at
            ? ` · concedido ${formatDate(consent.contact.opt_in_at)}`
            : ''}
          {consent?.contact?.opt_out_at
            ? ` · revocado ${formatDate(consent.contact.opt_out_at)}`
            : ''}
        </p>
        {consentItems.length > 0 ? (
          <ul className={styles.timelineList}>
            {consentItems.map((evt) => (
              <TimelineEntry
                key={evt.id}
                badge={
                  <StatusBadge tone={evt.event === 'opt_out' ? 'danger' : 'success'}>
                    {evt.event}
                  </StatusBadge>
                }
                title={`canal: ${evt.channel}`}
                meta={`${formatDate(evt.occurred_at)}${evt.legal_basis ? ` · ${evt.legal_basis}` : ''}`}
              >
                {evt.copy_shown ? <span>«{evt.copy_shown.slice(0, 240)}»</span> : null}
              </TimelineEntry>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>Aún no hay eventos registrados de consentimiento.</p>
        )}
      </div>
    </Card>
  );
}
