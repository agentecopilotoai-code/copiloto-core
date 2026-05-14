import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getPlatformFeatureFlags: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { getPlatformFeatureFlags } from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { FeatureFlags } from './FeatureFlags.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const FLAGS_RESPONSE = {
  flags: [
    {
      key: 'cloud_llm_primary',
      description: 'Usar el LLM cloud como primario, fallback Ollama.',
      type: 'kill',
      default: 'on',
      rollout_pct: 100,
      related_task: 'TASK-0024',
    },
    {
      key: 'instagram_messenger',
      description: 'Canales sociales Instagram DM y Messenger.',
      type: 'feature',
      default: 'on',
      rollout_pct: 100,
      related_task: 'TASK-0074',
    },
  ],
  flag_types: ['feature', 'kill', 'rollout', 'experiment'],
  summary: { total: 2, on: 2, off: 0, by_type: { kill: 1, feature: 1 } },
  note: 'Catálogo de solo lectura del registro estático de feature flags.',
};

function setup() {
  return render(
    <MemoryRouter>
      <FeatureFlags />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
  };
  getPlatformFeatureFlags.mockResolvedValue(FLAGS_RESPONSE);
});

describe('FeatureFlags', () => {
  it('renders the header, KPIs and the flag catalogue', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Feature flags' }),
    ).toBeInTheDocument();

    const totalKpi = screen.getByText('Flags en el catálogo').closest('article');
    expect(totalKpi.textContent).toContain('2');

    expect(screen.getByText('cloud_llm_primary')).toBeInTheDocument();
    expect(screen.getByText('instagram_messenger')).toBeInTheDocument();
  });

  it('filters the catalogue by flag type client-side', async () => {
    setup();
    await screen.findByText('cloud_llm_primary');

    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'feature');

    expect(screen.queryByText('cloud_llm_primary')).toBeNull();
    expect(screen.getByText('instagram_messenger')).toBeInTheDocument();
  });

  it('filters the catalogue by search text client-side', async () => {
    setup();
    await screen.findByText('cloud_llm_primary');

    await userEvent.type(screen.getByLabelText('Buscar'), 'instagram');

    expect(screen.queryByText('cloud_llm_primary')).toBeNull();
    expect(screen.getByText('instagram_messenger')).toBeInTheDocument();
  });

  it('renders an error state and supports retry', async () => {
    getPlatformFeatureFlags.mockRejectedValueOnce(new Error('feature-flags endpoint down'));
    setup();

    expect(
      await screen.findByText('feature-flags endpoint down'),
    ).toBeInTheDocument();

    getPlatformFeatureFlags.mockResolvedValueOnce(FLAGS_RESPONSE);
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await screen.findByText('cloud_llm_primary');
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Feature flags' })).toBeNull();
  });
});
