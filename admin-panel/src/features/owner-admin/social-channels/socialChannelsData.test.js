import { describe, it, expect } from 'vitest';

import {
  buildPayload,
  channelForProvider,
  channelRecipientId,
  emptyForm,
  providerMeta,
  statusLabel,
  statusTone,
} from './socialChannelsData.js';

describe('socialChannelsData', () => {
  it('emptyForm carries the provider and sane defaults', () => {
    const form = emptyForm('facebook_messenger');
    expect(form.provider).toBe('facebook_messenger');
    expect(form.account_mode).toBe('mock');
    expect(form.service_window_hours).toBe(24);
  });

  it('providerMeta resolves both Meta surfaces', () => {
    expect(providerMeta('instagram_messenger').label).toBe('Instagram DM');
    expect(providerMeta('facebook_messenger').label).toBe('Facebook Messenger');
    expect(providerMeta('unknown')).toBeNull();
  });

  it('channelForProvider finds the matching channel record', () => {
    const channels = [
      { provider: 'instagram_messenger', status: 'active' },
      { provider: 'facebook_messenger', status: 'active' },
    ];
    expect(channelForProvider(channels, 'facebook_messenger').provider).toBe(
      'facebook_messenger',
    );
    expect(channelForProvider(channels, 'missing')).toBeNull();
    expect(channelForProvider(undefined, 'x')).toBeNull();
  });

  it('statusLabel and statusTone reflect status + account mode', () => {
    expect(statusLabel(null)).toBe('sin configurar');
    expect(statusTone(null)).toBe('neutral');
    expect(statusLabel({ status: 'pending' })).toBe('pending');
    expect(statusTone({ status: 'pending' })).toBe('warning');
    expect(statusLabel({ status: 'active', account_mode: 'live' })).toBe('live');
    expect(statusTone({ status: 'active', account_mode: 'live' })).toBe('success');
    expect(statusLabel({ status: 'active', account_mode: 'mock' })).toBe('mock');
    expect(statusTone({ status: 'active', account_mode: 'mock' })).toBe('accent');
  });

  it('channelRecipientId prefers page_id then instagram_account_id', () => {
    expect(channelRecipientId({ page_id: 'PAGE-1' })).toBe('PAGE-1');
    expect(channelRecipientId({ instagram_account_id: 'IG-1' })).toBe('IG-1');
    expect(channelRecipientId({})).toBe('—');
    expect(channelRecipientId(null)).toBe('—');
  });

  it('buildPayload rejects a missing recipient and normalises a valid form', () => {
    expect(buildPayload(emptyForm('instagram_messenger'), 'instagram_messenger').error).toMatch(
      /obligatorio/i,
    );
    const { payload, error } = buildPayload(
      {
        ...emptyForm('facebook_messenger'),
        recipient_account_id: '  PAGE-9  ',
        business_id: '  ',
        meta_access_token: '  EAAG  ',
        service_window_hours: '48',
      },
      'facebook_messenger',
    );
    expect(error).toBeUndefined();
    expect(payload.provider).toBe('facebook_messenger');
    expect(payload.recipient_account_id).toBe('PAGE-9');
    expect(payload.business_id).toBeNull();
    expect(payload.meta_access_token).toBe('EAAG');
    expect(payload.app_secret).toBeUndefined();
    expect(payload.service_window_hours).toBe(48);
  });
});
