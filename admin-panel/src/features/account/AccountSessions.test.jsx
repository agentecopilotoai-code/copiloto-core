import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AccountSessions } from './AccountSessions.jsx';

describe('<AccountSessions/>', () => {
  it('pinta heading + listado de sesiones demo', () => {
    render(<AccountSessions />);
    expect(screen.getByRole('heading', { name: 'Sesiones activas' })).toBeInTheDocument();
    expect(screen.getByText(/Chrome 124 · macOS/)).toBeInTheDocument();
    expect(screen.getByText(/WhatsApp Web · iPhone 15/)).toBeInTheDocument();
    expect(screen.getByText(/Firefox 125 · Ubuntu/)).toBeInTheDocument();
  });

  it('marca la sesión actual con el chip "esta sesión"', () => {
    render(<AccountSessions />);
    expect(screen.getByText('esta sesión')).toBeInTheDocument();
  });

  it('botón "Revocar" de la sesión actual queda deshabilitado', () => {
    render(<AccountSessions />);
    const buttons = screen.getAllByRole('button', { name: /Revocar sesión/ });
    const currentBtn = buttons.find((btn) =>
      btn.getAttribute('aria-label')?.includes('Chrome 124'),
    );
    expect(currentBtn).toBeDisabled();
  });

  it('al revocar una sesión muestra AlertBanner UI-016.7-FU', async () => {
    render(<AccountSessions />);
    const otherSessionBtn = screen
      .getAllByRole('button', { name: /Revocar sesión/ })
      .find((btn) => btn.getAttribute('aria-label')?.includes('WhatsApp Web'));
    await userEvent.click(otherSessionBtn);
    expect(screen.getByText(/DELETE \/v1\/me\/sessions/)).toBeInTheDocument();
    expect(screen.getByText(/UI-016.7-FU/)).toBeInTheDocument();
  });

  it('al cerrar todas las demás sesiones muestra AlertBanner UI-016.7-FU', async () => {
    render(<AccountSessions />);
    await userEvent.click(
      screen.getByRole('button', { name: 'Cerrar todas las demás sesiones' }),
    );
    expect(screen.getByText(/Cerrar otras sesiones queda en standby/)).toBeInTheDocument();
  });
});
