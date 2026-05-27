import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  detectarPiiIa: vi.fn(),
  reportarFalsoPositivoPii: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { DeteccionPII, DeteccionPIIInline } from './DeteccionPII.jsx';

const HALLAZGO = {
  detectado: true,
  hallazgos: [
    { id: 'h1', tipo: 'cedula', severidad: 'alta',
      categoria_ley1581: 'identificacion', valor_redactado: '****12' },
    { id: 'h2', tipo: 'email', severidad: 'baja',
      valor_redactado: 'j**@gmail.com' },
  ],
};

beforeEach(() => vi.clearAllMocks());

describe('DeteccionPIIInline', () => {
  it('sin permiso → no render', () => {
    const { container } = render(
      <DeteccionPIIInline session={{}} roles={[]} contenido="x" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('escanea y muestra hallazgos', async () => {
    api.detectarPiiIa.mockResolvedValue(HALLAZGO);
    const onHallazgos = vi.fn();
    const user = userEvent.setup();
    render(
      <DeteccionPIIInline session={{ token: 't' }}
        roles={['gd.profesional']} contenido="CC 1234"
        onHallazgos={onHallazgos} />,
    );
    await user.click(screen.getByTestId('ia-pii-escanear'));
    await waitFor(() => screen.getByTestId('ia-pii-resultado'));
    expect(screen.getByTestId('ia-pii-aviso')).toBeInTheDocument();
    expect(screen.getAllByTestId('ia-pii-item')).toHaveLength(2);
    expect(onHallazgos).toHaveBeenCalled();
  });

  it('sin hallazgos muestra success', async () => {
    api.detectarPiiIa.mockResolvedValue({ detectado: false, hallazgos: [] });
    const user = userEvent.setup();
    render(
      <DeteccionPIIInline session={{ token: 't' }}
        roles={['gd.profesional']} contenido="x" />,
    );
    await user.click(screen.getByTestId('ia-pii-escanear'));
    await waitFor(() => screen.getByTestId('ia-pii-limpio'));
  });

  it('error', async () => {
    api.detectarPiiIa.mockRejectedValue(new Error('falló'));
    const user = userEvent.setup();
    render(
      <DeteccionPIIInline session={{ token: 't' }}
        roles={['gd.profesional']} contenido="x" />,
    );
    await user.click(screen.getByTestId('ia-pii-escanear'));
    await waitFor(() => expect(screen.getByTestId('ia-pii-error').textContent).toMatch(/falló/));
  });

  it('reporta falso positivo', async () => {
    api.detectarPiiIa.mockResolvedValue(HALLAZGO);
    api.reportarFalsoPositivoPii.mockResolvedValue({});
    const user = userEvent.setup();
    render(
      <DeteccionPIIInline session={{ token: 't' }}
        roles={['gd.profesional']} contenido="CC 1234" />,
    );
    await user.click(screen.getByTestId('ia-pii-escanear'));
    await waitFor(() => screen.getAllByTestId('ia-pii-fp'));
    await user.click(screen.getAllByTestId('ia-pii-fp')[0]);
    await waitFor(() => expect(api.reportarFalsoPositivoPii).toHaveBeenCalled());
  });

  it('reporta falso positivo con error swallow', async () => {
    api.detectarPiiIa.mockResolvedValue(HALLAZGO);
    api.reportarFalsoPositivoPii.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(
      <DeteccionPIIInline session={{ token: 't' }}
        roles={['gd.profesional']} contenido="CC 1234" />,
    );
    await user.click(screen.getByTestId('ia-pii-escanear'));
    await waitFor(() => screen.getAllByTestId('ia-pii-fp'));
    await user.click(screen.getAllByTestId('ia-pii-fp')[0]);
    // No re-throw — UI sigue mostrando el item.
    await waitFor(() => expect(api.reportarFalsoPositivoPii).toHaveBeenCalled());
  });
});

describe('DeteccionPII (vista standalone)', () => {
  it('sin permiso muestra aviso', () => {
    render(<DeteccionPII session={{}} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('ia-pii-no-perm')).toBeInTheDocument();
  });

  it('admin_seguridad puede ver textarea', () => {
    render(<DeteccionPII session={{ token: 't' }} roles={['gd.admin_seguridad']} />);
    expect(screen.getByTestId('ia-pii-textarea')).toBeInTheDocument();
  });

  it('al escribir aparece análisis inline', async () => {
    const user = userEvent.setup();
    render(<DeteccionPII session={{ token: 't' }} roles={['gd.admin_seguridad']} />);
    await user.type(screen.getByTestId('ia-pii-textarea'), 'CC 1234');
    expect(screen.getByTestId('ia-pii-inline')).toBeInTheDocument();
  });
});
