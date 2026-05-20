import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { PublicLandingShell } from './PublicLandingShell.jsx';


function renderShell(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<PublicLandingShell activeTab="ravit" />} />
        <Route path="/copiloto" element={<PublicLandingShell activeTab="copiloto" />} />
      </Routes>
    </MemoryRouter>,
  );
}


describe('<PublicLandingShell/> (UI-INFLU-016)', () => {
  it('/ renderiza shell con tab Ravit activo y hero del Pulse', () => {
    renderShell('/');
    expect(screen.getByTestId('public-landing-shell')).toBeInTheDocument();
    expect(screen.getByTestId('ravit-agent-pulse')).toBeInTheDocument();
    expect(screen.getByText(/Influencers de IA/i)).toBeInTheDocument();
    const ravitTab = screen.getByRole('link', { name: /Ravit Agent · Pulse/i });
    expect(ravitTab).toHaveAttribute('aria-current', 'page');
  });

  it('/copiloto renderiza shell con tab CopilotoIA activo y monta Landing embedded', () => {
    renderShell('/copiloto');
    expect(screen.getByTestId('public-landing')).toBeInTheDocument();
    expect(screen.queryByTestId('ravit-agent-pulse')).not.toBeInTheDocument();
    const copTab = screen.getByRole('link', { name: 'CopilotoIA' });
    expect(copTab).toHaveAttribute('aria-current', 'page');
  });

  it('CTA "Solicitar demo" abre modal con form + submit dispara onDemoRequest', async () => {
    const onDemoRequest = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<PublicLandingShell activeTab="ravit" onDemoRequest={onDemoRequest} />} />
        </Routes>
      </MemoryRouter>,
    );
    const buttons = screen.getAllByRole('button', { name: /Solicitar demo/i });
    await user.click(buttons[0]);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Nombre/i), 'Sofia');
    await user.type(screen.getByLabelText(/Email/i), 'sofia@example.com');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(onDemoRequest).toHaveBeenCalledOnce();
    expect(onDemoRequest.mock.calls[0][0]).toMatchObject({ name: 'Sofia', email: 'sofia@example.com' });
  });

  it('CTA "Iniciar sesión" usa loginHref como destino', () => {
    render(
      <MemoryRouter>
        <PublicLandingShell activeTab="ravit" loginHref="/login-test" />
      </MemoryRouter>,
    );
    const loginLinks = screen.getAllByRole('link', { name: /Iniciar sesión/i });
    expect(loginLinks[0]).toHaveAttribute('href', '/login-test');
  });

  it('tabs son visibles en ambas pestañas', () => {
    renderShell('/copiloto');
    expect(screen.getByRole('link', { name: /Ravit Agent · Pulse/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'CopilotoIA' })).toBeInTheDocument();
  });
});
