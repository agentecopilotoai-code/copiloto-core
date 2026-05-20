import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ToastProvider, useToast } from '../../../components/ui/index.js';
import {
  generationCompletedToast,
  insufficientCreditsToast,
  providerFallbackToast,
  publishFailedToast,
} from './influencerToasts.js';


function ToastTrigger({ onPush }) {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast.push(onPush())}>fire</button>
  );
}


function renderWithProvider(onPush) {
  return render(
    <ToastProvider>
      <ToastTrigger onPush={onPush} />
    </ToastProvider>,
  );
}


describe('influencerToasts (UI-INFLU-007)', () => {
  it('generationCompletedToast renderiza success con thumbnail img', async () => {
    const user = userEvent.setup();
    renderWithProvider(() => generationCompletedToast({
      count: 4,
      thumbnailUrl: 'https://s3/test/thumb.png',
    }));
    await user.click(screen.getByRole('button', { name: 'fire' }));
    expect(screen.getByText('Generación completada')).toBeInTheDocument();
    expect(screen.getByText('4 assets listos')).toBeInTheDocument();
    // El thumbnail debe estar presente como <img>.
    expect(document.querySelector('img[src="https://s3/test/thumb.png"]')).toBeTruthy();
  });

  it('insufficientCreditsToast dispara handler de top-up', async () => {
    const onTopUp = vi.fn();
    const user = userEvent.setup();
    renderWithProvider(() => insufficientCreditsToast({ shortBy: 5, onTopUp }));
    await user.click(screen.getByRole('button', { name: 'fire' }));
    await user.click(screen.getByRole('button', { name: /Top-up/i }));
    expect(onTopUp).toHaveBeenCalledOnce();
  });

  it('providerFallbackToast usa tone info y mensaje informativo', async () => {
    const user = userEvent.setup();
    renderWithProvider(() => providerFallbackToast({
      failedProvider: 'Grok', usingProvider: 'OpenAI',
    }));
    await user.click(screen.getByRole('button', { name: 'fire' }));
    expect(screen.getByText(/Provider Grok temporalmente caído/i)).toBeInTheDocument();
    expect(screen.getByText(/Usando OpenAI/i)).toBeInTheDocument();
  });

  it('publishFailedToast con token_expired dispara CTA Reconectar', async () => {
    const onReconnect = vi.fn();
    const user = userEvent.setup();
    renderWithProvider(() => publishFailedToast({
      platform: 'Instagram', reason: 'token_expired', onReconnect,
    }));
    await user.click(screen.getByRole('button', { name: 'fire' }));
    expect(screen.getByText(/Publicación a Instagram falló/i)).toBeInTheDocument();
    expect(screen.getByText(/Token expirado/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Reconectar/i }));
    expect(onReconnect).toHaveBeenCalledOnce();
  });
});
