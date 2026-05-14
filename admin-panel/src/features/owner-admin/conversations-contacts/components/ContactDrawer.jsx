import { useState } from 'react';

import { Card, CardHeader, EmptyState, FormField } from '../../../../components/ui/index.js';
import { formatDateShort, renderQualificationAnswer } from '../contactsFormat.js';
import { ContactTagsPanel } from './ContactTagsPanel.jsx';
import { ContactPackagesPanel } from './ContactPackagesPanel.jsx';
import { ContactTimeline } from './ContactTimeline.jsx';
import { ContactNotesPanel } from './ContactNotesPanel.jsx';
import styles from '../ConversationsContacts.module.css';

function ContactSummary({ stats }) {
  const s = stats || {};
  const rating =
    s.average_rating != null
      ? `${s.average_rating.toFixed(2)} ★ (${s.ratings_count || 0})`
      : '—';
  return (
    <Card padding="md">
      <CardHeader title="Resumen" />
      <dl className={styles.summaryGrid}>
        <div><dt>Citas totales</dt><dd>{s.total_appointments ?? 0}</dd></div>
        <div><dt>Completadas</dt><dd>{s.completed_appointments ?? 0}</dd></div>
        <div><dt>Primera visita</dt><dd>{formatDateShort(s.first_visit_at)}</dd></div>
        <div><dt>Última visita</dt><dd>{formatDateShort(s.last_visit_at)}</dd></div>
        <div><dt>Calificación promedio</dt><dd>{rating}</dd></div>
      </dl>
    </Card>
  );
}

/**
 * Right column of the Contactos view: the selected contact's detail drawer.
 * Owns only the phone-edit local form state; everything else is composed from
 * the split panels and driven by the data hook's `actions`.
 *
 * @param {{
 *   profile: object|null,
 *   consent: object|null,
 *   unassignedTags: Array<object>,
 *   contactPackages: Array<object>,
 *   availablePackages: Array<object>,
 *   isBusy: boolean,
 *   actions: object,
 * }} props
 */
export function ContactDrawer({
  profile,
  consent,
  unassignedTags,
  contactPackages,
  availablePackages,
  isBusy,
  actions,
}) {
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [phoneDraft, setPhoneDraft] = useState('');
  const [phoneReason, setPhoneReason] = useState('');

  if (!profile) {
    return (
      <Card padding="md">
        <EmptyState
          title="Selecciona un contacto"
          description="Verás historial de citas, conversaciones, calificaciones, paquetes y notas internas."
        />
      </Card>
    );
  }

  const contact = profile.contact || {};
  const questions = profile.qualification_questions || [];

  function openPhoneEdit() {
    setPhoneDraft(contact.phone_e164 || '');
    setPhoneReason('');
    setPhoneOpen(true);
  }

  function submitPhone(event) {
    event.preventDefault();
    const trimmed = phoneDraft.trim();
    if (!trimmed) return;
    actions.updatePhone(trimmed, phoneReason.trim());
    setPhoneOpen(false);
  }

  return (
    <div className={styles.drawer}>
      <Card padding="md">
        <div className={styles.drawerHead}>
          <div>
            <span className={styles.eyebrow}>Contacto</span>
            <h3 className={styles.contactName}>
              {contact.display_name || contact.phone_e164 || contact.wa_id}
            </h3>
            <p className={styles.contactPhone}>
              {contact.phone_e164}
              <button type="button" className={styles.linkButton} onClick={openPhoneEdit}>
                Cambiar teléfono
              </button>
            </p>
          </div>
        </div>
        {phoneOpen ? (
          <form className={styles.phoneForm} onSubmit={submitPhone}>
            <FormField
              label="Nuevo teléfono (E.164)"
              hint="Requiere rol manager o superior. Queda en audit_logs (contact.phone_changed). Si otro contacto del tenant ya tiene el número, el servidor responde 409."
            >
              <input
                type="text"
                value={phoneDraft}
                onChange={(event) => setPhoneDraft(event.target.value)}
                placeholder="+573001234567"
                required
              />
            </FormField>
            <FormField label="Razón (opcional, queda en el audit)">
              <input
                type="text"
                value={phoneReason}
                onChange={(event) => setPhoneReason(event.target.value)}
                placeholder="Cliente cambió de número"
              />
            </FormField>
            <div className={styles.formActions}>
              <button type="submit" className={styles.primaryButton} disabled={isBusy}>
                Guardar
              </button>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => setPhoneOpen(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        ) : null}
      </Card>

      <ContactTagsPanel
        tags={profile.tags || []}
        unassignedTags={unassignedTags}
        isBusy={isBusy}
        onAssign={actions.assignTag}
        onRemove={actions.removeTag}
      />

      <ContactSummary stats={profile.stats} />

      {questions.length > 0 ? (
        <Card padding="md">
          <CardHeader title="Calificación" />
          <dl className={styles.summaryGrid}>
            {questions.map((question) => (
              <div key={question.id}>
                <dt>{question.label}</dt>
                <dd>
                  {renderQualificationAnswer(
                    question,
                    profile.qualification_answers?.[question.id],
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : null}

      <ContactPackagesPanel
        contactPackages={contactPackages}
        availablePackages={availablePackages}
        isBusy={isBusy}
        onAssign={actions.assignPackage}
        onRefund={actions.refundPackage}
      />

      <ContactTimeline profile={profile} consent={consent} />

      <ContactNotesPanel notes={profile.notes || []} isBusy={isBusy} onCreate={actions.createNote} />
    </div>
  );
}
