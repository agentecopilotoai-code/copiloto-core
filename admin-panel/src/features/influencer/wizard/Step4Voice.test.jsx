import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../permissions/index.js';
import { Step4Voice } from './Step4Voice.jsx';


describe('<Step4Voice/> (UI-INFLU-011)', () => {
  it('cambio de tono programa fetchCaptions tras debounce (1s)', () => {
    vi.useFakeTimers();
    usePermissions.mockReturnValue({ can: () => true });
    const onFetchCaptions = vi.fn().mockResolvedValue({
      captions: { ig: 'IG cap', tiktok: 'TT cap', story: 'ST cap' },
    });
    const { rerender } = render(<Step4Voice onFetchCaptions={onFetchCaptions} />);

    // Force a re-render with different initialForm — simulates user changing tone.
    rerender(<Step4Voice initialForm={{ tone: 'professional' }} onFetchCaptions={onFetchCaptions} />);

    // Debounce no ha disparado todavía.
    vi.advanceTimersByTime(500);
    expect(onFetchCaptions).not.toHaveBeenCalled();

    vi.advanceTimersByTime(700);  // total > 1s
    expect(onFetchCaptions).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('re-generar sample disabled sin influencer.generate', () => {
    usePermissions.mockReturnValue({ can: () => false });
    render(<Step4Voice />);
    expect(screen.getByRole('button', { name: /Generar sample/i })).toBeDisabled();
  });

  it('audio player visible cuando hay sampleUrl', () => {
    usePermissions.mockReturnValue({ can: () => true });
    const { container } = render(
      <Step4Voice sampleUrl="https://s3/sample.mp3" />,
    );
    const audio = container.querySelector('audio');
    expect(audio).not.toBeNull();
    expect(audio.getAttribute('src')).toBe('https://s3/sample.mp3');
  });

  it('UI-INFLU-014.10: siguiente SIN sample ya NO bloquea (voz no obligatoria)', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step4Voice onNext={onNext} />);
    await user.click(screen.getByRole('button', { name: /Siguiente paso/i }));
    // El usuario puede continuar sin generar sample — la voz se puede
    // configurar después desde el estudio del personaje.
    expect(onNext).toHaveBeenCalledOnce();
  });
});
