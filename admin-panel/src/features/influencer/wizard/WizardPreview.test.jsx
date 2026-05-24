/**
 * Tests para WizardPreview (UI-INFLU-014.8).
 *
 * Cubre el preview persistente de steps 2-5 del wizard:
 * - Preview vacío (sin variaciones) muestra placeholder + texto.
 * - Pending spinner cuando hay generación en vuelo.
 * - Render de variaciones existentes con canonical destacada.
 * - Click en variación llama onSelectVariation.
 * - Click en "Generar" llama onGenerate.
 * - disabled deshabilita el botón.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { WizardPreview } from './WizardPreview.jsx';


describe('<WizardPreview/>', () => {
  it('vacío: muestra placeholder "VISTA PREVIA" y texto de empty state', () => {
    render(<WizardPreview personaName="Sofía" variations={[]} />);
    expect(screen.getByText('VISTA PREVIA')).toBeInTheDocument();
    expect(screen.getByText(/Aún no se ha generado/i)).toBeInTheDocument();
    // GENERACIÓN #01 (default cuando ready.length === 0).
    expect(screen.getByText(/GENERACIÓN #01/i)).toBeInTheDocument();
  });

  it('pendingCount > 0 sin variaciones: spinner en preview + tile', () => {
    render(<WizardPreview personaName="X" pendingCount={2} />);
    const statuses = screen.getAllByRole('status');
    // Hay al menos un status (spinner del preview + tiles pending).
    expect(statuses.length).toBeGreaterThan(0);
  });

  it('con variaciones: la última se elige como activa y se muestra en preview', () => {
    const variations = [
      { id: 'v1', url: 'https://cdn/v1.png' },
      { id: 'v2', url: 'https://cdn/v2.png' },
    ];
    const { container } = render(<WizardPreview personaName="Sofía" variations={variations} />);
    // GENERACIÓN #02 — porque hay 2 ready.
    expect(screen.getByText(/GENERACIÓN #02/i)).toBeInTheDocument();
    // El <img> grande del preview viene del último (v2).
    const previewImg = container.querySelector('img[alt="Vista previa"]');
    expect(previewImg.getAttribute('src')).toBe('https://cdn/v2.png');
  });

  it('respeta canonical si está marcada', () => {
    const variations = [
      { id: 'v1', url: 'https://cdn/v1.png', canonical: true },
      { id: 'v2', url: 'https://cdn/v2.png' },
    ];
    const { container } = render(<WizardPreview variations={variations} />);
    const previewImg = container.querySelector('img[alt="Vista previa"]');
    expect(previewImg.getAttribute('src')).toBe('https://cdn/v1.png');
  });

  it('respeta marked_canonical (alias del campo)', () => {
    const variations = [
      { id: 'v1', url: 'https://cdn/v1.png' },
      { id: 'v2', url: 'https://cdn/v2.png', marked_canonical: true },
    ];
    const { container } = render(<WizardPreview variations={variations} />);
    const previewImg = container.querySelector('img[alt="Vista previa"]');
    expect(previewImg.getAttribute('src')).toBe('https://cdn/v2.png');
  });

  it('click en una variación llama onSelectVariation con su id', async () => {
    const variations = [
      { id: 'v1', url: 'https://cdn/v1.png' },
      { id: 'v2', url: 'https://cdn/v2.png' },
    ];
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<WizardPreview variations={variations} onSelectVariation={onSelect} />);
    // Click en la variación v1 — buscamos por su <img alt>.
    const v1Btn = screen.getByAltText('Variación v1').closest('button');
    await user.click(v1Btn);
    expect(onSelect).toHaveBeenCalledWith('v1');
  });

  it('botón "Generar" llama onGenerate', async () => {
    const onGenerate = vi.fn();
    const user = userEvent.setup();
    render(<WizardPreview onGenerate={onGenerate} />);
    await user.click(screen.getByRole('button', { name: /Generar nueva variación/i }));
    expect(onGenerate).toHaveBeenCalled();
  });

  it('disabled deshabilita el botón Generar', () => {
    render(<WizardPreview disabled />);
    const btn = screen.getByRole('button', { name: /Generar nueva variación/i });
    expect(btn).toBeDisabled();
  });

  it('filtra variaciones sin url', () => {
    const variations = [
      { id: 'v1', url: 'https://cdn/v1.png' },
      { id: 'v2' },  // sin url — se ignora
      { id: 'v3', url: 'https://cdn/v3.png' },
    ];
    render(<WizardPreview variations={variations} />);
    // Solo 2 variaciones reales → GENERACIÓN #02
    expect(screen.getByText(/GENERACIÓN #02/i)).toBeInTheDocument();
    // 2 thumbnails dentro de la lista
    const list = screen.getByLabelText('Variaciones');
    expect(list.querySelectorAll('img').length).toBe(2);
  });

  it('combina ready + pendingCount en la lista', () => {
    const variations = [{ id: 'v1', url: 'https://cdn/v1.png' }];
    render(<WizardPreview variations={variations} pendingCount={2} />);
    const list = screen.getByLabelText('Variaciones');
    // 1 thumbnail real + 2 placeholders pending = 3 <li>
    expect(list.querySelectorAll('li').length).toBe(3);
  });
});
