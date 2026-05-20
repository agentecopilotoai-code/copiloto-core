import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Step5Platforms } from './Step5Platforms.jsx';


describe('<Step5Platforms/> (UI-INFLU-012)', () => {
  it('click "Conectar" en Instagram dispara onConnectInstagram', async () => {
    const onConnect = vi.fn();
    const user = userEvent.setup();
    render(<Step5Platforms onConnectInstagram={onConnect} />);
    // Find Instagram row's "Conectar" button — primer button "Conectar" en la lista.
    const buttons = screen.getAllByRole('button', { name: 'Conectar' });
    await user.click(buttons[0]);
    expect(onConnect).toHaveBeenCalledOnce();
  });

  it('TikTok/YouTube/etc. tienen botón "Próximamente" disabled', () => {
    render(<Step5Platforms />);
    const proximamente = screen.getAllByRole('button', { name: 'Próximamente' });
    expect(proximamente.length).toBeGreaterThan(0);
    proximamente.forEach((b) => expect(b).toBeDisabled());
  });

  it('Etiqueta IA visible está checked y disabled (no se puede desactivar)', () => {
    render(<Step5Platforms />);
    const checkbox = screen.getByRole('checkbox', { name: /Etiqueta IA visible/i });
    expect(checkbox).toBeChecked();
    expect(checkbox).toBeDisabled();
  });

  it('"Crear personaje" sin handles dispara error inline', async () => {
    const onActivate = vi.fn();
    const user = userEvent.setup();
    render(<Step5Platforms onActivate={onActivate} />);
    await user.click(screen.getByRole('button', { name: /Crear personaje/i }));
    expect(onActivate).not.toHaveBeenCalled();
    expect(screen.getByText(/Conecta al menos una plataforma/i)).toBeInTheDocument();
  });
});
