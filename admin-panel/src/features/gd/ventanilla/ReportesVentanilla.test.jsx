import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getReportesVentanilla: vi.fn(),
  exportarReporteVentanilla: vi.fn(),
}));
import {
  getReportesVentanilla,
  exportarReporteVentanilla,
} from '../services/gdApi.js';

import { ReportesVentanilla } from './ReportesVentanilla.jsx';

const DATA = {
  totales: { radicados: 247, anulaciones: 3, reasignaciones: 12, tiempo_medio_cierre_h: 36 },
  por_canal: [
    { canal: 'Web', total: 150 },
    { canal: 'Presencial', total: 60 },
    { canal: 'Correo', total: 37 },
  ],
  por_dependencia: [
    { dependencia: 'Jurídica', total: 80 },
    { dependencia: 'Talento', total: 50 },
  ],
  anulaciones_por_motivo: [
    { motivo: 'Duplicado', total: 2 },
    { motivo: 'Error de canal', total: 1 },
  ],
};

describe('ReportesVentanilla', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getReportesVentanilla.mockResolvedValue(DATA);
  });

  it('renderiza KPIs cuando llega data', async () => {
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => expect(screen.getByTestId('rep-kpis')).toBeInTheDocument());
    expect(screen.getByText('247')).toBeInTheDocument();
  });

  it('muestra barras por canal y por dep', async () => {
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => screen.getByTestId('rep-kpis'));
    expect(screen.getAllByTestId('simple-bars').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Web')).toBeInTheDocument();
    expect(screen.getByText('Jurídica')).toBeInTheDocument();
  });

  it('rol sin PERM-REP-004 NO ve botones exportar', async () => {
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('rep-kpis'));
    expect(screen.queryByTestId('rep-exportar-csv')).toBeNull();
  });

  it('coordinador VU ve botones y exportar muestra info', async () => {
    exportarReporteVentanilla.mockResolvedValueOnce({ export_id: 'e1' });
    const user = userEvent.setup();
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => screen.getByTestId('rep-kpis'));
    await user.click(screen.getByTestId('rep-exportar-csv'));
    await waitFor(() => expect(screen.getByTestId('rep-export-info')).toBeInTheDocument());
  });

  it('exportar error muestra info de error', async () => {
    exportarReporteVentanilla.mockRejectedValueOnce(new Error('quota'));
    const user = userEvent.setup();
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => screen.getByTestId('rep-kpis'));
    await user.click(screen.getByTestId('rep-exportar-pdf'));
    await waitFor(() => expect(screen.getByTestId('rep-export-info')).toBeInTheDocument());
    expect(screen.getByText(/quota/)).toBeInTheDocument();
  });

  it('cambio de periodo redispara fetch', async () => {
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => expect(getReportesVentanilla).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('rep-desde'), { target: { value: '2026-01-01' } });
    await waitFor(() => expect(getReportesVentanilla).toHaveBeenCalledTimes(2));
  });

  it('error carga muestra alert', async () => {
    getReportesVentanilla.mockRejectedValueOnce(new Error('net'));
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('refresh dispara fetch adicional', async () => {
    const user = userEvent.setup();
    render(<ReportesVentanilla session={{ token: 't' }} roles={['gd.coordinador_vu']} />);
    await waitFor(() => expect(getReportesVentanilla).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('rep-refresh'));
    expect(getReportesVentanilla).toHaveBeenCalledTimes(2);
  });
});
