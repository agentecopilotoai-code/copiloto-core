import { describe, it, expect } from 'vitest';

import {
  buildPromoPayload,
  emptyPromoForm,
  formatBytes,
  inferKindFromFile,
  labelFromFileName,
  parseTags,
  promoFormFromPromotion,
  validateUploadFile,
} from './mediaLibraryData.js';

const fakeFile = (name, type, sizeBytes) => ({ name, type, size: sizeBytes });

describe('mediaLibraryData', () => {
  it('inferKindFromFile maps mime types to media kinds', () => {
    expect(inferKindFromFile(fakeFile('a.jpg', 'image/jpeg', 1))).toBe('image');
    expect(inferKindFromFile(fakeFile('a.mp4', 'video/mp4', 1))).toBe('video');
    expect(inferKindFromFile(fakeFile('a.mp3', 'audio/mpeg', 1))).toBe('audio');
    expect(inferKindFromFile(fakeFile('a.pdf', 'application/pdf', 1))).toBe('pdf');
    expect(inferKindFromFile(null)).toBe('image');
  });

  it('validateUploadFile rejects files over the per-kind size limit', () => {
    const okImage = validateUploadFile(fakeFile('a.jpg', 'image/jpeg', 2 * 1024 * 1024));
    expect(okImage).toEqual({ kind: 'image', error: null });

    const bigImage = validateUploadFile(fakeFile('a.jpg', 'image/jpeg', 6 * 1024 * 1024));
    expect(bigImage.kind).toBe('image');
    expect(bigImage.error).toMatch(/5 MB/);
  });

  it('labelFromFileName drops the extension', () => {
    expect(labelFromFileName(fakeFile('lobby.principal.png', 'image/png', 1))).toBe(
      'lobby.principal',
    );
    expect(labelFromFileName(fakeFile('noext', 'image/png', 1))).toBe('noext');
  });

  it('promoFormFromPromotion maps a promotion record into the form shape', () => {
    const form = promoFormFromPromotion({
      name: 'Promo',
      discount_percent: 20,
      valid_from: '2026-05-01T10:00:00Z',
      applies_to_service_ids: ['s-1'],
      is_active: false,
    });
    expect(form.name).toBe('Promo');
    expect(form.discount_percent).toBe('20');
    expect(form.valid_from).toBe('2026-05-01T10:00');
    expect(form.applies_to_service_ids).toEqual(['s-1']);
    expect(form.is_active).toBe(false);
  });

  it('parseTags splits, trims and drops blanks', () => {
    expect(parseTags(' lobby , equipo ,, ')).toEqual(['lobby', 'equipo']);
    expect(parseTags('')).toEqual([]);
  });

  it('buildPromoPayload rejects a missing name and normalises a valid form', () => {
    expect(buildPromoPayload(emptyPromoForm()).error).toMatch(/obligatorio/i);

    const { payload, error } = buildPromoPayload({
      ...emptyPromoForm(),
      name: '  Promo mayo  ',
      discount_percent: '15',
      coupon_code: '  MAYO  ',
      sort_order: '2',
    });
    expect(error).toBeUndefined();
    expect(payload.name).toBe('Promo mayo');
    expect(payload.discount_percent).toBe(15);
    expect(payload.coupon_code).toBe('MAYO');
    expect(payload.description).toBeNull();
    expect(payload.sort_order).toBe(2);
  });

  it('formatBytes renders KB / MB and a dash for nullish input', () => {
    expect(formatBytes(2 * 1024 * 1024)).toBe('2.00 MB');
    expect(formatBytes(512 * 1024)).toBe('512 KB');
    expect(formatBytes(null)).toBe('—');
  });
});
