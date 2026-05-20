import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../permissions/index.js';
import { PersonaStudio } from './PersonaStudio.jsx';


function renderStudio(props) {
  return render(
    <MemoryRouter initialEntries={['/t/acme/influencer/personas/p1/studio']}>
      <Routes>
        <Route
          path="/t/:tenantSlug/influencer/personas/:personaId/studio"
          element={<PersonaStudio {...props} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}


const STUDIO_ACTIVE = {
  persona: {
    id: 'p1', name: 'Sofía', handle: 'sofia',
    status: 'active', voice: { tone: 'cálida', style_tokens: ['resort wear'] },
  },
  stats: { posts_total: 184, reach_30d: 2_400_000, engagement_rate: 0.084, scheduled_count: 12 },
  next_post: { at: new Date(Date.now() + 86_400_000).toISOString(), kind: 'reel', platforms: ['ig'] },
  platforms_connected: [
    { platform: 'instagram', external_handle: '@sofia.studio', status: 'connected' },
  ],
  recent_generations: [
    { id: 'g1', kind: 'photo', status: 'succeeded', created_at: '2026-05-19T10:00:00Z' },
  ],
};


describe('<PersonaStudio/>', () => {
  it('render con persona activa muestra nombre + status + KPIs', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: STUDIO_ACTIVE });
    // 'Sofía' aparece en el header del PageHeader y en el header de la
    // Card — basta con verificar que está presente al menos 1 vez.
    expect(screen.getAllByText('Sofía').length).toBeGreaterThan(0);
    expect(screen.getByText(/ACTIVO · 12 PROGRAMADOS/)).toBeInTheDocument();
    expect(screen.getByText('184')).toBeInTheDocument();
    expect(screen.getByText('2.4M')).toBeInTheDocument();
    expect(screen.getByText('8.4%')).toBeInTheDocument();
  });

  it('estado loading muestra mensaje', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: null, loading: true });
    expect(screen.getByText(/Cargando estudio/i)).toBeInTheDocument();
  });

  it('not-found / sin persona muestra el empty state', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: null, error: 'not_found' });
    expect(screen.getByText(/Personaje no disponible/i)).toBeInTheDocument();
  });

  it('CTA Generar visible para Manager con generate capability', () => {
    usePermissions.mockReturnValue({
      can: (cap) => cap === 'influencer.generate' || cap === 'influencer.personas.write',
    });
    renderStudio({ studio: STUDIO_ACTIVE });
    expect(screen.getByRole('button', { name: /Generar contenido/i })).toBeInTheDocument();
  });

  it('CTA Generar oculto sin influencer.generate', () => {
    usePermissions.mockReturnValue({ can: () => false });
    renderStudio({ studio: STUDIO_ACTIVE });
    expect(screen.queryByRole('button', { name: /Generar contenido/i })).not.toBeInTheDocument();
  });
});
