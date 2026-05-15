import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock coreApi so we control the get/update calls without spinning up the
// whole module graph. UI-022 didn't touch any endpoint — these mocks mirror
// the contract that already existed before the refactor.
vi.mock('../../../../services/coreApi.js', () => ({
  getKnowledgeStorageSettings: vi.fn(),
  updateKnowledgeStorageSettings: vi.fn(),
}));

// eslint-disable-next-line import/first
import {
  getKnowledgeStorageSettings,
  updateKnowledgeStorageSettings,
} from '../../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { KnowledgeStorageSettings } from './KnowledgeStorageSettings.jsx';

const MODULE = {
  label: 'Storage del Knowledge',
  summary:
    'Configura dónde se almacenan los documentos del bot. Compatible con S3 dedicado por tenant o storage local del entorno.',
};

const TENANT = { id: 'tenant-acme', label: 'Acme Co' };

const CONFIG_LOCAL = {
  backend: 'local',
  bucket: '',
  region: '',
  endpoint_url: '',
  prefix: 'tenants/tenant-acme/knowledge',
  access_key_id: '',
  effective_bucket: null,
  secret_configured: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  getKnowledgeStorageSettings.mockResolvedValue(CONFIG_LOCAL);
});

describe('KnowledgeStorageSettings', () => {
  it('renders the page header with the design-system primitive (h1)', async () => {
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    // PageHeader renders an <h1>. The legacy "Storage por tenant" eyebrow
    // copy must be gone — UI-022 alignment.
    expect(
      await screen.findByRole('heading', { name: 'Storage del Knowledge', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Storage por tenant')).toBeNull();
  });

  it('renders the form using <Button> primitives for the actions', async () => {
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    expect(
      await screen.findByRole('button', { name: 'Refrescar' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeInTheDocument();
  });

  it('renders the form fields wrapped in <FormField> labels', async () => {
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    expect(await screen.findByLabelText('Backend')).toBeInTheDocument();
    expect(screen.getByLabelText(/Bucket S3 del tenant/)).toBeInTheDocument();
    expect(screen.getByLabelText('Región')).toBeInTheDocument();
    expect(screen.getByLabelText('Endpoint S3 compatible')).toBeInTheDocument();
    expect(screen.getByLabelText('Prefix / carpeta lógica')).toBeInTheDocument();
    expect(screen.getByLabelText('Access Key ID')).toBeInTheDocument();
    expect(screen.getByLabelText('Secret Access Key')).toBeInTheDocument();
  });

  it('disables S3-specific inputs when backend is local', async () => {
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    await screen.findByLabelText('Backend');
    expect(screen.getByLabelText(/Bucket S3 del tenant/)).toBeDisabled();
    expect(screen.getByLabelText('Región')).toBeDisabled();
    expect(screen.getByLabelText('Access Key ID')).toBeDisabled();
  });

  it('enables S3-specific inputs after selecting the S3 backend', async () => {
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    const backend = await screen.findByLabelText('Backend');
    await userEvent.selectOptions(backend, 's3');
    expect(screen.getByLabelText(/Bucket S3 del tenant/)).not.toBeDisabled();
    expect(screen.getByLabelText('Endpoint S3 compatible')).not.toBeDisabled();
  });

  it('submits the form and surfaces the success notice via <AlertBanner>', async () => {
    updateKnowledgeStorageSettings.mockResolvedValue({
      ...CONFIG_LOCAL,
      backend: 'local',
    });
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    const save = await screen.findByRole('button', { name: 'Guardar' });
    await userEvent.click(save);
    await waitFor(() => {
      expect(updateKnowledgeStorageSettings).toHaveBeenCalledWith(
        {},
        'tenant-acme',
        expect.objectContaining({
          backend: 'local',
          prefix: 'tenants/tenant-acme/knowledge',
        }),
      );
    });
    expect(
      await screen.findByText(/Storage local activado para desarrollo\./),
    ).toBeInTheDocument();
  });

  it('renders the status sidebar with the effective configuration', async () => {
    render(
      <KnowledgeStorageSettings module={MODULE} session={{}} tenant={TENANT} />,
    );
    expect(
      await screen.findByRole('heading', { name: 'Estado actual', level: 3 }),
    ).toBeInTheDocument();
    expect(screen.getByText('Bucket efectivo')).toBeInTheDocument();
    expect(screen.getByText('Volumen local')).toBeInTheDocument();
    expect(screen.getByText('No configurado')).toBeInTheDocument();
  });
});
