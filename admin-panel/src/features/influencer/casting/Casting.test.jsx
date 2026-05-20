/**
 * UI-INFLU-004 — Tests del orquestador `Casting`.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../permissions/index.js';
import { Casting } from './Casting.jsx';


function makePersonas(n = 6) {
  const categories = ['fashion', 'beauty', 'lifestyle', 'editorial', 'beach', 'travel'];
  return Array.from({ length: n }, (_, i) => ({
    id: `p${i + 1}`,
    name: `Persona ${i + 1}`,
    handle: `persona${i + 1}`,
    status: i < 4 ? 'active' : 'paused',
    category: categories[i % categories.length],
    posts_total: 10 * (i + 1),
    reach_30d: 1000 * (i + 1),
    engagement_rate: 0.01 * (i + 1),
  }));
}


function renderCasting(casting) {
  return render(
    <MemoryRouter initialEntries={['/t/acme/influencer/casting']}>
      <Routes>
        <Route path="/t/:tenantSlug/influencer/casting" element={<Casting casting={casting} />} />
        <Route
          path="/t/:tenantSlug/influencer/personas/:personaId/studio"
          element={<div>Studio detail page</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}


describe('<Casting/>', () => {
  it('render con 6 personajes muestra KPIs + filtros + grid', () => {
    usePermissions.mockReturnValue({ can: () => true });
    const personas = makePersonas(6);
    renderCasting({
      kpis: {
        active_personas: 4, posts_this_month: 32,
        total_reach: 25000, avg_engagement: 0.045,
      },
      personas,
    });

    // KPIs
    expect(screen.getByText('Personajes activos')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('25K')).toBeInTheDocument();
    expect(screen.getByText('4.5%')).toBeInTheDocument();

    // Filtros
    expect(screen.getByRole('button', { name: 'Todos' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /Ordenar personajes/i })).toBeInTheDocument();

    // Grid — 6 cards (cada PersonaCard tiene role=article)
    expect(screen.getAllByRole('article')).toHaveLength(6);
  });

  it('click en chip Fashion filtra a las personas de esa categoría', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const personas = makePersonas(6);
    const user = userEvent.setup();
    renderCasting({ kpis: {}, personas });

    // Antes del filter: 6 cards
    expect(screen.getAllByRole('article')).toHaveLength(6);

    await user.click(screen.getByRole('button', { name: 'Fashion' }));

    // Después: las del category=fashion (1)
    const articles = screen.getAllByRole('article');
    expect(articles.length).toBeLessThan(6);
    expect(articles.length).toBeGreaterThanOrEqual(1);
  });

  it('click en card navega al studio del personaje', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const personas = makePersonas(2);
    const user = userEvent.setup();
    renderCasting({ kpis: {}, personas });

    const opener = screen.getAllByRole('button', { name: /Abrir estudio de Persona 1/i })[0];
    await user.click(opener);
    expect(screen.getByText('Studio detail page')).toBeInTheDocument();
  });

  it('sin influencer.personas.read renderiza el empty state', () => {
    usePermissions.mockReturnValue({ can: () => false });
    renderCasting({ kpis: {}, personas: makePersonas(3) });
    // El empty state se identifica por su texto distintivo.
    expect(screen.getByText(/Tu casting está vacío/i)).toBeInTheDocument();
  });
});
