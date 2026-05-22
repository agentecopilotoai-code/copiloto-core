import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { WizardPreview } from './WizardPreview.jsx';

const READY_VARIATIONS = [
  { id: 'v1', url: '/img/v1.png', status: 'ready' },
  { id: 'v2', url: '/img/v2.png', status: 'ready' },
];

describe('<WizardPreview/> (UI-INFLU-014.1)', () => {
  it('muestra el botón Generar con costo +1', () => {
    render(<WizardPreview onGenerate={() => {}} />);
    const btn = screen.getByRole('button', { name: /generar nueva variación/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveTextContent('Generar');
    expect(btn).toHaveTextContent('+1');
    // El botón NO contiene la palabra "crédito" (decisión UX del usuario).
    expect(btn.textContent).not.toMatch(/crédito/i);
  });

  it('llama onGenerate al hacer click en el botón', () => {
    const onGenerate = vi.fn();
    render(<WizardPreview onGenerate={onGenerate} />);
    fireEvent.click(screen.getByRole('button', { name: /generar nueva variación/i }));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it('auto-selecciona la última variación lista en el preview grande', () => {
    render(
      <WizardPreview variations={READY_VARIATIONS} onGenerate={() => {}} />,
    );
    // El alt del img grande debe ser "Variación 2 de …" (la última).
    expect(screen.getByAltText(/Variación 2 de/i)).toBeInTheDocument();
  });

  it('respeta selectedIndex explícito sobre el auto-select', () => {
    render(
      <WizardPreview
        variations={READY_VARIATIONS}
        selectedIndex={0}
        onGenerate={() => {}}
      />,
    );
    expect(screen.getByAltText(/Variación 1 de/i)).toBeInTheDocument();
  });

  it('llama onSelectVariation al hacer click en un thumbnail', () => {
    const onSelect = vi.fn();
    render(
      <WizardPreview
        variations={READY_VARIATIONS}
        onSelectVariation={onSelect}
        onGenerate={() => {}}
      />,
    );
    const thumbs = screen.getAllByRole('button', { name: /Seleccionar variación/i });
    fireEvent.click(thumbs[0]);
    expect(onSelect).toHaveBeenCalledWith(0);
  });

  it('muestra placeholders con spinner cuando pendingCount > 0', () => {
    render(
      <WizardPreview
        variations={READY_VARIATIONS}
        pendingCount={2}
        onGenerate={() => {}}
      />,
    );
    // 2 thumbnails ready + 2 placeholders pending = 4 total
    const pendingThumbs = screen.getAllByRole('button', {
      name: /Variación en generación/i,
    });
    expect(pendingThumbs).toHaveLength(2);
    pendingThumbs.forEach((thumb) => expect(thumb).toBeDisabled());
  });

  it('muestra spinner grande centrado cuando no hay variations pero pendingCount > 0', () => {
    render(<WizardPreview pendingCount={1} onGenerate={() => {}} />);
    // El preview grande contiene un status role con label "Generando primera variación…"
    expect(screen.getByRole('status', { name: /Generando primera variación/i }))
      .toBeInTheDocument();
  });

  it('muestra texto vacío cuando no hay variaciones ni pending', () => {
    render(<WizardPreview onGenerate={() => {}} />);
    expect(screen.getByText(/Aún no has generado/i)).toBeInTheDocument();
    expect(screen.getByText(/Configura los rasgos/i)).toBeInTheDocument();
  });

  it('renderiza el overlay GENERACIÓN + nombre del personaje', () => {
    render(
      <WizardPreview
        personaName="Sofía Vega"
        generationNumber={4}
        variations={READY_VARIATIONS}
        onGenerate={() => {}}
      />,
    );
    expect(screen.getByText('GENERACIÓN #04')).toBeInTheDocument();
    expect(screen.getByText('Sofía Vega')).toBeInTheDocument();
  });

  it('deshabilita el botón cuando disabled=true', () => {
    render(<WizardPreview disabled onGenerate={() => {}} />);
    const btn = screen.getByRole('button', { name: /generar nueva variación/i });
    expect(btn).toBeDisabled();
  });
});
