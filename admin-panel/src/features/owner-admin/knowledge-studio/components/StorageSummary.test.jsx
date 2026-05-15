import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { StorageSummary, backendLabel, formatStorageSize } from './StorageSummary.jsx';

describe('formatStorageSize', () => {
  it('renders an em-dash for missing or invalid values', () => {
    expect(formatStorageSize(undefined)).toBe('—');
    expect(formatStorageSize(null)).toBe('—');
    expect(formatStorageSize(-1)).toBe('—');
    expect(formatStorageSize(Number.NaN)).toBe('—');
  });

  it('formats values in B / KB / MB / GB depending on magnitude', () => {
    expect(formatStorageSize(0)).toBe('0 B');
    expect(formatStorageSize(2048)).toBe('2 KB');
    expect(formatStorageSize(18.4 * 1024 * 1024)).toBe('18.4 MB');
    expect(formatStorageSize(2 * 1024 * 1024 * 1024)).toBe('2.0 GB');
  });
});

describe('backendLabel', () => {
  it('maps s3 → "S3 dedicado" with the success tone, anything else to neutral local', () => {
    expect(backendLabel('s3')).toEqual({ label: 'S3 dedicado', tone: 'success' });
    expect(backendLabel('local')).toEqual({ label: 'Local develop', tone: 'neutral' });
    expect(backendLabel(undefined)).toEqual({ label: 'Local develop', tone: 'neutral' });
  });
});

describe('StorageSummary', () => {
  it('renders the read-only summary tiles for an S3-backed tenant', () => {
    render(
      <StorageSummary
        storage={{
          backend: 's3',
          effective_bucket: 's3://copilotoia-kb-prod/clinica-est-norte/',
          secret_configured: true,
          total_bytes: 18.4 * 1024 * 1024,
          document_count: 7,
        }}
        documentCount={7}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Storage' })).toBeInTheDocument();
    expect(screen.getAllByText('S3 dedicado').length).toBeGreaterThan(0);
    expect(
      screen.getByText('s3://copilotoia-kb-prod/clinica-est-norte/'),
    ).toBeInTheDocument();
    expect(screen.getByText('Documentos').nextSibling.textContent).toContain('7');
    expect(screen.getByText('Tamaño').nextSibling.textContent).toContain('18.4 MB');
    expect(screen.getByText('Credenciales fuera de DB')).toBeInTheDocument();
  });

  it('falls back to the local backend copy when storage is null', () => {
    render(<StorageSummary storage={null} documentCount={3} />);
    expect(screen.getByRole('heading', { name: 'Storage' })).toBeInTheDocument();
    expect(screen.getAllByText('Local develop').length).toBeGreaterThan(0);
    expect(screen.getByText('Documentos').nextSibling.textContent).toContain('3');
    expect(screen.getByText('Tamaño').nextSibling.textContent).toContain('—');
  });

  it('shows a loading hint and surfaces an error when provided', () => {
    render(
      <StorageSummary
        storage={null}
        documentCount={0}
        isLoading
        error="Sin permisos para leer storage."
      />,
    );
    expect(screen.getByText('Cargando configuración de storage…')).toBeInTheDocument();
    expect(screen.getByText('Sin permisos para leer storage.')).toBeInTheDocument();
  });
});
