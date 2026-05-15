import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

let mockSession;
vi.mock('../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

// eslint-disable-next-line import/first
import { AccountProfile } from './AccountProfile.jsx';

const OWNER_PROFILE = {
  name: 'Camila Rojas Martínez',
  email: 'camila@clinicaen.co',
  phone_number: '+57 300 8842 100',
  roles: ['owner'],
};

describe('<AccountProfile/>', () => {
  it('pinta hero con nombre, email del profile y badge del rol', () => {
    mockSession = { profile: OWNER_PROFILE };
    render(<AccountProfile />);
    expect(screen.getByRole('heading', { name: 'Perfil' })).toBeInTheDocument();
    expect(screen.getByText('Camila Rojas Martínez')).toBeInTheDocument();
    expect(screen.getByText(/camila@clinicaen.co/)).toBeInTheDocument();
    expect(screen.getByText('owner')).toBeInTheDocument();
  });

  it('email es read-only y muestra el helper de Auth0', () => {
    mockSession = { profile: OWNER_PROFILE };
    render(<AccountProfile />);
    const emailInput = screen.getByLabelText(/Email/);
    expect(emailInput).toHaveAttribute('readOnly');
    expect(screen.getByText(/Lo gestiona Auth0/)).toBeInTheDocument();
  });

  it('al hacer submit muestra el AlertBanner de UI-016.7-FU', async () => {
    mockSession = { profile: OWNER_PROFILE };
    render(<AccountProfile />);
    await userEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(
      screen.getByText(/PATCH \/v1\/me\/profile/),
    ).toBeInTheDocument();
    expect(screen.getByText(/UI-016.7-FU/)).toBeInTheDocument();
  });

  it('permite editar el nombre antes de guardar', async () => {
    mockSession = { profile: OWNER_PROFILE };
    render(<AccountProfile />);
    const nameInput = screen.getByLabelText('Nombre completo');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'Camila R.');
    expect(nameInput).toHaveValue('Camila R.');
  });

  it('si no hay session.profile usa fallback "Usuario" sin reventar', () => {
    mockSession = null;
    render(<AccountProfile />);
    expect(screen.getByText('Usuario')).toBeInTheDocument();
  });
});
