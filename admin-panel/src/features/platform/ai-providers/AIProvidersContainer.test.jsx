import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../../services/coreApi.js', () => ({
  listAIProviders: vi.fn(),
  updateAIProvider: vi.fn(),
  testAIProvider: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// AIProviders es presentacional; mockeamos para verificar las props que recibe.
vi.mock('./AIProviders.jsx', () => ({
  AIProviders: ({ rows, onSave, onTestProvider }) => (
    <div data-testid="ai-providers">
      <span data-testid="row-count">{rows.length}</span>
      <button
        type="button"
        onClick={() => onSave('llm', { provider: 'grok' })}
        data-testid="trigger-save"
      >
        save
      </button>
      <button
        type="button"
        onClick={() => onTestProvider('llm', { prompt: 'hi' })}
        data-testid="trigger-test"
      >
        test
      </button>
    </div>
  ),
}));

// eslint-disable-next-line no-unused-vars
import * as coreApi from '../../../services/coreApi.js';
import { AIProvidersContainer } from './AIProvidersContainer.jsx';

const SESSION = { accessToken: 'tk' };

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION };
});

describe('<AIProvidersContainer/>', () => {
  it('muestra LoadingScreen mientras carga', () => {
    coreApi.listAIProviders.mockReturnValue(new Promise(() => {}));
    render(<AIProvidersContainer />);
    expect(screen.getByRole('heading', { name: /Cargando/i })).toBeInTheDocument();
  });

  it('hidrata rows desde response.rows', async () => {
    coreApi.listAIProviders.mockResolvedValue({ rows: [{ modality: 'llm' }, { modality: 'image' }] });
    render(<AIProvidersContainer />);
    expect(await screen.findByTestId('ai-providers')).toBeInTheDocument();
    expect(screen.getByTestId('row-count').textContent).toBe('2');
  });

  it('rows = [] cuando response.rows no es array', async () => {
    coreApi.listAIProviders.mockResolvedValue({});
    render(<AIProvidersContainer />);
    expect(await screen.findByTestId('row-count')).toHaveTextContent('0');
  });

  it('pinta AlertBanner cuando listAIProviders falla', async () => {
    coreApi.listAIProviders.mockRejectedValue(new Error('http 500'));
    render(<AIProvidersContainer />);
    expect(await screen.findByText(/http 500/)).toBeInTheDocument();
  });

  it('onSave invoca updateAIProvider y refresca', async () => {
    coreApi.listAIProviders.mockResolvedValue({ rows: [] });
    coreApi.updateAIProvider.mockResolvedValue({});
    render(<AIProvidersContainer />);
    const btn = await screen.findByTestId('trigger-save');
    btn.click();
    await waitFor(() => {
      expect(coreApi.updateAIProvider).toHaveBeenCalledWith(SESSION, 'llm', { provider: 'grok' });
    });
  });

  it('onSave propaga el error al caller (throw)', async () => {
    coreApi.listAIProviders.mockResolvedValue({ rows: [] });
    coreApi.updateAIProvider.mockRejectedValue(new Error('mfa req'));
    // El onSave del container hace setError(...) + re-throw. El re-throw lo
    // captura el caller real (presentational AIProviders) en su propio
    // try/catch; en este test el button mock NO await, así que swallow
    // explícito con un listener temporal.
    const onUnhandled = vi.fn();
    process.on('unhandledRejection', onUnhandled);
    try {
      render(<AIProvidersContainer />);
      const btn = await screen.findByTestId('trigger-save');
      btn.click();
      expect(await screen.findByText(/mfa req/)).toBeInTheDocument();
    } finally {
      process.off('unhandledRejection', onUnhandled);
    }
  });

  it('onTestProvider llama testAIProvider', async () => {
    coreApi.listAIProviders.mockResolvedValue({ rows: [] });
    coreApi.testAIProvider.mockResolvedValue({ ok: true });
    render(<AIProvidersContainer />);
    const btn = await screen.findByTestId('trigger-test');
    btn.click();
    await waitFor(() => {
      expect(coreApi.testAIProvider).toHaveBeenCalledWith(SESSION, 'llm', { prompt: 'hi' });
    });
  });

  it('no dispara la query cuando session es null', () => {
    mockTenantContext = { session: null };
    render(<AIProvidersContainer />);
    expect(coreApi.listAIProviders).not.toHaveBeenCalled();
  });
});
