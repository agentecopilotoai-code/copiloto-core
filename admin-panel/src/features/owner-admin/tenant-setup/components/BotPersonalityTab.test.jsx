/**
 * UI-012-FU: tests for the brand logo uploader embedded in the "Voz del
 * bot" tab. Race-resilient: uses findBy* whenever the asserted DOM
 * depends on an async mock resolving (per UI-015 convention).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { BotPersonalityTab } from './BotPersonalityTab.jsx';
import { DEFAULT_BOT_PERSONALITY } from '../tenantSetupData.js';

function buildState({ brandLogoUrl = null } = {}) {
  return {
    botPersonality: { ...DEFAULT_BOT_PERSONALITY },
    tenantForm: { display_name: 'Tenant Demo' },
    isBusy: false,
    currentTenantId: 'tenant-abc',
    brandLogoUrl,
  };
}

function buildActions(overrides = {}) {
  return {
    handleSaveSettings: vi.fn(),
    setBotPersonality: vi.fn(),
    handleUploadBrandLogo: vi.fn().mockResolvedValue({ brand_logo_url: 'https://cdn/x.png' }),
    handleClearBrandLogo: vi.fn().mockResolvedValue({ brand_logo_url: null }),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BotPersonalityTab — brand logo section', () => {
  it('shows the empty-state copy when no brand_logo_url is loaded', () => {
    render(<BotPersonalityTab state={buildState()} actions={buildActions()} />);
    expect(screen.getByRole('heading', { name: 'Logo de marca', level: 3 })).toBeInTheDocument();
    expect(screen.getByTestId('brand-logo-empty')).toBeInTheDocument();
    // "Quitar logo" is NOT shown when there's nothing to clear.
    expect(screen.queryByRole('button', { name: 'Quitar logo' })).toBeNull();
  });

  it('renders the current logo and the "Quitar logo" button when brand_logo_url is set', () => {
    render(
      <BotPersonalityTab
        state={buildState({ brandLogoUrl: 'https://cdn.example/logo.png' })}
        actions={buildActions()}
      />,
    );
    const img = screen.getByRole('img', { name: /Logo actual de Tenant Demo/ });
    expect(img).toHaveAttribute('src', 'https://cdn.example/logo.png');
    expect(screen.getByRole('button', { name: 'Quitar logo' })).toBeInTheDocument();
    expect(screen.queryByTestId('brand-logo-empty')).toBeNull();
  });

  it('calls handleUploadBrandLogo with the selected file on submit', async () => {
    const actions = buildActions();
    render(<BotPersonalityTab state={buildState()} actions={actions} />);

    const file = new File(['png-bytes'], 'logo.png', { type: 'image/png' });
    const input = screen.getByTestId('brand-logo-file-input');
    fireEvent.change(input, { target: { files: [file] } });

    const submit = screen.getByRole('button', { name: 'Subir logo' });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    expect(actions.handleUploadBrandLogo).toHaveBeenCalledTimes(1);
    expect(actions.handleUploadBrandLogo).toHaveBeenCalledWith(file);
  });

  it('calls handleClearBrandLogo when the "Quitar logo" button is clicked', async () => {
    const actions = buildActions();
    render(
      <BotPersonalityTab
        state={buildState({ brandLogoUrl: 'https://cdn.example/logo.png' })}
        actions={actions}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Quitar logo' }));
    expect(actions.handleClearBrandLogo).toHaveBeenCalledTimes(1);
  });

  it('disables Subir logo when no file is selected', () => {
    render(<BotPersonalityTab state={buildState()} actions={buildActions()} />);
    expect(screen.getByRole('button', { name: 'Subir logo' })).toBeDisabled();
  });

  it('disables Subir logo when there is no current tenant id', () => {
    render(
      <BotPersonalityTab
        state={{ ...buildState(), currentTenantId: null }}
        actions={buildActions()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Subir logo' })).toBeDisabled();
  });
});
