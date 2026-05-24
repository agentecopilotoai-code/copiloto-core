import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useGdScope, GD_SCOPE_LABELS } from './useGdScope.js';

describe('useGdScope', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it('default = propio cuando no hay storage previo', () => {
    const { result } = renderHook(() => useGdScope('acme'));
    expect(result.current.scope).toBe('propio');
    expect(result.current.scopes).toEqual([
      'propio', 'dependencias_autorizadas', 'institucional',
    ]);
  });

  it('setScope persiste en localStorage por tenant', () => {
    const { result } = renderHook(() => useGdScope('acme'));
    act(() => result.current.setScope('institucional'));
    expect(result.current.scope).toBe('institucional');
    expect(window.localStorage.getItem('gd_scope__acme')).toBe('institucional');
  });

  it('ignora scopes inválidos', () => {
    const { result } = renderHook(() => useGdScope('acme'));
    act(() => result.current.setScope('XYZ'));
    expect(result.current.scope).toBe('propio');
  });

  it('lee valor previo de localStorage al montar', () => {
    window.localStorage.setItem('gd_scope__otro', 'dependencias_autorizadas');
    const { result } = renderHook(() => useGdScope('otro'));
    expect(result.current.scope).toBe('dependencias_autorizadas');
  });

  it('GD_SCOPE_LABELS expone label en español para cada scope', () => {
    expect(GD_SCOPE_LABELS.propio).toMatch(/dependencia/i);
    expect(GD_SCOPE_LABELS.institucional).toMatch(/entidad/i);
  });
});
