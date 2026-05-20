import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../../permissions/index.js';
import {
  NoCreditsEmpty,
  NoGenerationsEmpty,
  NoPlatformsConnectedEmpty,
  NoScheduledPostsEmpty,
  ProviderUnavailableEmpty,
} from './EmptyStates.jsx';


describe('Influencer empty states (UI-INFLU-006)', () => {
  it('NoGenerationsEmpty dispara onGenerate al hacer click', async () => {
    const onGenerate = vi.fn();
    const user = userEvent.setup();
    render(<NoGenerationsEmpty onGenerate={onGenerate} />);
    await user.click(screen.getByRole('button', { name: /Generar contenido/i }));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it('NoScheduledPostsEmpty dispara onSchedule', async () => {
    const onSchedule = vi.fn();
    const user = userEvent.setup();
    render(<NoScheduledPostsEmpty onSchedule={onSchedule} />);
    await user.click(screen.getByRole('button', { name: /Programar post/i }));
    expect(onSchedule).toHaveBeenCalledOnce();
  });

  it('NoPlatformsConnectedEmpty dispara onConnect', async () => {
    const onConnect = vi.fn();
    const user = userEvent.setup();
    render(<NoPlatformsConnectedEmpty onConnect={onConnect} />);
    await user.click(screen.getByRole('button', { name: /Conectar plataforma/i }));
    expect(onConnect).toHaveBeenCalledOnce();
  });

  it('NoCreditsEmpty CTA disabled sin influencer.credits.topup', () => {
    usePermissions.mockReturnValue({ can: () => false });
    render(<NoCreditsEmpty onTopUp={() => {}} />);
    expect(screen.getByRole('button', { name: /Comprar créditos/i })).toBeDisabled();
  });

  it('ProviderUnavailableEmpty dispara onRetry', async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ProviderUnavailableEmpty onRetry={onRetry} />);
    await user.click(screen.getByRole('button', { name: /Reintentar/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
