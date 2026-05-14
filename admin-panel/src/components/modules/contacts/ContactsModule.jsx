import { useEffect, useMemo, useState } from 'react';

import { StatusBadge } from '../../ui/StatusBadge.jsx';
import {
  AppointmentCard,
  ContactCard,
  TagPill,
  TimelineEntry,
} from '../../domain/index.js';
import {
  assignContactPackage,
  assignContactTags,
  createContactNote,
  getContactProfile,
  listContactConsent,
  listContactPackages,
  listContactTags,
  listContacts,
  listTreatmentPackages,
  refundContactPackage,
  unassignContactTag,
  updateContactPhone,
} from '../../../services/coreApi.js';

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatDateShort(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' }).format(new Date(value));
  } catch {
    return value;
  }
}

export function ContactsModule({ module, session, tenant }) {
  const [contacts, setContacts] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTagId, setFilterTagId] = useState('');
  const [selectedContactId, setSelectedContactId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [pendingTagId, setPendingTagId] = useState('');
  const [contactPackages, setContactPackages] = useState([]);
  const [availablePackages, setAvailablePackages] = useState([]);
  const [pendingPackageId, setPendingPackageId] = useState('');
  const [consent, setConsent] = useState(null);
  const [phoneEditOpen, setPhoneEditOpen] = useState(false);
  const [phoneDraft, setPhoneDraft] = useState('');
  const [phoneReason, setPhoneReason] = useState('');

  const tenantId = tenant?.id;

  function refreshContacts() {
    if (!tenantId) return Promise.resolve();
    return listContacts(session, tenantId, {
      q: searchTerm || undefined,
      tagId: filterTagId || undefined,
      limit: 100,
    })
      .then((items) => {
        setContacts(items || []);
        if (items?.length && !items.some((c) => c.id === selectedContactId)) {
          setSelectedContactId(items[0].id);
        } else if (!items?.length) {
          setSelectedContactId(null);
          setProfile(null);
        }
      })
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshTags() {
    if (!tenantId) return Promise.resolve();
    return listContactTags(session, tenantId)
      .then((items) => setAvailableTags(items || []))
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshProfile(contactId = selectedContactId) {
    if (!tenantId || !contactId) {
      setProfile(null);
      return Promise.resolve();
    }
    return getContactProfile(session, tenantId, contactId)
      .then(setProfile)
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshContactPackages(contactId = selectedContactId) {
    if (!tenantId || !contactId) {
      setContactPackages([]);
      return Promise.resolve();
    }
    return listContactPackages(session, tenantId, contactId)
      .then((items) => setContactPackages(Array.isArray(items) ? items : []))
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshConsent(contactId = selectedContactId) {
    if (!tenantId || !contactId) {
      setConsent(null);
      return Promise.resolve();
    }
    return listContactConsent(session, tenantId, contactId, { limit: 100 })
      .then(setConsent)
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshAvailablePackages() {
    if (!tenantId) return Promise.resolve();
    return listTreatmentPackages(session, tenantId, { is_active: true })
      .then((items) => setAvailablePackages(Array.isArray(items) ? items : []))
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  useEffect(() => {
    if (!tenantId) return;
    refreshTags();
    refreshContacts();
    refreshAvailablePackages();
  }, [tenantId]);

  useEffect(() => {
    if (selectedContactId) {
      refreshProfile(selectedContactId);
      refreshContactPackages(selectedContactId);
      refreshConsent(selectedContactId);
    } else {
      setConsent(null);
    }
  }, [selectedContactId]);

  function handleSearch(event) {
    event.preventDefault();
    refreshContacts();
  }

  async function handleAssignTag(event) {
    event.preventDefault();
    if (!pendingTagId || !selectedContactId) return;
    setIsBusy(true);
    try {
      await assignContactTags(session, tenantId, selectedContactId, [pendingTagId]);
      setPendingTagId('');
      setNotice({ type: 'success', text: 'Etiqueta asignada.' });
      await Promise.all([refreshProfile(), refreshContacts()]);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRemoveTag(tagId) {
    if (!selectedContactId) return;
    setIsBusy(true);
    try {
      await unassignContactTag(session, tenantId, selectedContactId, tagId);
      setNotice({ type: 'success', text: 'Etiqueta retirada.' });
      await Promise.all([refreshProfile(), refreshContacts()]);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAssignPackage(event) {
    event.preventDefault();
    if (!pendingPackageId || !selectedContactId) return;
    setIsBusy(true);
    try {
      await assignContactPackage(session, tenantId, selectedContactId, {
        package_id: pendingPackageId,
        payment_status: 'pending',
      });
      setPendingPackageId('');
      setNotice({ type: 'success', text: 'Paquete asignado.' });
      await refreshContactPackages();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRefundPackage(contactPackageId) {
    if (!selectedContactId) return;
    if (!window.confirm('¿Reembolsar este paquete? Se marcará como refunded.')) return;
    setIsBusy(true);
    try {
      await refundContactPackage(session, tenantId, selectedContactId, contactPackageId);
      setNotice({ type: 'success', text: 'Paquete reembolsado.' });
      await refreshContactPackages();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleUpdatePhone(event) {
    event.preventDefault();
    if (!selectedContactId) return;
    const trimmed = phoneDraft.trim();
    if (!trimmed) {
      setNotice({ type: 'error', text: 'El nuevo teléfono es obligatorio.' });
      return;
    }
    setIsBusy(true);
    try {
      await updateContactPhone(session, tenantId, selectedContactId, {
        phone_e164: trimmed,
        reason: phoneReason.trim() || undefined,
      });
      setNotice({ type: 'success', text: 'Teléfono actualizado y registrado en audit_logs.' });
      setPhoneEditOpen(false);
      setPhoneDraft('');
      setPhoneReason('');
      await refreshProfile();
      await refreshContacts();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateNote(event) {
    event.preventDefault();
    if (!noteDraft.trim() || !selectedContactId) return;
    setIsBusy(true);
    try {
      await createContactNote(session, tenantId, selectedContactId, noteDraft.trim());
      setNoteDraft('');
      setNotice({ type: 'success', text: 'Nota interna agregada.' });
      await refreshProfile();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  const unassignedTags = useMemo(() => {
    const assignedIds = new Set((profile?.tags || []).map((t) => t.id));
    return availableTags.filter((tag) => !assignedIds.has(tag.id));
  }, [availableTags, profile?.tags]);

  if (!tenantId) {
    return (
      <section className="module-card">
        <div className="module-heading">
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <p className="hint">Selecciona un tenant para ver sus contactos.</p>
      </section>
    );
  }

  return (
    <section className="module-card contacts-module">
      <div className="module-heading">
        <div>
          <p className="eyebrow">CRM</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      <form className="form-grid" onSubmit={handleSearch} style={{ alignItems: 'end' }}>
        <label>
          Buscar
          <input
            placeholder="Nombre o teléfono"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </label>
        <label>
          Filtrar por etiqueta
          <select value={filterTagId} onChange={(event) => setFilterTagId(event.target.value)}>
            <option value="">Todas</option>
            {availableTags.map((tag) => (
              <option key={tag.id} value={tag.id}>{tag.name}</option>
            ))}
          </select>
        </label>
        <div className="form-actions">
          <button className="secondary-action" type="submit" disabled={isBusy}>
            Aplicar filtros
          </button>
        </div>
      </form>

      <div className="operations-layout" style={{ marginTop: '1rem' }}>
        <aside className="conversation-list" aria-label="Contactos">
          {contacts.length === 0 ? (
            <p className="hint">No hay contactos para este filtro.</p>
          ) : null}
          {contacts.map((contact) => (
            <ContactCard
              key={contact.id}
              contact={contact}
              selected={contact.id === selectedContactId}
              onSelect={() => setSelectedContactId(contact.id)}
            />
          ))}
        </aside>

        <section className="conversation-detail">
          {!profile ? (
            <div className="empty-detail">
              <h3>Selecciona un contacto</h3>
              <p className="hint">Verás historial de citas, conversaciones, calificaciones y notas internas.</p>
            </div>
          ) : (
            <>
              <div className="detail-header">
                <div>
                  <p className="eyebrow">Contacto</p>
                  <h3>{profile.contact.display_name || profile.contact.phone_e164 || profile.contact.wa_id}</h3>
                  <p className="hint">
                    {profile.contact.phone_e164}{' '}
                    <button
                      type="button"
                      className="link-action"
                      onClick={() => {
                        setPhoneDraft(profile.contact.phone_e164 || '');
                        setPhoneReason('');
                        setPhoneEditOpen(true);
                      }}
                      style={{ marginLeft: '0.5rem' }}
                    >
                      Cambiar teléfono
                    </button>
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
                  {(profile.tags || []).map((tag) => (
                    <TagPill tag={tag} key={tag.id} onRemove={() => handleRemoveTag(tag.id)} disabled={isBusy} />
                  ))}
                </div>
              </div>

              {phoneEditOpen && (
                <form className="form-grid" onSubmit={handleUpdatePhone}>
                  <label>
                    Nuevo teléfono (E.164)
                    <input
                      onChange={(event) => setPhoneDraft(event.target.value)}
                      placeholder="+573001234567"
                      required
                      value={phoneDraft}
                    />
                    <small className="hint">
                      Requiere rol <strong>manager</strong> o superior. La
                      operación queda registrada en <code>audit_logs</code>
                      (<code>contact.phone_changed</code>). Si otro contacto del
                      tenant ya tiene este número, el servidor responde 409.
                    </small>
                  </label>
                  <label>
                    Razón (opcional, queda en el audit)
                    <input
                      onChange={(event) => setPhoneReason(event.target.value)}
                      placeholder="Cliente cambió de número"
                      value={phoneReason}
                    />
                  </label>
                  <div className="form-actions">
                    <button className="primary-action" type="submit" disabled={isBusy}>
                      Guardar nuevo teléfono
                    </button>
                    <button
                      className="secondary-action"
                      type="button"
                      onClick={() => {
                        setPhoneEditOpen(false);
                        setPhoneDraft('');
                        setPhoneReason('');
                      }}
                    >
                      Cancelar
                    </button>
                  </div>
                </form>
              )}

              <form className="form-grid" onSubmit={handleAssignTag}>
                <label>
                  Asignar etiqueta
                  <select value={pendingTagId} onChange={(event) => setPendingTagId(event.target.value)}>
                    <option value="">— Selecciona —</option>
                    {unassignedTags.map((tag) => (
                      <option key={tag.id} value={tag.id}>{tag.name}</option>
                    ))}
                  </select>
                </label>
                <div className="form-actions">
                  <button className="secondary-action" type="submit" disabled={!pendingTagId || isBusy}>
                    Asignar
                  </button>
                </div>
              </form>

              <div className="schedule-panel">
                <div>
                  <strong>Resumen</strong>
                  <ul className="hint" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                    <li>Citas totales: <strong>{profile.stats?.total_appointments ?? 0}</strong></li>
                    <li>Completadas: <strong>{profile.stats?.completed_appointments ?? 0}</strong></li>
                    <li>Primera visita: <strong>{formatDateShort(profile.stats?.first_visit_at)}</strong></li>
                    <li>Última visita: <strong>{formatDateShort(profile.stats?.last_visit_at)}</strong></li>
                    <li>Calificación promedio: <strong>
                      {profile.stats?.average_rating != null ? `${profile.stats.average_rating.toFixed(2)} ★ (${profile.stats.ratings_count || 0})` : '—'}
                    </strong></li>
                  </ul>
                </div>
              </div>

              {profile.qualification_questions?.length ? (
                <div className="schedule-panel">
                  <div>
                    <strong>Calificación</strong>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {profile.qualification_questions.map((question) => {
                        const raw = profile.qualification_answers?.[question.id];
                        let display = '—';
                        if (question.kind === 'yes_no') {
                          if (raw === true) display = 'Sí';
                          else if (raw === false) display = 'No';
                        } else if (
                          question.kind === 'single_choice'
                          || question.kind === 'multi_choice'
                        ) {
                          const opts = Array.isArray(question.options) ? question.options : [];
                          const lookup = (val) => {
                            const found = opts.find((o) => o.value === val);
                            return found?.label || val;
                          };
                          if (Array.isArray(raw)) {
                            display = raw.map(lookup).join(', ') || '—';
                          } else if (typeof raw === 'string') {
                            display = lookup(raw);
                          }
                        } else if (raw != null && raw !== '') {
                          display = String(raw);
                        }
                        return (
                          <li key={question.id} style={{ padding: '0.3rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                            <div className="hint" style={{ fontSize: '0.8rem' }}>{question.label}</div>
                            <strong>{display}</strong>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              ) : null}

              <div className="schedule-panel">
                <div>
                  <strong>Últimas citas</strong>
                  {profile.appointments?.length ? (
                    <div>
                      {profile.appointments.map((appointment) => (
                        <AppointmentCard
                          key={appointment.id}
                          appointment={appointment}
                          dateText={formatDate(appointment.starts_at)}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="hint">Sin citas registradas.</p>
                  )}
                </div>
              </div>

              <div className="schedule-panel">
                <div>
                  <strong>Últimas conversaciones</strong>
                  {profile.conversations?.length ? (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {profile.conversations.map((conversation) => (
                        <TimelineEntry
                          key={conversation.id}
                          title={`${conversation.status} · ${conversation.message_count || 0} mensajes`}
                          meta={`${formatDate(conversation.updated_at)}${conversation.current_intent ? ` · ${conversation.current_intent}` : ''}`}
                        />
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Sin conversaciones todavía.</p>
                  )}
                </div>
              </div>

              <div className="schedule-panel" data-testid="contact-referrals-panel">
                <div>
                  <strong>Referidos</strong>
                  {profile.referrals?.referred_by ? (
                    <p className="hint" style={{ marginTop: '0.4rem' }}>
                      Le recomendó este negocio:{' '}
                      <strong>
                        {profile.referrals.referred_by.display_name
                          || profile.referrals.referred_by.phone_e164
                          || profile.referrals.referred_by.contact_id}
                      </strong>
                    </p>
                  ) : (
                    <p className="hint" style={{ marginTop: '0.4rem' }}>
                      Sin referidor registrado.
                    </p>
                  )}
                  {profile.referrals?.referred_contacts?.length ? (
                    <>
                      <p
                        className="hint"
                        style={{ marginTop: '0.6rem', fontWeight: 600 }}
                      >
                        Personas que recomendó ({profile.referrals.referred_contacts.length})
                      </p>
                      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                        {profile.referrals.referred_contacts.map((ref) => (
                          <TimelineEntry
                            key={ref.contact_id}
                            title={ref.display_name || ref.phone_e164 || '—'}
                            meta={`${formatDateShort(ref.created_at)}${ref.phone_e164 ? ` · ${ref.phone_e164}` : ''}`}
                          />
                        ))}
                      </ul>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="schedule-panel" data-testid="contact-packages-panel">
                <div>
                  <strong>Paquetes activos</strong>
                  <p className="hint" style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
                    Asignar y reembolsar requieren rol <strong>admin</strong> u
                    <strong> owner</strong>. El estado de pago
                    (<code>paid</code>, <code>failed</code>, <code>refunded</code>)
                    solo lo escribe el webhook firmado del proveedor.
                  </p>
                  <form onSubmit={handleAssignPackage} style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                    <select
                      value={pendingPackageId}
                      onChange={(event) => setPendingPackageId(event.target.value)}
                      style={{ flex: 1 }}
                      disabled={isBusy || availablePackages.length === 0}
                    >
                      <option value="">— Asignar paquete —</option>
                      {availablePackages.map((pkg) => (
                        <option key={pkg.id} value={pkg.id}>
                          {pkg.name} ({pkg.total_sessions} sesiones · {pkg.price_amount} {pkg.price_currency})
                        </option>
                      ))}
                    </select>
                    <button className="primary-action" type="submit" disabled={!pendingPackageId || isBusy}>
                      Asignar
                    </button>
                  </form>
                  {contactPackages.length ? (
                    <ul style={{ listStyle: 'none', padding: 0, marginTop: '0.5rem' }}>
                      {contactPackages.map((pkg) => (
                        <TimelineEntry
                          key={pkg.id}
                          title={pkg.package_name || pkg.name}
                          badge={(
                            <StatusBadge tone={pkg.status === 'active' ? 'success' : 'neutral'}>
                              {pkg.status}
                            </StatusBadge>
                          )}
                          meta={`${pkg.remaining_sessions} / ${pkg.total_sessions} sesiones restantes · pago: ${pkg.payment_status}${pkg.expires_at ? ` · vence ${formatDateShort(pkg.expires_at)}` : ''}`}
                        >
                          {pkg.status === 'active' ? (
                            <button
                              type="button"
                              onClick={() => handleRefundPackage(pkg.id)}
                              disabled={isBusy}
                              style={{ marginTop: '0.35rem' }}
                            >
                              Reembolsar
                            </button>
                          ) : null}
                        </TimelineEntry>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Sin paquetes asignados.</p>
                  )}
                </div>
              </div>

              <div className="schedule-panel" data-testid="contact-consent-panel">
                <div>
                  <strong>Consentimiento (Ley 1581 / GDPR)</strong>
                  <p className="hint" style={{ marginTop: '0.3rem' }}>
                    Estado actual:{' '}
                    <strong>{consent?.contact?.opt_in_status || profile.contact.opt_in_status || '—'}</strong>
                    {consent?.contact?.opt_in_at
                      ? ` · concedido ${formatDate(consent.contact.opt_in_at)}`
                      : ''}
                    {consent?.contact?.opt_out_at
                      ? ` · revocado ${formatDate(consent.contact.opt_out_at)}`
                      : ''}
                  </p>
                  {consent?.items?.length ? (
                    <ul style={{ listStyle: 'none', padding: 0, marginTop: '0.5rem' }}>
                      {consent.items.map((evt) => (
                        <TimelineEntry
                          key={evt.id}
                          badge={(
                            <StatusBadge tone={evt.event === 'opt_out' ? 'danger' : 'success'}>
                              {evt.event}
                            </StatusBadge>
                          )}
                          title={`canal: ${evt.channel}`}
                          meta={`${formatDate(evt.occurred_at)}${evt.legal_basis ? ` · ${evt.legal_basis}` : ''}`}
                        >
                          {evt.copy_shown ? <span>«{evt.copy_shown.slice(0, 240)}»</span> : null}
                        </TimelineEntry>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Aún no hay eventos registrados de consentimiento.</p>
                  )}
                </div>
              </div>

              <div className="schedule-panel">
                <div>
                  <strong>Notas internas</strong>
                  <form onSubmit={handleCreateNote} style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                    <textarea
                      placeholder="Agrega una nota visible solo para el equipo"
                      value={noteDraft}
                      onChange={(event) => setNoteDraft(event.target.value)}
                      rows={2}
                      style={{ flex: 1 }}
                    />
                    <button className="primary-action" type="submit" disabled={!noteDraft.trim() || isBusy}>
                      Guardar nota
                    </button>
                  </form>
                  {profile.notes?.length ? (
                    <ul style={{ listStyle: 'none', padding: 0, marginTop: '0.5rem' }}>
                      {profile.notes.map((note) => (
                        <TimelineEntry
                          key={note.id}
                          meta={`${note.created_by_name || 'Equipo'} · ${formatDate(note.created_at)}`}
                        >
                          {note.body}
                        </TimelineEntry>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Sin notas todavía.</p>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
