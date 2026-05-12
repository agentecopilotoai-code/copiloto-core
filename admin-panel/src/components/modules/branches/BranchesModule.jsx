import { useEffect, useMemo, useState } from 'react';

import {
  createBranch,
  deactivateBranch,
  listBranches,
  updateBranch,
} from '../../../services/coreApi.js';

const WEEKDAYS = [
  { key: 'mon', label: 'Lun' },
  { key: 'tue', label: 'Mar' },
  { key: 'wed', label: 'Mié' },
  { key: 'thu', label: 'Jue' },
  { key: 'fri', label: 'Vie' },
  { key: 'sat', label: 'Sáb' },
  { key: 'sun', label: 'Dom' },
];

const TIMEZONE_OPTIONS = [
  'America/Bogota',
  'America/Mexico_City',
  'America/Lima',
  'America/Santiago',
  'America/Argentina/Buenos_Aires',
  'America/Caracas',
  'America/Sao_Paulo',
  'Europe/Madrid',
];

function emptyForm() {
  return {
    id: null,
    name: '',
    code: '',
    address: '',
    city: '',
    state: '',
    country: 'CO',
    lat: '',
    lng: '',
    maps_url: '',
    phone_e164: '',
    timezone: 'America/Bogota',
    opening_hours: {},
    is_active: true,
    sort_order: 0,
  };
}

function toForm(branch) {
  return {
    id: branch.id,
    name: branch.name || '',
    code: branch.code || '',
    address: branch.address || '',
    city: branch.city || '',
    state: branch.state || '',
    country: branch.country || 'CO',
    lat: branch.lat ?? '',
    lng: branch.lng ?? '',
    maps_url: branch.maps_url || '',
    phone_e164: branch.phone_e164 || '',
    timezone: branch.timezone || 'America/Bogota',
    opening_hours: branch.opening_hours || {},
    is_active: branch.is_active !== false,
    sort_order: branch.sort_order || 0,
  };
}

function buildMapsPreview(lat, lng, address) {
  const trimmedLat = (lat ?? '').toString().trim();
  const trimmedLng = (lng ?? '').toString().trim();
  if (trimmedLat && trimmedLng) {
    return `https://www.google.com/maps?q=${encodeURIComponent(`${trimmedLat},${trimmedLng}`)}`;
  }
  const trimmedAddress = (address ?? '').trim();
  if (trimmedAddress) {
    return `https://www.google.com/maps?q=${encodeURIComponent(trimmedAddress)}`;
  }
  return null;
}

