/**
 * UsuarioPicker — selector de usuario filtrado por dependencia y rol.
 *
 * Usado por TareaFicha (reasignar) y ReasignacionMasiva. No es modal en sí,
 * se renderiza inline dentro de su contenedor.
 */
import React from 'react';

import { useUsuariosDependencia } from './useGdBuzon.js';

export function UsuarioPicker({
  session,
  dependenciaId,
  rol,
  value,
  onChange,
  label = 'Seleccione usuario',
  excluir = [],
  testId = 'usuario-picker',
}) {
  const { items, loading, error } = useUsuariosDependencia(
    session, dependenciaId, { rol, enabled: Boolean(dependenciaId) },
  );

  const filtered = (items || []).filter((u) => !excluir.includes(u.id || u.user_id));

  return (
    <div className="field" data-testid={testId}>
      <label>{label}</label>
      {!dependenciaId && (
        <p className="hint">
          Seleccione primero una dependencia.
        </p>
      )}
      {loading && <p className="muted">Cargando usuarios…</p>}
      {error && (
        <p className="hint" style={{ color: 'var(--red-700)' }}>
          {error.message || 'No se pudieron cargar usuarios.'}
        </p>
      )}
      {!loading && !error && (
        <select
          className="select"
          value={value || ''}
          onChange={(e) => onChange?.(e.target.value)}
          disabled={!dependenciaId || filtered.length === 0}
          data-testid={`${testId}-select`}
        >
          <option value="">— Sin asignar —</option>
          {filtered.map((u) => (
            <option key={u.id || u.user_id} value={u.id || u.user_id}>
              {u.nombre} {u.cargo ? `· ${u.cargo}` : ''}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export default UsuarioPicker;
