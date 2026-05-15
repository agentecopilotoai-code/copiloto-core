import { describe, it, expect } from 'vitest';
import {
  DEFAULT_HANDOFF_FILTER,
  HANDOFF_FILTERS,
  applyHandoffFilter,
  deriveHandoffCounts,
  filterHandoffs,
  filterMyHandoffs,
  filterUnassignedHandoffs,
  isHandoffConversation,
  toHandoffRow,
} from './myHandoffsData.js';

const CONVERSATIONS = [
  // assigned to the current user
  {
    id: 'c1',
    status: 'human_active',
    contact_label: 'Camila Velasco',
    active_handoff_id: 'h1',
    active_handoff_assigned_to: 'user-me',
  },
  // unassigned handoff (escalated, nobody took it)
  {
    id: 'c2',
    status: 'human_required',
    contact_label: 'Andrés Gómez',
    active_handoff_id: 'h2',
    active_handoff_assigned_to: null,
  },
  // assigned to a colleague
  {
    id: 'c3',
    status: 'human_active',
    contact_label: 'María José L.',
    active_handoff_id: 'h3',
    active_handoff_assigned_to: 'user-luis',
  },
  // plain bot conversation — not a handoff
  {
    id: 'c4',
    status: 'open',
    contact_label: 'Sin escalar',
    active_handoff_id: null,
    active_handoff_assigned_to: null,
  },
];

describe('myHandoffsData', () => {
  it('exposes the handoff filter tab definitions', () => {
    expect(HANDOFF_FILTERS.map((f) => f.id)).toEqual(['all', 'unassigned', 'mine']);
    expect(DEFAULT_HANDOFF_FILTER).toBe('all');
  });

  it('identifies handoff conversations by active handoff or human status', () => {
    expect(isHandoffConversation(CONVERSATIONS[0])).toBe(true);
    expect(isHandoffConversation(CONVERSATIONS[3])).toBe(false);
    expect(isHandoffConversation({ status: 'waiting_agent' })).toBe(true);
    expect(isHandoffConversation(null)).toBe(false);
  });

  it('filters the full handoff queue, excluding bot-only conversations', () => {
    expect(filterHandoffs(CONVERSATIONS).map((c) => c.id)).toEqual(['c1', 'c2', 'c3']);
    expect(filterHandoffs(null)).toEqual([]);
  });

  it('filters handoffs assigned to the current user', () => {
    expect(filterMyHandoffs(CONVERSATIONS, 'user-me').map((c) => c.id)).toEqual(['c1']);
    // without a current user id there is nobody to match against
    expect(filterMyHandoffs(CONVERSATIONS, null)).toEqual([]);
  });

  it('filters unassigned handoffs', () => {
    expect(filterUnassignedHandoffs(CONVERSATIONS).map((c) => c.id)).toEqual(['c2']);
  });

  it('applies a filter tab by id and derives per-tab counts', () => {
    expect(applyHandoffFilter(CONVERSATIONS, 'mine', 'user-me').map((c) => c.id)).toEqual(['c1']);
    expect(applyHandoffFilter(CONVERSATIONS, 'unassigned', 'user-me').map((c) => c.id)).toEqual([
      'c2',
    ]);
    expect(applyHandoffFilter(CONVERSATIONS, 'all', 'user-me').map((c) => c.id)).toEqual([
      'c1',
      'c2',
      'c3',
    ]);
    expect(deriveHandoffCounts(CONVERSATIONS, 'user-me')).toEqual({
      all: 3,
      unassigned: 1,
      mine: 1,
    });
  });

  it('shapes a conversation into a handoff row with ownership flags', () => {
    expect(toHandoffRow(CONVERSATIONS[0], 'user-me')).toMatchObject({
      id: 'c1',
      contactLabel: 'Camila Velasco',
      isMine: true,
      isUnassigned: false,
      ownership: 'Mía',
    });
    expect(toHandoffRow(CONVERSATIONS[1], 'user-me')).toMatchObject({
      isUnassigned: true,
      ownership: 'Sin asignar',
    });
    expect(toHandoffRow(CONVERSATIONS[2], 'user-me')).toMatchObject({
      isMine: false,
      isUnassigned: false,
      ownership: 'Colega',
    });
  });
});
