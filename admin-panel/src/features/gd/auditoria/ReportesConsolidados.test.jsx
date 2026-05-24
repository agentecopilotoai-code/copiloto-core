import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getReportesConsolidados: vi.fn(),
  exportarReporteConsolidado: vi.fn(),
  exportarReporteEjecutivoPdf: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { ReportesConsolidados } from './ReportesConsolidados.jsx';

const ROLES = ['gd.auditor'];
const DATA = {
  radicados_total: 1500, pqrsd_total: 320, pqrsd_vencidas: 12,
  documentos_total: 880, expedientes_nuevos: 45, expedientes_cerrados: 28,
  pqrsd_cumplimiento: 0.962, pqrsd_tiempo_medio_h: 36.4,
  por_dependencia: [
    { dependencia: 'Talento', radicados: 420, pqrsd: 80, documentos: 200,
      expedientes: 10, cumplimiento: 0.95 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getReportesConsolidados.mockResolvedValue(DATA);
});

describe('ReportesConsolidados', () => {
  it('KPIs + tabla por dependencia', async () => {
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('rep-kpis')).toBeInTheDocument());
    expect(screen.getByTestId('rep-dep-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('rep-kpi').length).toBeGreaterThanOrEqual(8);
  });

  it('error', async () => {
    api.getReportesConsolidados.mockRejectedValue(new Error('e'));
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('cambiar periodo dispara refetch', async () => {
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.getReportesConsolidados).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('rep-desde'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByTestId('rep-dep'), { target: { value: 'Talento' } });
    await waitFor(() => expect(api.getReportesConsolidados).toHaveBeenCalledTimes(3));
  });

  it('exportar CSV', async () => {
    api.exportarReporteConsolidado.mockResolvedValue({ url_descarga: 'https://x/r.csv' });
    const user = userEvent.setup();
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('rep-csv'));
    await waitFor(() => expect(screen.getByTestId('rep-export-info').textContent).toMatch(/csv/));
    expect(screen.getByTestId('rep-export-link')).toBeInTheDocument();
  });

  it('exportar PDF ejecutivo invoca endpoint distinto', async () => {
    api.exportarReporteEjecutivoPdf.mockResolvedValue({ url_descarga: 'https://x/r.pdf' });
    const user = userEvent.setup();
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('rep-pdf'));
    await waitFor(() => expect(api.exportarReporteEjecutivoPdf).toHaveBeenCalled());
    expect(api.exportarReporteConsolidado).not.toHaveBeenCalled();
    expect(screen.getByTestId('rep-export-info').textContent).toMatch(/firma institucional/);
  });

  it('exportar error', async () => {
    api.exportarReporteConsolidado.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('rep-csv'));
    await waitFor(() => expect(screen.getByTestId('rep-export-info').textContent).toMatch(/boom/));
  });

  it('sin permiso oculta exportar', async () => {
    render(<ReportesConsolidados session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('rep-kpis'));
    expect(screen.queryByTestId('rep-csv')).toBeNull();
    expect(screen.queryByTestId('rep-pdf')).toBeNull();
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<ReportesConsolidados session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('rep-kpis'));
    await user.click(screen.getByTestId('rep-refresh'));
    expect(api.getReportesConsolidados).toHaveBeenCalledTimes(2);
  });
});
