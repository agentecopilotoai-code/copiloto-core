/**
 * JustificacionRequiredField — campo obligatorio de justificación para
 * acciones irreversibles (anular, reasignar, reclasificar, cerrar PQRSD).
 *
 * RNF-009/058: toda acción crítica registra justificación auditable.
 * El componente valida longitud mínima (default 10 chars) y delega al
 * padre vía `onChange(value, isValid)`.
 */
import React, { useState } from 'react';

export function JustificacionRequiredField({
  value,
  onChange,
  minLength = 10,
  maxLength = 2000,
  label = 'Justificación',
  placeholder = 'Explique brevemente el motivo de esta acción…',
  hint,
  required = true,
  id = 'justificacion',
}) {
  const [touched, setTouched] = useState(false);
  const v = value ?? '';
  const isValid = !required || v.trim().length >= minLength;

  function isValidOf(s, req, min) {
    if (!req) return true;
    return (s ?? '').trim().length >= min;
  }

  const handleChange = (e) => {
    const next = e.target.value.slice(0, maxLength);
    onChange?.(next, isValidOf(next, required, minLength));
  };

  const showError = touched && !isValid;

  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required && <span className="req" aria-label="obligatorio">*</span>}
      </label>
      <textarea
        id={id}
        className="textarea"
        value={v}
        onChange={handleChange}
        onBlur={() => setTouched(true)}
        placeholder={placeholder}
        aria-required={required}
        aria-invalid={showError}
        data-testid="justificacion-required-field"
      />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 11.5,
        }}
      >
        <span className={showError ? '' : 'hint'} style={{
          color: showError ? 'var(--red-700)' : undefined,
        }}>
          {showError
            ? `Mínimo ${minLength} caracteres.`
            : hint || `Mínimo ${minLength} caracteres.`}
        </span>
        <span className="hint">{v.length} / {maxLength}</span>
      </div>
    </div>
  );
}

export default JustificacionRequiredField;