export function BranchesModule({ module, session, tenant }) {
  const [branches, setBranches] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function refresh() {
    if (!tenant?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listBranches(session, tenant.id, {});
      setBranches(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'No se pudieron cargar las sedes.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  const mapsPreviewUrl = useMemo(
    () => buildMapsPreview(form.lat, form.lng, form.address),
    [form.lat, form.lng, form.address],
  );

  function resetForm() {
    setForm(emptyForm());
  }

  function selectBranchForEdit(branch) {
    setForm(toForm(branch));
  }

  function setHoursForDay(dayKey, franjas) {
    setForm((prev) => ({
      ...prev,
      opening_hours: {
        ...(prev.opening_hours || {}),
        [dayKey]: franjas,
      },
    }));
  }

  function addFranja(dayKey) {
    const current = (form.opening_hours || {})[dayKey] || [];
    setHoursForDay(dayKey, [...current, { start: '09:00', end: '18:00' }]);
  }

  function removeFranja(dayKey, idx) {
    const current = (form.opening_hours || {})[dayKey] || [];
    setHoursForDay(
      dayKey,
      current.filter((_, i) => i !== idx),
    );
  }

  function updateFranja(dayKey, idx, field, value) {
    const current = (form.opening_hours || {})[dayKey] || [];
    const next = current.map((f, i) => (i === idx ? { ...f, [field]: value } : f));
    setHoursForDay(dayKey, next);
  }

  async function handleSave(evt) {
    evt.preventDefault();
    if (!tenant?.id) return;
    setSaving(true);
    setError(null);
    const payload = {
      name: form.name.trim(),
      code: form.code.trim(),
      address: form.address.trim() || null,
      city: form.city.trim() || null,
      state: form.state.trim() || null,
      country: form.country.trim().slice(0, 2).toUpperCase() || 'CO',
      lat: form.lat === '' ? null : Number(form.lat),
      lng: form.lng === '' ? null : Number(form.lng),
      maps_url: form.maps_url.trim() || null,
      phone_e164: form.phone_e164.trim() || null,
      timezone: form.timezone || 'America/Bogota',
      opening_hours: form.opening_hours || {},
      is_active: !!form.is_active,
      sort_order: Number(form.sort_order) || 0,
    };
    try {
      if (form.id) {
        await updateBranch(session, tenant.id, form.id, payload);
      } else {
        await createBranch(session, tenant.id, payload);
      }
      resetForm();
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo guardar la sede.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(branch) {
    if (!tenant?.id) return;
    if (!window.confirm(`¿Desactivar la sede "${branch.name}"?`)) return;
    setSaving(true);
    setError(null);
    try {
      await deactivateBranch(session, tenant.id, branch.id);
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo desactivar la sede.');
    } finally {
      setSaving(false);
    }
  }

  const activeBranches = branches.filter((b) => b.is_active);
  const inactiveBranches = branches.filter((b) => !b.is_active);

  return (
    <section className="module-card branches-module" data-module-key="branches">
      <header>
        <h2>{module?.label || 'Sedes'}</h2>
        <p className="hint">{module?.summary}</p>
      </header>

      {error ? (
        <div className="callout callout-error" role="alert">
          {error}
        </div>
      ) : null}

      <form className="branches-form" onSubmit={handleSave} aria-label="Formulario de sede">
        <div className="grid-2">
          <label>
            Nombre
            <input
              required
              maxLength={160}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label>
            Código (único por tenant)
            <input
              required
              maxLength={80}
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
          </label>
        </div>
        <div className="grid-2">
          <label>
            Dirección
            <input
              maxLength={500}
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
          </label>
          <label>
            Ciudad
            <input
              maxLength={120}
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
            />
          </label>
        </div>
        <div className="grid-3">
          <label>
            Lat
            <input
              type="number"
              step="0.0000001"
              value={form.lat}
              onChange={(e) => setForm({ ...form, lat: e.target.value })}
            />
          </label>
          <label>
            Lng
            <input
              type="number"
              step="0.0000001"
              value={form.lng}
              onChange={(e) => setForm({ ...form, lng: e.target.value })}
            />
          </label>
          <label>
            Zona horaria
            <select
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value })}
            >
              {TIMEZONE_OPTIONS.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid-2">
          <label>
            Maps URL
            <input
              maxLength={500}
              value={form.maps_url}
              onChange={(e) => setForm({ ...form, maps_url: e.target.value })}
              placeholder="https://maps.google.com/..."
            />
          </label>
          <label>
            Teléfono (E.164)
            <input
              maxLength={32}
              value={form.phone_e164}
              onChange={(e) => setForm({ ...form, phone_e164: e.target.value })}
              placeholder="+57..."
            />
          </label>
        </div>
        {mapsPreviewUrl ? (
          <p className="branches-maps-preview">
            Vista previa:{' '}
            <a href={mapsPreviewUrl} target="_blank" rel="noopener noreferrer">
              abrir en Google Maps
            </a>
          </p>
        ) : null}

        <fieldset className="branches-hours" data-testid="branches-hours">
          <legend>Horarios de atención por día</legend>
          {WEEKDAYS.map((day) => {
            const franjas = (form.opening_hours || {})[day.key] || [];
            return (
              <div className="branches-day" key={day.key}>
                <strong>{day.label}</strong>
                {franjas.map((franja, idx) => (
                  <span className="branches-franja" key={idx}>
                    <input
                      type="time"
                      value={franja.start || ''}
                      onChange={(e) => updateFranja(day.key, idx, 'start', e.target.value)}
                    />
                    <span aria-hidden="true">–</span>
                    <input
                      type="time"
                      value={franja.end || ''}
                      onChange={(e) => updateFranja(day.key, idx, 'end', e.target.value)}
                    />
                    <button type="button" onClick={() => removeFranja(day.key, idx)}>
                      Quitar
                    </button>
                  </span>
                ))}
                <button type="button" onClick={() => addFranja(day.key)}>
                  + franja
                </button>
              </div>
            );
          })}
        </fieldset>

        <div className="grid-2">
          <label>
            Orden
            <input
              type="number"
              min="0"
              value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Activa
          </label>
        </div>

        <div className="actions">
          <button type="submit" disabled={saving}>
            {form.id ? 'Guardar cambios' : 'Crear sede'}
          </button>
          {form.id ? (
            <button type="button" onClick={resetForm} disabled={saving}>
              Cancelar
            </button>
          ) : null}
        </div>
      </form>

      <h3>Sedes activas ({activeBranches.length})</h3>
      {loading ? <p>Cargando…</p> : null}
      <ul className="branches-list">
        {activeBranches.map((branch) => (
          <li className="branches-row" key={branch.id}>
            <div>
              <strong>{branch.name}</strong>{' '}
              <span className="hint">[{branch.code}]</span>
              <div className="hint">
                {branch.address || '—'}
                {branch.city ? `, ${branch.city}` : ''} · {branch.timezone}
              </div>
            </div>
            <div className="actions">
              <button type="button" onClick={() => selectBranchForEdit(branch)}>
                Editar
              </button>
              <button type="button" onClick={() => handleDeactivate(branch)}>
                Desactivar
              </button>
            </div>
          </li>
        ))}
      </ul>

      {inactiveBranches.length > 0 ? (
        <>
          <h3>Inactivas ({inactiveBranches.length})</h3>
          <ul className="branches-list inactive">
            {inactiveBranches.map((branch) => (
              <li className="branches-row" key={branch.id}>
                <div>
                  <strong>{branch.name}</strong>{' '}
                  <span className="hint">[{branch.code}]</span>
                </div>
                <div className="actions">
                  <button type="button" onClick={() => selectBranchForEdit(branch)}>
                    Reactivar (editar)
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
