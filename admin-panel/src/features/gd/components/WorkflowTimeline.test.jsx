import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WorkflowTimeline } from './WorkflowTimeline.jsx';

const EV = (over = {}) => ({
  id: 'e1',
  tipo_evento: 'RadicadoCreado',
  criticidad: 'media',
  actor_nombre: 'María Pérez',
  actor_rol: 'gd.radicador',
  actor_dependencia_nombre: 'Ventanilla',
  accion: 'crear',
  created_at: '2026-05-23T10:00:00Z',
  ...over,
});

describe('WorkflowTimeline', () => {
  it('loading muestra mensaje', () => {
    render(<WorkflowTimeline loading />);
    expect(screen.getByText(/Cargando trazabilidad/)).toBeInTheDocument();
  });

  it('error muestra alert con mensaje', () => {
    render(<WorkflowTimeline error={new Error('No conecta')} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('No conecta')).toBeInTheDocument();
  });

  it('error sin message usa fallback', () => {
    render(<WorkflowTimeline error={{}} />);
    expect(screen.getByText(/Intente nuevamente/)).toBeInTheDocument();
  });

  it('vacío muestra empty', () => {
    render(<WorkflowTimeline events={[]} />);
    expect(screen.getByTestId('timeline-empty')).toBeInTheDocument();
  });

  it('lista eventos con actor + dep + criticidad', () => {
    render(<WorkflowTimeline events={[EV(), EV({ id: 'e2', criticidad: 'alta' })]} />);
    expect(screen.getByTestId('workflow-timeline')).toBeInTheDocument();
    expect(screen.getAllByText('RadicadoCreado')).toHaveLength(2);
    expect(screen.getAllByText(/María Pérez/)).toHaveLength(2);
    expect(screen.getByText('alta')).toBeInTheDocument();
  });

  it('justificación se muestra cuando existe', () => {
    render(
      <WorkflowTimeline
        events={[EV({ justificacion: 'cambio de canal' })]}
      />,
    );
    expect(screen.getByText(/cambio de canal/)).toBeInTheDocument();
  });

  it('sin criticidad usa media por default visual', () => {
    render(<WorkflowTimeline events={[EV({ criticidad: undefined })]} />);
    expect(screen.getByText('media')).toBeInTheDocument();
  });

  it('actor_nombre nulo → "Sistema"', () => {
    render(<WorkflowTimeline events={[EV({ actor_nombre: null })]} />);
    expect(screen.getByText(/Sistema/)).toBeInTheDocument();
  });
});
