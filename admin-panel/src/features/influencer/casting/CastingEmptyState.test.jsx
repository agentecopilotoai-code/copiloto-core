/**
 * UI-INFLU-003 — Tests para `CastingEmptyState`.
 *
 * Cubre los 3 criterios del backlog:
 *  1. Render del hero + CTA.
 *  2. CTA disabled para roles sin `influencer.personas.write` (Viewer/Agent).
 *  3. Click en CTA navega al wizard.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../permissions/index.js';
import { CastingEmptyState } from './CastingEmptyState.jsx';


function renderAt(path = '/t/acme/influencer') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/t/:tenantSlug/influencer" element={<CastingEmptyState />} />
        <Route
          path="/t/:tenantSlug/influencer/personas/new/step-1"
          element={<div>Wizard paso 1</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}


describe('<CastingEmptyState/>', () => {
  it('renderiza hero + CTA cuando el rol puede escribir', () => {
    usePermissions.mockReturnValue({ can: (cap) => cap === 'influencer.personas.write' });
    renderAt();
    expect(screen.getByText(/Tu casting está vacío/i)).toBeInTheDocument();
    expect(screen.getByText(/Aún no tienes personajes/i)).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: /Crear personaje/i });
    expect(cta).toBeEnabled();
  });

  it('CTA disabled cuando el rol NO tiene influencer.personas.write', () => {
    usePermissions.mockReturnValue({ can: () => false });
    renderAt();
    const cta = screen.getByRole('button', { name: /Crear personaje/i });
    expect(cta).toBeDisabled();
    expect(cta).toHaveAttribute(
      'title',
      expect.stringMatching(/permiso/i),
    );
  });

  it('al hacer click navega al wizard paso 1', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const user = userEvent.setup();
    renderAt();
    await user.click(screen.getByRole('button', { name: /Crear personaje/i }));
    expect(screen.getByText('Wizard paso 1')).toBeInTheDocument();
  });
});
