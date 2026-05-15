import { describe, it, expect, vi } from 'vitest';

// `viewerConversationsData` reusa `isUrgentConversation` / `parseMeta` desde
// `inboxData.js`, que a su vez importa `conversationMessageMediaUrl` de
// `coreApi`. Aislamos el import para no arrastrar todo el grafo del módulo.
vi.mock('../../../services/coreApi.js', () => ({
  conversationMessageMediaUrl: vi.fn(() => 'https://media/url'),
}));

import {
  CONVERSATIONS_DESCRIPTION,
  countByStatus,
  countUrgent,
  countWithHandoff,
  summarizeConversations,
} from './viewerConversationsData.js';

const CONVERSATIONS = [
  { id: 'c1', status: 'open' },
  { id: 'c2', status: 'human_required' },
  { id: 'c3', status: 'human_active' },
  { id: 'c4', status: 'waiting_user' },
  {
    id: 'c5',
    status: 'open',
    metadata: { qualification: { urgency_level: 'emergency' } },
  },
  {
    id: 'c6',
    status: 'human_required',
    metadata: '{"qualification":{"urgency_level":"high"}}',
  },
];

const COMPLAINTS = [
  { id: 'q1', feedback_rating: 1 },
  { id: 'q2', feedback_rating: 2 },
];

describe('viewerConversationsData', () => {
  it('CONVERSATIONS_DESCRIPTION menciona el modo solo lectura', () => {
    // El PageHeader del feature debe explicar el contrato — el `ReadOnlyShell`
    // ya añade el banner permanente, pero el subtítulo refuerza el alcance.
    expect(CONVERSATIONS_DESCRIPTION).toMatch(/solo lectura/i);
    expect(CONVERSATIONS_DESCRIPTION).toMatch(/iniciar conversaciones/i);
  });

  it('countByStatus agrega por estado y omite filas sin `status`', () => {
    expect(countByStatus(CONVERSATIONS)).toEqual({
      open: 2,
      human_required: 2,
      human_active: 1,
      waiting_user: 1,
    });
    expect(countByStatus([])).toEqual({});
    expect(countByStatus(null)).toEqual({});
    // Filas sin `status` (defensivo) no rompen la suma.
    expect(countByStatus([{ id: 'x' }, { id: 'y', status: 'open' }])).toEqual({ open: 1 });
  });

  it('countWithHandoff cuenta human_required + human_active + waiting_agent', () => {
    // De la fixture: c2 (human_required), c3 (human_active), c6 (human_required).
    expect(countWithHandoff(CONVERSATIONS)).toBe(3);
    expect(countWithHandoff([])).toBe(0);
    expect(countWithHandoff(null)).toBe(0);

    const withWaitingAgent = [{ id: 'a', status: 'waiting_agent' }];
    expect(countWithHandoff(withWaitingAgent)).toBe(1);
  });

  it('countUrgent cuenta solo metadata.qualification.urgency_level ∈ {emergency, high}', () => {
    // De la fixture: c5 (emergency), c6 (high, metadata stringificada).
    expect(countUrgent(CONVERSATIONS)).toBe(2);

    // medium/low no cuentan.
    const mid = [
      { id: 'm', status: 'open', metadata: { qualification: { urgency_level: 'medium' } } },
    ];
    expect(countUrgent(mid)).toBe(0);
    expect(countUrgent([])).toBe(0);
    expect(countUrgent(null)).toBe(0);
  });

  it('summarizeConversations agrega total + withHandoff + urgent + complaints', () => {
    expect(summarizeConversations(CONVERSATIONS, COMPLAINTS)).toEqual({
      total: 6,
      withHandoff: 3,
      urgent: 2,
      complaints: 2,
    });
    // Inputs inválidos degradan a `0` en cada campo.
    expect(summarizeConversations(null, null)).toEqual({
      total: 0,
      withHandoff: 0,
      urgent: 0,
      complaints: 0,
    });
  });
});
