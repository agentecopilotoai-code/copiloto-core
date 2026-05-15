import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MfaRequiredBlocker } from './MfaRequiredBlocker.jsx';

describe('<MfaRequiredBlocker/> (UI-016.6 refactor)', () => {
  beforeEach(() => {
    // El formulario oculto persiste entre tests porque cada render lo crea de
    // nuevo en jsdom. Limpiar el DOM previo evita IDs duplicados.
    document.body.innerHTML = '';
  });

  it('muestra el heading del HTML T2', () => {
    render(<MfaRequiredBlocker />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'Activa autenticación de dos factores' }),
    ).toBeInTheDocument();
  });

  it('mantiene "Verificación en dos pasos" o equivalente como assertdialog accesible', () => {
    render(<MfaRequiredBlocker />);
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('expone el countdown estático de 7 días', () => {
    render(<MfaRequiredBlocker />);
    expect(screen.getByText(/7 días/)).toBeInTheDocument();
  });

  it('renderiza un form oculto que POST-ea a /admin/logout', () => {
    render(<MfaRequiredBlocker />);
    const form = document.getElementById('mfa-blocker-logout-form');
    expect(form).not.toBeNull();
    expect(form.getAttribute('method')).toBe('post');
    expect(form.getAttribute('action')).toMatch(/\/admin\/logout$/);
  });

  it('al hacer click en "Cerrar sesión" dispara form.submit() del logout', async () => {
    const submitSpy = vi
      .spyOn(HTMLFormElement.prototype, 'submit')
      .mockImplementation(() => {});
    render(<MfaRequiredBlocker />);
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
    expect(submitSpy).toHaveBeenCalledTimes(1);
    submitSpy.mockRestore();
  });

  it('"Configurar MFA →" también dispara el submit del logout (reto MFA en Auth0)', async () => {
    const submitSpy = vi
      .spyOn(HTMLFormElement.prototype, 'submit')
      .mockImplementation(() => {});
    render(<MfaRequiredBlocker />);
    await userEvent.click(screen.getByRole('button', { name: /Configurar MFA/ }));
    expect(submitSpy).toHaveBeenCalledTimes(1);
    submitSpy.mockRestore();
  });
});
