import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { runAxe } from './axeHelper.js';

vi.mock('../../services/coreApi.js', () => ({
  acceptConversationHandoff: vi.fn(),
  assignContactTags: vi.fn(),
  cancelAppointment: vi.fn(),
  conversationMessageMediaUrl: vi.fn(() => 'https://media/url'),
  createAppointment: vi.fn(),
  createContactNote: vi.fn(),
  createConversationHandoff: vi.fn(),
  createQuote: vi.fn(),
  createResource: vi.fn(),
  createServiceRequest: vi.fn(),
  generateAppointmentPaymentLink: vi.fn(),
  getConversation: vi.fn(),
  getQuoteForSr: vi.fn(),
  getTenantAvailability: vi.fn(),
  listAppointmentFeedback: vi.fn(),
  listAppointments: vi.fn(),
  listComplaintConversations: vi.fn(),
  listContactTags: vi.fn(),
  listConversations: vi.fn(),
  listMediaAssets: vi.fn(),
  listResources: vi.fn(),
  listServiceRequests: vi.fn(),
  openConversationStream: vi.fn(() => ({ close: vi.fn(), readyState: 0 })),
  patchQuote: vi.fn(),
  patchServiceRequest: vi.fn(),
  releaseConversation: vi.fn(),
  sendAppointmentPaymentLink: vi.fn(),
  sendConversationMessage: vi.fn(),
  sendQuote: vi.fn(),
  startConversation: vi.fn(),
  unassignContactTag: vi.fn(),
  updateAppointment: vi.fn(),
  updateAppointmentPaymentStatus: vi.fn(),
  updateResource: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { OperationsDesk } from '../../features/agente/inbox/index.js';

const AGENT_PROFILE = { sub: 'u-agent' };
const ACME = {
  id: 'tenant-acme',
  slug: 'acme',
  roles: ['agent'],
  vertical_code: 'salon',
};
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Inbox operativo', summary: 'Conversaciones del tenant' };

const CONVERSATIONS = [
  {
    id: 'conv-1',
    contact_label: 'María Pérez',
    contact_id: 'contact-1',
    status: 'human_required',
    latest_message_text: 'Hola',
    updated_at: '2026-05-14T09:00:00Z',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: AGENT_PROFILE };
  coreApi.listConversations.mockResolvedValue(CONVERSATIONS);
  coreApi.listComplaintConversations.mockResolvedValue([]);
  coreApi.getConversation.mockResolvedValue({
    id: 'conv-1',
    contact_label: 'María Pérez',
    contact_id: 'contact-1',
    status: 'human_required',
    messages: [],
  });
  coreApi.listResources.mockResolvedValue([]);
  coreApi.listAppointments.mockResolvedValue([]);
  coreApi.listMediaAssets.mockResolvedValue([]);
  coreApi.listContactTags.mockResolvedValue([]);
  coreApi.getTenantAvailability.mockResolvedValue({ resources: [] });
  coreApi.listServiceRequests.mockResolvedValue([]);
});

describe('a11y · Agente · Operations Desk', () => {
  it('a11y — Operations Desk has no serious/critical violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <OperationsDesk module={MODULE} session={SESSION} tenant={ACME} />
      </MemoryRouter>,
    );
    await screen.findAllByText('María Pérez');

    expect(await runAxe(container)).toHaveNoViolations();
  });
});
