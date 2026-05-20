import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../permissions/index.js';
import { Generate } from './Generate.jsx';


describe('<Generate/> (UI-INFLU-013)', () => {
  it('cambio de kind actualiza el costo proyectado', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const user = userEvent.setup();
    render(<Generate balance={500} />);

    expect(screen.getByRole('button', { name: /Generar.*3 créditos/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Reel/i }));
    expect(screen.getByRole('button', { name: /Generar.*8 créditos/i })).toBeInTheDocument();
  });

  it('balance ≤ 0 muestra NoCreditsEmpty', () => {
    usePermissions.mockReturnValue({ can: () => true });
    render(<Generate balance={0} />);
    expect(screen.getByText(/Sin créditos disponibles/i)).toBeInTheDocument();
  });

  it('providerDown muestra ProviderUnavailableEmpty', () => {
    usePermissions.mockReturnValue({ can: () => true });
    render(<Generate balance={100} providerDown />);
    expect(screen.getByText(/Servicio temporalmente no disponible/i)).toBeInTheDocument();
  });

  it('submit con balance suficiente dispara onGenerate con payload válido', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const onGenerate = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<Generate balance={100} onGenerate={onGenerate} />);

    await user.click(screen.getByRole('button', { name: /Generar.*3 créditos/i }));
    expect(onGenerate).toHaveBeenCalledOnce();
    const payload = onGenerate.mock.calls[0][0];
    expect(payload.kind).toBe('photo');
    expect(payload.format).toBe('1:1');
  });

  it('balance bajo deshabilita el botón Generar con tooltip', () => {
    usePermissions.mockReturnValue({ can: () => true });
    render(<Generate balance={1} />);
    const btn = screen.getByRole('button', { name: /Generar.*3 créditos/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', expect.stringMatching(/créditos más/i));
  });
});
