import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AccountNotifications } from './AccountNotifications.jsx';

describe('<AccountNotifications/>', () => {
  it('pinta las 6 filas de eventos del HTML T3', () => {
    render(<AccountNotifications />);
    expect(screen.getByText('Digest diario')).toBeInTheDocument();
    expect(screen.getByText('Handoff con SLA cercano')).toBeInTheDocument();
    expect(screen.getByText('Cobro fallido')).toBeInTheDocument();
    expect(screen.getByText('Cita confirmada')).toBeInTheDocument();
    expect(screen.getByText('Quality rating de WhatsApp baja')).toBeInTheDocument();
    expect(screen.getByText('Resumen semanal de campañas')).toBeInTheDocument();
  });

  it('cada fila ofrece checkboxes para email/wa/inapp', () => {
    render(<AccountNotifications />);
    const dailyDigestRow = screen.getByText('Digest diario').closest('[role="row"]');
    expect(dailyDigestRow).not.toBeNull();
    const checkboxes = within(dailyDigestRow).getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3);
  });

  it('toggle de checkbox actualiza su estado checked', async () => {
    render(<AccountNotifications />);
    // Digest diario · email viene marcado por defecto (matriz canónica).
    const checkbox = document.querySelector(
      'input[data-event="daily_digest"][data-channel="email"]',
    );
    expect(checkbox).toBeChecked();
    await userEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it('al hacer submit muestra el AlertBanner de UI-016.7-FU', async () => {
    render(<AccountNotifications />);
    await userEvent.click(screen.getByRole('button', { name: 'Guardar preferencias' }));
    expect(
      screen.getByText(/PATCH \/v1\/me\/notifications/),
    ).toBeInTheDocument();
    expect(screen.getByText(/UI-016.7-FU/)).toBeInTheDocument();
  });
});
