import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { NoModuleAccessScreen } from './NoModuleAccessScreen.jsx';

describe('<NoModuleAccessScreen/>', () => {
  it('pinta el heading + body explicativo', () => {
    render(<NoModuleAccessScreen />);
    expect(
      screen.getByRole('heading', { name: /Sin acceso a ningún módulo/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Contacta a la persona owner/i)).toBeInTheDocument();
  });

  it('expone el form POST oculto a /admin/logout', () => {
    render(<NoModuleAccessScreen />);
    const form = document.getElementById('no-module-access-logout-form');
    expect(form).toBeInstanceOf(HTMLFormElement);
    expect(form.method).toBe('post');
    expect(form.action).toMatch(/\/admin\/logout$/);
  });

  it('el CTA "Cerrar sesión" dispara el submit del form oculto', async () => {
    const submitSpy = vi
      .spyOn(HTMLFormElement.prototype, 'submit')
      .mockImplementation(() => {});
    render(<NoModuleAccessScreen />);
    await userEvent.click(screen.getByRole('button', { name: /Cerrar sesión/i }));
    expect(submitSpy).toHaveBeenCalled();
    submitSpy.mockRestore();
  });
});
