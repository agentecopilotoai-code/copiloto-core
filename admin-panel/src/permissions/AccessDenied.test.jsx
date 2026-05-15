import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AccessDenied } from './AccessDenied.jsx';

describe('<AccessDenied/> (UI-016.6 refactor)', () => {
  it('muestra el heading del HTML T2 + capability + modo', () => {
    render(<AccessDenied capability="services.write" mode="RW" />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'No tienes acceso a este módulo' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/services\.write/)).toBeInTheDocument();
    expect(screen.getByText(/edición/i)).toBeInTheDocument();
  });

  it('en modo R describe acceso de lectura', () => {
    render(<AccessDenied capability="campaigns.write" mode="R" />);
    // Lectura para campaigns.write — el usuario ni siquiera puede ver el módulo.
    expect(screen.getByText(/lectura/i)).toBeInTheDocument();
    expect(screen.getByText(/campaigns\.write/)).toBeInTheDocument();
  });

  it('mantiene "Acceso restringido" como microcopy legacy (regex de tests por módulo)', () => {
    render(<AccessDenied capability="services.write" mode="R" />);
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
  });

  it('dispara onGoHome al click en "Volver al inicio"', async () => {
    const onGoHome = vi.fn();
    render(<AccessDenied capability="services.write" mode="R" onGoHome={onGoHome} />);
    await userEvent.click(screen.getByRole('button', { name: 'Volver al inicio' }));
    expect(onGoHome).toHaveBeenCalledTimes(1);
  });

  it('renderiza children debajo del body cuando se pasan', () => {
    render(
      <AccessDenied capability="x.read" mode="R">
        <span>Slot adicional</span>
      </AccessDenied>,
    );
    expect(screen.getByText('Slot adicional')).toBeInTheDocument();
  });
});
