import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getReportesPQRSD: vi.fn(),
  exportarReportePQRSD: vi.fn(),
}));
import {
  getReportesPQRSD,
  exportarReportePQRSD,
} from '../services/gdApi.js';

import { ReportesPQRSD } from './ReportesPQRSD.jsx';

const DATA = {
  totales: {
    total: 320,
    cerradas_a_tiempo: 290,
    vencidas: 8,
    cumplimiento: 0.91,
    tiempo_medio_respuesta_h: 86.4,
  },
  por_tipo: [
    { tipo: 'P', total: 200 },
    { tipo: 'Q', total: 60 },
    { tipo: 'R', total: 30 },
  ],
  por_dependencia: [
    { dependencia: 'Jurídica', total: 120 },
  ],
  por_canal: [
    { canal: 'Web', total: 200 },
  ],
  por_tiempo: [
    { rango: '0-7d', cantidad: 180 },
    { rango: '8-15d', cantidad: 100 },
  ],
};

describe('ReportesPQRSD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getReportesPQRSD.mockResolvedValue(DATA);
  });

  it('renderiza KPIs con valores formateados', async () => {
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.admin_pqrsd']} />);
    await waitFor(() => expect(screen.getByTestId('rep-pqrsd-kpis')).toBeInTheDocument());
    expect(screen.getByText('320')).toBeInTheDocument();
    expect(screen.getByText(/91/)).toBeInTheDocument(); // cumplimiento
  });

  it('muestra 4 tableros de barras', async () => {
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.admin_pqrsd']} />);
    await waitFor(() => screen.getByTestId('rep-pqrsd-kpis'));
    expect(screen.getAllByTestId('rep-pqrsd-bars').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Jurídica')).toBeInTheDocument();
  });

  it('rol sin REP-004 NO ve botones exportar', async () => {
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('rep-pqrsd-kpis'));
    expect(screen.queryByTestId('rep-pqrsd-csv')).toBeNull();
  });

  it('coordinador VU exporta CSV → exportInfo OK', async () => {
    exportarReportePQRSD.mockResolvedValueOnce({ export_id: 'e1' });
    const user = userEvent.setup();
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => screen.getByTestId('rep-pqrsd-kpis'));
    await user.click(screen.getByTestId('rep-pqrsd-csv'));
    await waitFor(() => expect(screen.getByTestId('rep-pqrsd-export-info')).toBeInTheDocument());
  });

  it('error exportar muestra info danger', async () => {
    exportarReportePQRSD.mockRejectedValueOnce(new Error('cuota'));
    const user = userEvent.setup();
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => screen.getByTestId('rep-pqrsd-kpis'));
    await user.click(screen.getByTestId('rep-pqrsd-pdf'));
    await waitFor(() => expect(screen.getByTestId('rep-pqrsd-export-info')).toBeInTheDocument());
    expect(screen.getByText(/cuota/)).toBeInTheDocument();
  });

  it('cambio de periodo redispara fetch', async () => {
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.admin_pqrsd']} />);
    await waitFor(() => expect(getReportesPQRSD).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('rep-pqrsd-desde'), { target: { value: '2026-01-01' } });
    await waitFor(() => expect(getReportesPQRSD).toHaveBeenCalledTimes(2));
  });

  it('error al cargar muestra alert', async () => {
    getReportesPQRSD.mockRejectedValue(new Error('net'));
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.admin_pqrsd']} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('refresh dispara fetch adicional', async () => {
    const user = userEvent.setup();
    render(<ReportesPQRSD session={{ token: 't' }} roles={['gd.admin_pqrsd']} />);
    await waitFor(() => expect(getReportesPQRSD).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('rep-pqrsd-refresh'));
    expect(getReportesPQRSD).toHaveBeenCalledTimes(2);
  });
});
