import { describe, it, expect } from 'vitest';

import { formatDate, formatDateShort, renderQualificationAnswer } from './contactsFormat.js';

describe('contactsFormat', () => {
  it('formatDate / formatDateShort return a dash for missing values', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatDateShort('')).toBe('—');
  });

  it('formatDate / formatDateShort render a non-empty string for a valid ISO date', () => {
    const iso = '2026-05-14T09:42:00Z';
    expect(formatDate(iso)).not.toBe('—');
    expect(formatDate(iso).length).toBeGreaterThan(0);
    expect(formatDateShort(iso)).not.toBe('—');
  });

  it('renderQualificationAnswer maps yes_no answers', () => {
    const q = { kind: 'yes_no' };
    expect(renderQualificationAnswer(q, true)).toBe('Sí');
    expect(renderQualificationAnswer(q, false)).toBe('No');
    expect(renderQualificationAnswer(q, undefined)).toBe('—');
  });

  it('renderQualificationAnswer maps single and multi choice to option labels', () => {
    const single = {
      kind: 'single_choice',
      options: [{ value: 'a', label: 'Opción A' }, { value: 'b', label: 'Opción B' }],
    };
    expect(renderQualificationAnswer(single, 'b')).toBe('Opción B');
    // unknown value falls back to the raw value
    expect(renderQualificationAnswer(single, 'z')).toBe('z');

    const multi = {
      kind: 'multi_choice',
      options: [{ value: 'x', label: 'X' }, { value: 'y', label: 'Y' }],
    };
    expect(renderQualificationAnswer(multi, ['x', 'y'])).toBe('X, Y');
    expect(renderQualificationAnswer(multi, [])).toBe('—');
  });

  it('renderQualificationAnswer stringifies free-form answers and handles nullish', () => {
    expect(renderQualificationAnswer({ kind: 'text' }, 'hola')).toBe('hola');
    expect(renderQualificationAnswer({ kind: 'number' }, 42)).toBe('42');
    expect(renderQualificationAnswer({ kind: 'text' }, '')).toBe('—');
    expect(renderQualificationAnswer(null, 'x')).toBe('—');
  });
});
