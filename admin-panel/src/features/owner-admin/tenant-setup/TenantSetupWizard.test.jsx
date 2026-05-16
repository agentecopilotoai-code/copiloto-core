import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  createContactTag: vi.fn(),
  createTenant: vi.fn(),
  deleteContactTag: vi.fn(),
  getRetentionPreview: vi.fn(),
  getTenant: vi.fn(),
  getTenantPaymentSettings: vi.fn(),
  getTenantSettings: vi.fn(),
  listAuditLogs: vi.fn(),
  listContactTags: vi.fn(),
  listRetentionPolicies: vi.fn(),
  patchTenantStatus: vi.fn(),
  reindexAllKnowledgeDocuments: vi.fn(),
  updateContactTag: vi.fn(),
  updateRetentionPolicies: vi.fn(),
  updateTenant: vi.fn(),
  updateTenantPaymentSettings: vi.fn(),
  updateTenantSettings: vi.fn(),
  createDigestSubscription: vi.fn(),
  deleteDigestSubscription: vi.fn(),
  listDigestSubscriptions: vi.fn(),
  updateDigestSubscription: vi.fn(),
  createQualificationQuestion: vi.fn(),
  deleteQualificationQuestion: vi.fn(),
  listQualificationQuestions: vi.fn(),
  listServices: vi.fn(),
  reorderQualificationQuestions: vi.fn(),
  updateQualificationQuestion: vi.fn(),
  listBranches: vi.fn(),
  createBranch: vi.fn(),
  updateBranch: vi.fn(),
  deleteBranch: vi.fn(),
  uploadTenantBrandLogo: vi.fn(),
}));

// Mock TenantProvider so `usePermissions` resolves with an owner role via
// `profile.support_mode` (no tenant required). Owner gets RW on
// `tenant_setup.write`, which is the gate UI-021 added at the wizard root.
vi.mock('../../../app/TenantProvider.jsx', () => {
  const ctx = {
    profile: { sub: 'u-owner', support_mode: true, roles: ['owner'] },
  };
  return {
    useTenantContext: () => ctx,
    useOptionalTenantContext: () => ctx,
  };
});

// eslint-disable-next-line import/first
import { TenantSetupWizard } from './TenantSetupWizard.jsx';

const MODULE = { label: 'Tenant Setup', summary: 'Configuración general del tenant.' };

function setup() {
  // No tenant: keeps `currentTenantId` null so the side-panel fetch effects
  // (payments / retention) early-return — same shape as the original test.
  return render(<TenantSetupWizard module={MODULE} session={{}} tenant={undefined} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('TenantSetupWizard', () => {
  it('renders the page header and the full tab nav using design-system primitives', () => {
    setup();
    // PageHeader renders an <h1>, replacing the legacy "Wizard MVP" eyebrow.
    expect(screen.getByRole('heading', { name: 'Tenant Setup', level: 1 })).toBeInTheDocument();
    // No more MVP copy — UI-021 alignment.
    expect(screen.queryByText('Wizard MVP')).toBeNull();
    // Tab nav from the `<Tabs>` primitive.
    expect(screen.getByRole('tab', { name: 'Negocio' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Horarios' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Voz del bot' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Auditoría' })).toBeInTheDocument();
  });

  it('shows the General tab by default', () => {
    setup();
    expect(screen.getByText('Slug')).toBeInTheDocument();
  });

  it('switches to the Horarios tab when clicked', async () => {
    setup();
    await userEvent.click(screen.getByRole('tab', { name: 'Horarios' }));
    expect(screen.getByRole('button', { name: 'Guardar horarios' })).toBeInTheDocument();
    expect(screen.queryByText('Slug')).toBeNull();
  });

  it('switches to the Voz del bot tab when clicked', async () => {
    setup();
    await userEvent.click(screen.getByRole('tab', { name: 'Voz del bot' }));
    expect(screen.getByRole('heading', { name: 'Voz del bot', level: 3 })).toBeInTheDocument();
    expect(screen.getByText('Tono')).toBeInTheDocument();
  });

  it('renders the brand logo uploader inside the Voz del bot tab', async () => {
    setup();
    await userEvent.click(screen.getByRole('tab', { name: 'Voz del bot' }));
    expect(screen.getByRole('heading', { name: 'Logo de marca', level: 3 })).toBeInTheDocument();
    // Empty state message (no tenant selected, brand_logo_url null).
    expect(screen.getByTestId('brand-logo-empty')).toBeInTheDocument();
    // The file input + submit button are present.
    expect(screen.getByTestId('brand-logo-file-input')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Subir logo' })).toBeDisabled();
  });
});
