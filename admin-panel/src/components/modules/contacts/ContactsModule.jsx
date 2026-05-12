import { useEffect, useMemo, useState } from 'react';

import {
  assignContactPackage,
  assignContactTags,
  createContactNote,
  getContactProfile,
  listContactPackages,
  listContactTags,
  listContacts,
  listTreatmentPackages,
  refundContactPackage,
  unassignContactTag,
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

function TagChip({ tag, onRemove }) {
  const background = tag.color || '#4f6ef7';
  return (
    <span
      className="status-pill"
      style={{
        background,
        color: '#fff',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.35rem',
        padding: '0.15rem 0.6rem',
        fontSize: '0.75rem',
      }}
    >
      {tag.name}
      {onRemove ? (
        <button
          type="button"
          aria-label={`Quitar etiqueta ${tag.name}`}
          onClick={onRemove}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '0.9rem',
            padding: 0,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      ) : null}
    </span>
  );
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
            <button
              className={`conversation-card ${contact.id === selectedContactId ? 'active' : ''}`}
              key={contact.id}
              onClick={() => setSelectedContactId(contact.id)}
              type="button"
            >
              <span>{contact.display_name || contact.phone_e164 || contact.wa_id}</span>
              <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                {(contact.tags || []).map((tag) => (
                  <TagChip tag={tag} key={tag.id} />
                ))}
              </div>
              <small>{contact.phone_e164}</small>
              <small>{contact.appointments_count || 0} citas</small>
            </button>
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
                  <p className="hint">{profile.contact.phone_e164}</p>
                </div>
                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
                  {(profile.tags || []).map((tag) => (
                    <TagChip tag={tag} key={tag.id} onRemove={() => handleRemoveTag(tag.id)} />
                  ))}
                </div>
              </div>

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
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {profile.appointments.map((appointment) => (
                        <li key={appointment.id} style={{ padding: '0.4rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <strong>{appointment.service_name || appointment.service_code}</strong>
                          <span className={`status-pill status-${appointment.status}`} style={{ marginLeft: '0.4rem' }}>
                            {appointment.status}
                          </span>
                          <div className="hint" style={{ fontSize: '0.8rem' }}>
                            {formatDate(appointment.starts_at)} · {appointment.resource_name || '—'}
                          </div>
                        </li>
                      ))}
                    </ul>
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
                        <li key={conversation.id} style={{ padding: '0.35rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <strong>{conversation.status}</strong> · {conversation.message_count || 0} mensajes
                          <div className="hint" style={{ fontSize: '0.8rem' }}>
                            {formatDate(conversation.updated_at)}
                            {conversation.current_intent ? ` · ${conversation.current_intent}` : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Sin conversaciones todavía.</p>
                  )}
                </div>
              </div>

              <div className="schedule-panel" data-testid="contact-packages-panel">
                <div>
                  <strong>Paquetes activos</strong>
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
                        <li key={pkg.id} style={{ padding: '0.4rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <div>
                            <strong>{pkg.package_name || pkg.name}</strong>{' '}
                            <span className={`status-pill status-${pkg.status}`}>{pkg.status}</span>
                          </div>
                          <div className="hint" style={{ fontSize: '0.8rem' }}>
                            {pkg.remaining_sessions} / {pkg.total_sessions} sesiones restantes ·
                            pago: {pkg.payment_status}
                            {pkg.expires_at ? ` · vence ${formatDateShort(pkg.expires_at)}` : ''}
                          </div>
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
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Sin paquetes asignados.</p>
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
                        <li key={note.id} style={{ padding: '0.4rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <div>{note.body}</div>
                          <div className="hint" style={{ fontSize: '0.75rem' }}>
                            {note.created_by_name || 'Equipo'} · {formatDate(note.created_at)}
                          </div>
                        </li>
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
