import { useEffect, useMemo, useState } from 'react';

import {
  createPromotion,
  deleteMediaAsset,
  deletePromotion,
  listMediaAssets,
  listPromotions,
  listServices,
  updateMediaAsset,
  updatePromotion,
  uploadMediaAsset,
} from '../../../services/coreApi.js';

const MEDIA_KIND_LABELS = {
  image: 'Imagen',
  video: 'Video',
  pdf: 'PDF',
  audio: 'Audio',
};

const SIZE_LIMITS_MB = { image: 5, video: 16, audio: 16, pdf: 100 };

function inferKindFromFile(file) {
  if (!file) return 'image';
  const type = (file.type || '').toLowerCase();
  if (type.startsWith('image/')) return 'image';
  if (type.startsWith('video/')) return 'video';
  if (type.startsWith('audio/')) return 'audio';
  if (type === 'application/pdf') return 'pdf';
  return 'image';
}

function emptyPromoForm() {
  return {
    name: '',
    description: '',
    media_asset_id: '',
    valid_from: '',
    valid_until: '',
    applies_to_service_ids: [],
    coupon_code: '',
    discount_percent: '',
    is_active: true,
    sort_order: 0,
  };
}

export function MediaLibraryModule({ module: moduleMeta, session, tenant }) {
  const tenantId = tenant?.id;

  const [assets, setAssets] = useState([]);
  const [promotions, setPromotions] = useState([]);
  const [services, setServices] = useState([]);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const [uploadForm, setUploadForm] = useState({
    kind: 'image',
    label: '',
    description: '',
    tags: '',
    file: null,
  });
  const [promoForm, setPromoForm] = useState(emptyPromoForm());
  const [editingPromoId, setEditingPromoId] = useState(null);

  const assetsById = useMemo(() => {
    const map = new Map();
    assets.forEach((a) => map.set(a.id, a));
    return map;
  }, [assets]);

  const servicesById = useMemo(() => {
    const map = new Map();
    services.forEach((s) => map.set(s.id, s));
    return map;
  }, [services]);

  const reload = async () => {
    if (!tenantId) return;
    setIsLoading(true);
    try {
      const [mediaList, promoList, serviceList] = await Promise.all([
        listMediaAssets(session, tenantId),
        listPromotions(session, tenantId, { includeInactive: true }),
        listServices(session, tenantId, { includeInactive: false }),
      ]);
      setAssets(mediaList || []);
      setPromotions(promoList || []);
      setServices(serviceList || []);
    } catch (error) {
      setNotice({ type: 'error', text: `No se pudo cargar la biblioteca: ${error.message}` });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;
    if (!file) {
      setUploadForm((prev) => ({ ...prev, file: null }));
      return;
    }
    const kind = inferKindFromFile(file);
    const sizeMb = file.size / (1024 * 1024);
    if (sizeMb > SIZE_LIMITS_MB[kind]) {
      setNotice({
        type: 'error',
        text: `El archivo supera el límite de ${SIZE_LIMITS_MB[kind]} MB para ${MEDIA_KIND_LABELS[kind]}.`,
      });
      event.target.value = '';
      return;
    }
    setUploadForm((prev) => ({
      ...prev,
      file,
      kind,
      label: prev.label || file.name.split('.').slice(0, -1).join('.') || file.name,
    }));
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!tenantId) return;
    if (!uploadForm.file) {
      setNotice({ type: 'error', text: 'Selecciona un archivo primero.' });
      return;
    }
    if (!uploadForm.label.trim()) {
      setNotice({ type: 'error', text: 'La etiqueta del archivo es obligatoria.' });
      return;
    }
    setIsBusy(true);
    try {
      const tags = uploadForm.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      await uploadMediaAsset(session, tenantId, {
        kind: uploadForm.kind,
        label: uploadForm.label.trim(),
        description: uploadForm.description.trim(),
        tags,
        file: uploadForm.file,
      });
      setUploadForm({ kind: 'image', label: '', description: '', tags: '', file: null });
      setNotice({ type: 'success', text: 'Medio subido correctamente.' });
      await reload();
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'Error al subir.' });
    } finally {
      setIsBusy(false);
    }
  };

  const handleDeleteAsset = async (asset) => {
    if (!window.confirm(`¿Eliminar el archivo "${asset.label}"?`)) return;
    setIsBusy(true);
    try {
      await deleteMediaAsset(session, tenantId, asset.id);
      setNotice({ type: 'success', text: 'Archivo eliminado.' });
      await reload();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  };

  const handleUpdateTags = async (asset, tags) => {
    setIsBusy(true);
    try {
      await updateMediaAsset(session, tenantId, asset.id, { tags });
      await reload();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  };

  const startNewPromo = () => {
    setEditingPromoId(null);
    setPromoForm(emptyPromoForm());
  };

  const startEditPromo = (promo) => {
    setEditingPromoId(promo.id);
    setPromoForm({
      name: promo.name || '',
      description: promo.description || '',
      media_asset_id: promo.media_asset_id || '',
      valid_from: promo.valid_from ? promo.valid_from.slice(0, 16) : '',
      valid_until: promo.valid_until ? promo.valid_until.slice(0, 16) : '',
      applies_to_service_ids: promo.applies_to_service_ids || [],
      coupon_code: promo.coupon_code || '',
      discount_percent: promo.discount_percent != null ? String(promo.discount_percent) : '',
      is_active: promo.is_active !== false,
      sort_order: promo.sort_order ?? 0,
    });
  };

  const submitPromo = async (event) => {
    event.preventDefault();
    if (!tenantId) return;
    if (!promoForm.name.trim()) {
      setNotice({ type: 'error', text: 'El nombre de la promoción es obligatorio.' });
      return;
    }
    const payload = {
      name: promoForm.name.trim(),
      description: promoForm.description.trim() || null,
      media_asset_id: promoForm.media_asset_id || null,
      valid_from: promoForm.valid_from ? new Date(promoForm.valid_from).toISOString() : null,
      valid_until: promoForm.valid_until ? new Date(promoForm.valid_until).toISOString() : null,
      applies_to_service_ids: promoForm.applies_to_service_ids,
      coupon_code: promoForm.coupon_code.trim() || null,
      discount_percent: promoForm.discount_percent === '' ? null : Number(promoForm.discount_percent),
      is_active: promoForm.is_active,
      sort_order: Number(promoForm.sort_order) || 0,
    };
    setIsBusy(true);
    try {
      if (editingPromoId) {
        await updatePromotion(session, tenantId, editingPromoId, payload);
        setNotice({ type: 'success', text: 'Promoción actualizada.' });
      } else {
        await createPromotion(session, tenantId, payload);
        setNotice({ type: 'success', text: 'Promoción creada.' });
      }
      startNewPromo();
      await reload();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  };

  const removePromo = async (promo) => {
    if (!window.confirm(`¿Eliminar la promoción "${promo.name}"?`)) return;
    setIsBusy(true);
    try {
      await deletePromotion(session, tenantId, promo.id);
      setNotice({ type: 'success', text: 'Promoción eliminada.' });
      if (editingPromoId === promo.id) startNewPromo();
      await reload();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  };

  if (!tenantId) {
    return (
      <section className="module-card">
        <h2>{moduleMeta?.label || 'Medios y promociones'}</h2>
        <p className="hint">Selecciona un tenant para gestionar la biblioteca de medios.</p>
      </section>
    );
  }

  return (
    <section className="module-card media-library">
      <header className="module-header">
        <div>
          <h2>{moduleMeta?.label || 'Medios y promociones'}</h2>
          <p className="hint">
            Sube fotos, videos y PDFs del negocio. Crea promociones que el bot envía durante el
            booking para subir conversión.
          </p>
        </div>
      </header>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      <div className="media-library-grid" style={{ display: 'grid', gap: '1.5rem', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
        <div>
          <h3>Subir nuevo medio</h3>
          <form className="form-grid" onSubmit={handleUpload}>
            <label>
              Archivo
              <input
                type="file"
                onChange={handleFileChange}
                accept="image/jpeg,image/png,image/webp,video/mp4,video/3gpp,audio/aac,audio/mp4,audio/mpeg,audio/amr,audio/ogg,application/pdf"
                required
              />
              {uploadForm.file ? (
                <small className="hint">
                  {MEDIA_KIND_LABELS[uploadForm.kind]} ·
                  {' '}
                  {(uploadForm.file.size / (1024 * 1024)).toFixed(2)} MB
                </small>
              ) : (
                <small className="hint">
                  Límites: Imagen 5MB · Video 16MB · Audio 16MB · PDF 100MB
                </small>
              )}
            </label>
            <label>
              Etiqueta corta
              <input
                type="text"
                value={uploadForm.label}
                onChange={(event) => setUploadForm({ ...uploadForm, label: event.target.value })}
                placeholder="Ej. Lobby principal"
                maxLength={200}
                required
              />
            </label>
            <label>
              Descripción
              <textarea
                value={uploadForm.description}
                onChange={(event) => setUploadForm({ ...uploadForm, description: event.target.value })}
                rows={2}
                placeholder="Contexto que aparecerá en el panel interno"
              />
            </label>
            <label>
              Tags (separados por coma)
              <input
                type="text"
                value={uploadForm.tags}
                onChange={(event) => setUploadForm({ ...uploadForm, tags: event.target.value })}
                placeholder="lobby, equipo, procedimiento"
              />
            </label>
            <div className="form-actions">
              <button className="primary-action" type="submit" disabled={isBusy}>
                Subir
              </button>
            </div>
          </form>

          <h3 style={{ marginTop: '1.5rem' }}>Biblioteca ({assets.length})</h3>
          {isLoading ? <p className="hint">Cargando…</p> : null}
          {assets.length === 0 && !isLoading ? <p className="hint">Aún no hay archivos.</p> : null}
          <div className="media-grid" style={{ display: 'grid', gap: '0.75rem', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
            {assets.map((asset) => (
              <article key={asset.id} className="media-card" style={{ border: '1px solid var(--border, #e2e8f0)', borderRadius: 6, padding: '0.5rem' }}>
                <strong>{asset.label}</strong>
                <div className="hint" style={{ fontSize: '0.75rem' }}>
                  {MEDIA_KIND_LABELS[asset.kind] || asset.kind} ·
                  {' '}
                  {(asset.size_bytes / 1024).toFixed(0)} KB
                </div>
                {(asset.tags || []).length ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.2rem', margin: '0.25rem 0' }}>
                    {asset.tags.map((tag) => (
                      <span key={tag} className="status-pill" style={{ fontSize: '0.65rem', background: '#475569', color: '#fff', padding: '0.05rem 0.4rem' }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}
                {asset.description ? <p className="hint" style={{ fontSize: '0.75rem' }}>{asset.description}</p> : null}
                <div style={{ display: 'flex', gap: '0.25rem', marginTop: '0.4rem' }}>
                  <button
                    type="button"
                    onClick={() => {
                      const next = window.prompt('Tags (separados por coma):', (asset.tags || []).join(', '));
                      if (next != null) {
                        const tags = next.split(',').map((t) => t.trim()).filter(Boolean);
                        handleUpdateTags(asset, tags);
                      }
                    }}
                    disabled={isBusy}
                  >
                    Tags
                  </button>
                  <button type="button" className="danger" onClick={() => handleDeleteAsset(asset)} disabled={isBusy}>
                    Eliminar
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div>
          <h3>{editingPromoId ? 'Editar promoción' : 'Nueva promoción'}</h3>
          <form className="form-grid" onSubmit={submitPromo}>
            <label>
              Nombre
              <input
                type="text"
                value={promoForm.name}
                onChange={(event) => setPromoForm({ ...promoForm, name: event.target.value })}
                placeholder="Ej. Limpieza dental 20% - mayo"
                maxLength={200}
                required
              />
            </label>
            <label>
              Descripción / texto que envía el bot
              <textarea
                value={promoForm.description}
                onChange={(event) => setPromoForm({ ...promoForm, description: event.target.value })}
                rows={3}
                maxLength={2000}
              />
            </label>
            <label>
              Imagen / video asociado
              <select
                value={promoForm.media_asset_id || ''}
                onChange={(event) => setPromoForm({ ...promoForm, media_asset_id: event.target.value })}
              >
                <option value="">— Sin medio (solo texto) —</option>
                {assets
                  .filter((a) => ['image', 'video', 'pdf'].includes(a.kind))
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {MEDIA_KIND_LABELS[a.kind]}: {a.label}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Aplica a servicios
              <select
                multiple
                value={promoForm.applies_to_service_ids}
                onChange={(event) => {
                  const ids = Array.from(event.target.selectedOptions).map((o) => o.value);
                  setPromoForm({ ...promoForm, applies_to_service_ids: ids });
                }}
                style={{ minHeight: '6rem' }}
              >
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
              <small className="hint">Vacío = aplica a todos los servicios del tenant.</small>
            </label>
            <label>
              Vigencia desde
              <input
                type="datetime-local"
                value={promoForm.valid_from}
                onChange={(event) => setPromoForm({ ...promoForm, valid_from: event.target.value })}
              />
            </label>
            <label>
              Vigencia hasta
              <input
                type="datetime-local"
                value={promoForm.valid_until}
                onChange={(event) => setPromoForm({ ...promoForm, valid_until: event.target.value })}
              />
            </label>
            <label>
              Código de cupón
              <input
                type="text"
                value={promoForm.coupon_code}
                onChange={(event) => setPromoForm({ ...promoForm, coupon_code: event.target.value })}
                maxLength={80}
              />
            </label>
            <label>
              Descuento (%)
              <input
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={promoForm.discount_percent}
                onChange={(event) => setPromoForm({ ...promoForm, discount_percent: event.target.value })}
              />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={promoForm.is_active}
                onChange={(event) => setPromoForm({ ...promoForm, is_active: event.target.checked })}
              />
              Promoción activa
            </label>
            <div className="form-actions">
              {editingPromoId ? (
                <button type="button" onClick={startNewPromo} disabled={isBusy}>
                  Cancelar
                </button>
              ) : null}
              <button className="primary-action" type="submit" disabled={isBusy}>
                {editingPromoId ? 'Guardar cambios' : 'Crear promoción'}
              </button>
            </div>
          </form>

          <h3 style={{ marginTop: '1.5rem' }}>Promociones ({promotions.length})</h3>
          {promotions.length === 0 ? <p className="hint">Aún no hay promociones configuradas.</p> : null}
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {promotions.map((promo) => {
              const media = promo.media_asset_id ? assetsById.get(promo.media_asset_id) : null;
              return (
                <li key={promo.id} style={{ borderBottom: '1px solid var(--border, #e2e8f0)', padding: '0.6rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'flex-start' }}>
                    <div>
                      <strong>{promo.name}</strong>
                      {promo.is_active ? (
                        <span className="status-pill" style={{ background: '#16a34a', color: '#fff', fontSize: '0.65rem', marginLeft: '0.4rem' }}>Activa</span>
                      ) : (
                        <span className="status-pill" style={{ background: '#94a3b8', color: '#fff', fontSize: '0.65rem', marginLeft: '0.4rem' }}>Pausada</span>
                      )}
                      {promo.discount_percent != null ? (
                        <span className="hint" style={{ marginLeft: '0.4rem' }}>{promo.discount_percent}% off</span>
                      ) : null}
                      <div className="hint" style={{ fontSize: '0.75rem' }}>
                        {media ? `Con ${MEDIA_KIND_LABELS[media.kind]}: ${media.label}` : 'Solo texto'}
                      </div>
                      {promo.applies_to_service_ids?.length ? (
                        <div className="hint" style={{ fontSize: '0.75rem' }}>
                          Servicios: {promo.applies_to_service_ids.map((sid) => servicesById.get(sid)?.name || sid.slice(0, 8)).join(', ')}
                        </div>
                      ) : (
                        <div className="hint" style={{ fontSize: '0.75rem' }}>Todos los servicios</div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                      <button type="button" onClick={() => startEditPromo(promo)} disabled={isBusy}>Editar</button>
                      <button type="button" className="danger" onClick={() => removePromo(promo)} disabled={isBusy}>Eliminar</button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}
