import { Link } from 'react-router-dom';

import { Card, CardHeader, KpiTile, StatusBadge } from '../../../../components/ui/index.js';
import { ContactCard, TagPill } from '../../../../components/domain/index.js';
import { formatDateShort } from '../../../owner-admin/conversations-contacts/index.js';
import {
  consentStatusLabel,
  contactInitials,
  notesCount,
  summaryStats,
} from '../contactProfileData.js';
import styles from '../ContactProfile.module.css';

/**
 * Focused contact-profile header (UI-009.3).
 *
 * Reuses the `ContactCard` domain component for the canonical identity row and
 * adds the focused-view chrome around it: a back link to the Contactos module,
 * the avatar/initials block, identity fields and the headline KPIs derived from
 * the `getContactProfile` `stats` block.
 *
 * @param {{
 *   profile: object,
 *   consent: object|null,
 *   tenantSlug: string,
 * }} props
 */
export function ContactProfileHeader({ profile, consent, tenantSlug }) {
  const contact = profile?.contact || {};
  const tags = profile?.tags || [];
  const stats = summaryStats(profile?.stats);
  const consentLabel = consentStatusLabel(profile, consent);

  return (
    <Card padding="md">
      <div className={styles.backRow}>
        <Link to={`/t/${tenantSlug}/contacts`} className={styles.backLink}>
          ← Volver a Contactos
        </Link>
      </div>

      <div className={styles.identity}>
        <span className={styles.avatar} aria-hidden="true">
          {contactInitials(contact)}
        </span>
        <div className={styles.identityBody}>
          <h2 className={styles.identityName}>
            {contact.display_name || contact.phone_e164 || contact.wa_id || 'Contacto'}
          </h2>
          <div className={styles.identityMeta}>
            {contact.phone_e164 ? <span>{contact.phone_e164}</span> : null}
            <StatusBadge tone={consentLabel === 'opted_in' ? 'success' : 'neutral'}>
              Consent: {consentLabel}
            </StatusBadge>
          </div>
          {tags.length > 0 ? (
            <div className={styles.tagRow}>
              {tags.map((tag) => (
                <TagPill key={tag.id} tag={tag} size="sm" />
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <dl className={styles.fieldGrid}>
        <div>
          <dt>Idioma</dt>
          <dd>{contact.language || '—'}</dd>
        </div>
        <div>
          <dt>WhatsApp ID</dt>
          <dd>{contact.wa_id || '—'}</dd>
        </div>
        <div>
          <dt>Primer contacto</dt>
          <dd>{formatDateShort(contact.created_at)}</dd>
        </div>
        <div>
          <dt>Notas internas</dt>
          <dd>{notesCount(profile)}</dd>
        </div>
      </dl>

      <CardHeader title="Valor del cliente" />
      <div className={styles.kpiGrid}>
        {stats.map((stat) => (
          <KpiTile key={stat.key} label={stat.label} value={stat.value} />
        ))}
      </div>

      {/* `ContactCard` domain component reused for the canonical identity row;
          non-interactive here since the focused view is the contact itself. */}
      <div className={styles.contactCardWrap} data-testid="contact-profile-identity-card">
        <ContactCard contact={{ ...contact, tags }} />
      </div>
    </Card>
  );
}
