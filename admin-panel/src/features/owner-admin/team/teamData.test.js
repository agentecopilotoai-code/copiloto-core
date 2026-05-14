import { describe, it, expect } from 'vitest';

import {
  callerIsOwner,
  emptyInviteForm,
  highestRole,
  memberInitials,
  roleCounts,
} from './teamData.js';

describe('teamData', () => {
  it('emptyInviteForm starts blank with the default role', () => {
    expect(emptyInviteForm()).toEqual({ email: '', display_name: '', role: 'agent' });
  });

  it('highestRole resolves the highest-precedence role', () => {
    expect(highestRole(['agent', 'admin'])).toBe('admin');
    expect(highestRole(['viewer'])).toBe('viewer');
    expect(highestRole(['owner', 'manager'])).toBe('owner');
    expect(highestRole([])).toBe('viewer');
    expect(highestRole(undefined)).toBe('viewer');
  });

  it('memberInitials builds up to two uppercase letters', () => {
    expect(memberInitials({ display_name: 'Camila Rojas' })).toBe('CR');
    expect(memberInitials({ display_name: 'Diana' })).toBe('DI');
    expect(memberInitials({ email: 'luis@x.co' })).toBe('LU');
    expect(memberInitials(null)).toBe('?');
  });

  it('callerIsOwner is true for owner or platform_owner across profile + tenant roles', () => {
    expect(callerIsOwner(['agent'], ['admin'])).toBe(false);
    expect(callerIsOwner(['owner'], [])).toBe(true);
    expect(callerIsOwner([], ['platform_owner'])).toBe(true);
    expect(callerIsOwner(undefined, undefined)).toBe(false);
  });

  it('roleCounts buckets members by highest role and counts pending invites', () => {
    const counts = roleCounts([
      { roles: ['owner'], status: 'active' },
      { roles: ['admin'], status: 'active' },
      { roles: ['agent'], status: 'active' },
      { roles: ['agent'], status: 'invited' },
      { roles: ['viewer'], status: 'active' },
    ]);
    expect(counts).toEqual({
      owner: 1,
      admin: 1,
      manager: 0,
      agent: 2,
      viewer: 1,
      pending: 1,
    });
  });
});
