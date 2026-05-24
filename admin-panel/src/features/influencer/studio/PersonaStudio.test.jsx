import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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


describe('<PersonaStudio/> (redesign UI-INFLU-014.13)', () => {
  it('render con persona muestra nombre + título Estudio · generar', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: STUDIO_ACTIVE });
    // El nombre aparece en el header (eyebrow "SOFÍA / ESTUDIO") y en
    // el persona switcher. Aceptamos múltiples ocurrencias.
    expect(screen.getAllByText(/Sofía/i).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: /Estudio · generar/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /¿Qué quieres crear hoy\?/i })).toBeInTheDocument();
  });

  it('muestra las 5 tarjetas de formato (Foto / Reel / Carrusel / Historia / Anuncio)', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: STUDIO_ACTIVE });
    const list = screen.getByLabelText('Tipo de contenido');
    expect(list).toBeInTheDocument();
    // Cada label aparece dentro de la lista
    ['Foto', 'Reel', 'Carrusel', 'Historia', 'Anuncio'].forEach((name) => {
      expect(screen.getAllByText(new RegExp(`^${name}$`, 'i')).length).toBeGreaterThan(0);
    });
  });

  it('panel Ajustes muestra formato/cantidad/estilo/locación/modo seguro', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: STUDIO_ACTIVE });
    expect(screen.getByLabelText('Ajustes de generación')).toBeInTheDocument();
    expect(screen.getByLabelText('Cantidad')).toBeInTheDocument();
    expect(screen.getByLabelText('Estilo visual')).toBeInTheDocument();
    expect(screen.getByLabelText('Modo seguro')).toBeChecked();
  });

  it('CTA grande "Generar · N imágenes" llama onGenerate con el payload', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const onGenerate = vi.fn().mockResolvedValue({ generation_id: 'g99' });
    const user = userEvent.setup();
    renderStudio({ studio: STUDIO_ACTIVE, onGenerate, balance: 1000 });
    await user.click(screen.getByRole('button', { name: /Generar · 4 imágenes/i }));
    expect(onGenerate).toHaveBeenCalled();
    const call = onGenerate.mock.calls[0][0];
    expect(call.kind).toBe('photo');
    expect(call.format).toBe('1:1');
    expect(call.count).toBe(4);
  });

  it('cambia de formato (Reel) y el subtítulo del panel se actualiza', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const user = userEvent.setup();
    renderStudio({ studio: STUDIO_ACTIVE });
    // Click en el botón de la card Reel — buscamos el botón con aria-pressed
    // (FormatCard usa aria-pressed). El primer botón de tipo es Foto, el
    // segundo es Reel.
    const cards = screen.getAllByRole('button', { pressed: false });
    // Encontrar la card con label "Reel"
    const reelCard = cards.find((b) => /Reel/.test(b.textContent || ''));
    expect(reelCard).toBeTruthy();
    await user.click(reelCard);
    // Reel solo permite 9:16 — el botón 9:16 está aria-pressed
    expect(screen.getByRole('button', { name: '9:16', pressed: true })).toBeInTheDocument();
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

  it('CTA "Generar contenido" (legacy) visible para Manager con generate capability', () => {
    usePermissions.mockReturnValue({
      can: (cap) => cap === 'influencer.generate' || cap === 'influencer.personas.write',
    });
    renderStudio({ studio: STUDIO_ACTIVE });
    expect(screen.getByRole('button', { name: /Generar contenido/i })).toBeInTheDocument();
  });

  it('CTA "Generar contenido" oculto sin influencer.generate', () => {
    usePermissions.mockReturnValue({ can: () => false });
    renderStudio({ studio: STUDIO_ACTIVE });
    expect(screen.queryByRole('button', { name: /Generar contenido/i })).not.toBeInTheDocument();
  });

  it('KPIs compactos al final muestran los números del bundle', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderStudio({ studio: STUDIO_ACTIVE });
    expect(screen.getByText('184')).toBeInTheDocument();
    expect(screen.getByText('2.4M')).toBeInTheDocument();
    expect(screen.getByText('8.4%')).toBeInTheDocument();
  });
});
