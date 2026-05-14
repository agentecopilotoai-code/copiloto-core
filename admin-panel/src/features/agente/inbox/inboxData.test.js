import { describe, it, expect, vi } from 'vitest';
import {
  WORKING_DAYS,
  buildResourcePayload,
  computeQuoteTotals,
  deliveryLabel,
  emptyWorkingHoursForm,
  isUrgentConversation,
  mediaSource,
  messageLabel,
  parseMeta,
  sortConversations,
  statusLabel,
  workingHoursToJson,
} from './inboxData.js';

// `inboxData` imports `conversationMessageMediaUrl` from coreApi; mock it so the
// unit tests don't drag in the full service module graph. `vi.mock` is hoisted
// above the imports by vitest.
vi.mock('../../../services/coreApi.js', () => ({
  conversationMessageMediaUrl: vi.fn(
    (_session, tenantId, conversationId, messageId) =>
      `https://api/${tenantId}/${conversationId}/${messageId}`,
  ),
}));

describe('inboxData', () => {
  it('maps conversation status to Spanish labels with a passthrough fallback', () => {
    expect(statusLabel('human_active')).toBe('Humano activo');
    expect(statusLabel('open')).toBe('Bot activo');
    expect(statusLabel('mystery_status')).toBe('mystery_status');
  });

  it('maps message types to Spanish labels', () => {
    expect(messageLabel({ message_type: 'image' })).toBe('Imagen');
    expect(messageLabel({ message_type: 'interactive' })).toBe('Interactivo');
    expect(messageLabel({})).toBe('Mensaje');
  });

  it('derives a human-readable delivery label per message status', () => {
    expect(deliveryLabel({ status: 'queued' })).toBe('En cola: pendiente del worker');
    expect(deliveryLabel({ status: 'failed', error_code: 'E1' })).toBe('Falló WhatsApp: E1');
    expect(deliveryLabel({ status: 'sent', external_message_id: 'wamid.X' })).toBe(
      'Aceptado por WhatsApp: wamid.X',
    );
    expect(deliveryLabel({ status: 'sent' })).toBe('Enviado al proveedor');
    expect(deliveryLabel({ payload: { provider_result: { mocked: true } } })).toBe(
      'Simulado local: no salió a WhatsApp',
    );
  });

  it('parses a stringified metadata blob and tolerates bad JSON', () => {
    expect(parseMeta('{"a":1}')).toEqual({ a: 1 });
    expect(parseMeta('not json')).toBeNull();
    expect(parseMeta({ a: 1 })).toEqual({ a: 1 });
  });

  it('flags emergency/high urgency conversations and floats them to the top', () => {
    const urgent = { id: 'u', metadata: { qualification: { urgency_level: 'emergency' } } };
    const normal = { id: 'n', metadata: { qualification: { urgency_level: 'low' } } };
    expect(isUrgentConversation(urgent)).toBe(true);
    expect(isUrgentConversation(normal)).toBe(false);
    expect(sortConversations([normal, urgent]).map((c) => c.id)).toEqual(['u', 'n']);
  });

  it('builds an authenticated media URL only for streamable media messages', () => {
    const base = { id: 'm1', conversation_id: 'c1', media_id: 'med1' };
    expect(mediaSource({ ...base, message_type: 'image' }, {}, 'tenant-1')).toBe(
      'https://api/tenant-1/c1/m1',
    );
    // No tenant id → no URL.
    expect(mediaSource({ ...base, message_type: 'image' }, {}, null)).toBeNull();
    // Text messages never resolve a media URL.
    expect(mediaSource({ ...base, message_type: 'text' }, {}, 'tenant-1')).toBeNull();
  });

  it('computes quote subtotal and grand total from items, discount and tax', () => {
    const items = [
      { description: 'A', qty: 2, unit_price: 100 },
      { description: 'B', qty: 1, unit_price: 50 },
    ];
    const { subtotal, grandTotal } = computeQuoteTotals(items, 30, 20);
    expect(subtotal).toBe(250);
    expect(grandTotal).toBe(240);
  });

  it('serializes the working-hours form to the working_hours JSON shape', () => {
    const form = emptyWorkingHoursForm();
    const json = workingHoursToJson(form);
    // Mon-Fri enabled by default → one slot each; Sat/Sun empty.
    expect(json.mon).toEqual([{ start: '09:00', end: '18:00' }]);
    expect(json.sat).toEqual([]);
    expect(WORKING_DAYS).toHaveLength(7);
  });

  it('builds the resource payload with the capabilities + profile shaping', () => {
    const payload = buildResourcePayload({
      code: ' TEC-01 ',
      name: ' Técnico ',
      resourceType: 'technician',
      verticalCode: 'plumbing',
      workingHours: emptyWorkingHoursForm(),
      bio: '  ',
      photoMediaAssetId: '',
      specialty: 'Gasfitería',
      licenseNumber: '',
      yearsOfExperience: '7',
      publicProfile: true,
    });
    expect(payload.code).toBe('TEC-01');
    expect(payload.name).toBe('Técnico');
    expect(payload.bio).toBeNull();
    expect(payload.photo_media_asset_id).toBeNull();
    expect(payload.specialty).toBe('Gasfitería');
    expect(payload.years_of_experience).toBe(7);
    expect(payload.public_profile).toBe(true);
    expect(payload.capabilities.working_hours.mon).toEqual([{ start: '09:00', end: '18:00' }]);
  });
});
