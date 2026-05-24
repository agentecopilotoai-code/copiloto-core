import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getConfigSeguridad: vi.fn(),
  actualizarConfigSeguridad: vi.fn(),
  listSesionesActivas: vi.fn(),
  revocarSesion: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Seguridad } from './Seguridad.jsx';

const ROLES_PWD = ['gd.admin_seguridad'];

const CFG = {
  password: { pwd_min_length: 12, pwd_expira_dias: 90,
    pwd_require_upper: true, pwd_require_number: true, pwd_require_symbol: true },
  mfa: { mfa_obligatorio: false, mfa_metodo: 'totp', mfa_grace_dias: 7 },
};
const SES = {
  id: 'ses1', usuario_email: 'ana@x.gov.co', ip: '10.1.1.1',
  user_agent: 'Chrome 121 muy largo agent user', iniciada_en: '2026-05-23 10:00',
};

describe('Seguridad', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getConfigSeguridad.mockResolvedValue(CFG);
    api.listSesionesActivas.mockResolvedValue({ items: [SES] });
  });

  it('renderiza tabs y Política por default', async () => {
    render(<Seguridad session={{ token: 't' }} roles={ROLES_PWD} />);
    await waitFor(() => expect(screen.getByTestId('seg-tabs')).toBeInTheDocument());
    expect(screen.getByTestId('seg-pol')).toBeInTheDocument();
  });

  it('guardar política con motivo', async () => {
    api.actualizarConfigSeguridad.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Seguridad session={{ token: 't' }} roles={ROLES_PWD} />);
    await waitFor(() => screen.getByTestId('seg-pol'));
    fireEvent.change(screen.getByTestId('seg-pwd-min'), { target: { value: '14' } });
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'fortalecimiento por incidente' } });
    await user.click(screen.getByTestId('seg-pol-guardar'));
    await waitFor(() => expect(api.actualizarConfigSeguridad).toHaveBeenCalled());
  });

  it('política error', async () => {
    api.actualizarConfigSeguridad.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Seguridad session={{ token: 't' }} roles={ROLES_PWD} />);
    await waitFor(() => screen.getByTestId('seg-pol'));
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'cambio operativo válido' } });
    await user.click(screen.getByTestId('seg-pol-guardar'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('tab MFA + guardar', async () => {
    api.actualizarConfigSeguridad.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Seguridad session={{ token: 't' }} roles={ROLES_PWD} />);
    await user.click(await screen.findByTestId('seg-tab-btn-MFA'));
    expect(screen.getByTestId('seg-mfa')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('seg-mfa-obl'));
    fireEvent.change(screen.getByTestId('seg-mfa-metodo'), { target: { value: 'email' } });
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'política obligatoria nueva' } });
    await user.click(screen.getByTestId('seg-mfa-guardar'));
    await waitFor(() => expect(api.actualizarConfigSeguridad).toHaveBeenCalled());
  });

  it('tab Sesiones con permiso muestra tabla y revoca', async () => {
    api.revocarSesion.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Seguridad session={{ token: 't' }} roles={['gd.admin_seguridad']} />);
    await user.click(await screen.findByTestId('seg-tab-btn-Sesiones activas'));
    await waitFor(() => expect(screen.getByTestId('seg-ses-table')).toBeInTheDocument());
    await user.click(screen.getByTestId('seg-ses-revocar'));
    fireEvent.change(screen.getByLabelText(/Motivo de la revocación/i), { target: { value: 'comportamiento sospechoso' } });
    await user.click(screen.getByTestId('seg-ses-revocar-submit'));
    await waitFor(() => expect(api.revocarSesion).toHaveBeenCalled());
  });

  it('tab Sesiones sin permiso', async () => {
    const user = userEvent.setup();
    render(<Seguridad session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await user.click(await screen.findByTestId('seg-tab-btn-Sesiones activas'));
    expect(screen.getByTestId('seg-ses-no-perm')).toBeInTheDocument();
  });

  it('sesiones empty', async () => {
    api.listSesionesActivas.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<Seguridad session={{ token: 't' }} roles={['gd.admin_seguridad']} />);
    await user.click(await screen.findByTestId('seg-tab-btn-Sesiones activas'));
    await waitFor(() => expect(screen.getByTestId('seg-ses-empty')).toBeInTheDocument());
  });
});
