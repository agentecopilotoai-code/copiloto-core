/**
 * Coverage push for useLegalData — exercises draft creation + publish
 * including validation guards and error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  createLegalDocumentDraft: vi.fn(),
  legalDocumentPublicUrl: vi.fn(() => 'https://public/url'),
  listLegalDocuments: vi.fn(),
  publishLegalDocument: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useLegalData } from './useLegalData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-1' };
const DRAFT = {
  id: 'doc-1',
  kind: 'privacy',
  title: 'Privacidad v1',
  version: 1,
  status: 'draft',
  language: 'es',
};

function setup(opts = {}) {
  const tenant = 'tenant' in opts ? opts.tenant : TENANT;
  return renderHook(() => useLegalData({ session: SESSION, tenant }));
}

beforeEach(() => {
  vi.clearAllMocks();
  coreApi.listLegalDocuments.mockResolvedValue({ documents: [DRAFT] });
});

describe('useLegalData', () => {
  it('loads documents on mount', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));
    expect(hook.result.current.state.grouped.privacy).toHaveLength(1);
  });

  it('surfaces an error when the fetch fails', async () => {
    coreApi.listLegalDocuments.mockRejectedValueOnce(new Error('boom'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.error).toBe('boom'));
  });

  it('does not crash when there is no tenant', () => {
    const hook = setup({ tenant: undefined });
    expect(hook.result.current.state.documents).toEqual([]);
  });

  it('saveDraft rejects when the title is empty', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.saveDraft();
    });
    expect(hook.result.current.state.error).toMatch(/título/);
    expect(coreApi.createLegalDocumentDraft).not.toHaveBeenCalled();
  });

  it('saveDraft rejects when the content is empty', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));

    act(() => hook.result.current.actions.setFormField({ title: 'Some title' }));
    await act(async () => {
      await hook.result.current.actions.saveDraft();
    });
    expect(hook.result.current.state.error).toMatch(/Markdown/);
    expect(coreApi.createLegalDocumentDraft).not.toHaveBeenCalled();
  });

  it('saveDraft creates a draft and sets the info notice', async () => {
    coreApi.createLegalDocumentDraft.mockResolvedValueOnce({ version: 2 });
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));

    act(() =>
      hook.result.current.actions.setFormField({
        title: 'Política',
        content_md: '# Hola',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.saveDraft();
    });

    expect(coreApi.createLegalDocumentDraft).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      expect.objectContaining({
        kind: 'privacy',
        language: 'es',
        title: 'Política',
        content_md: '# Hola',
      }),
    );
    expect(hook.result.current.state.info).toMatch(/Borrador v2/);
  });

  it('saveDraft surfaces error notice on failure', async () => {
    coreApi.createLegalDocumentDraft.mockRejectedValueOnce(new Error('save-fail'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));

    act(() =>
      hook.result.current.actions.setFormField({
        title: 'X',
        content_md: 'Y',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.saveDraft();
    });
    expect(hook.result.current.state.error).toBe('save-fail');
  });

  it('publish calls publishLegalDocument and sets info notice', async () => {
    coreApi.publishLegalDocument.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.publish(DRAFT);
    });

    expect(coreApi.publishLegalDocument).toHaveBeenCalledWith(SESSION, 'tenant-1', 'doc-1');
    expect(hook.result.current.state.info).toMatch(/publicada/);
  });

  it('publish surfaces error notice on failure', async () => {
    coreApi.publishLegalDocument.mockRejectedValueOnce(new Error('pub-fail'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.publish(DRAFT);
    });
    expect(hook.result.current.state.error).toBe('pub-fail');
  });

  it('publicUrl returns empty string when there is no tenant', () => {
    const hook = setup({ tenant: undefined });
    expect(hook.result.current.publicUrl('privacy')).toBe('');
  });

  it('publicUrl returns the legalDocumentPublicUrl when tenant exists', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.documents.length).toBe(1));
    expect(hook.result.current.publicUrl('privacy')).toBe('https://public/url');
    expect(coreApi.legalDocumentPublicUrl).toHaveBeenCalledWith(SESSION, 'tenant-1', 'privacy');
  });

  it('dismissError and dismissInfo clear the notices', async () => {
    coreApi.listLegalDocuments.mockRejectedValueOnce(new Error('boom'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.error).toBe('boom'));
    act(() => hook.result.current.actions.dismissError());
    expect(hook.result.current.state.error).toBeNull();

    // Trigger an info notice for the dismissInfo branch.
    coreApi.createLegalDocumentDraft.mockResolvedValueOnce({ version: 3 });
    act(() =>
      hook.result.current.actions.setFormField({
        title: 'T',
        content_md: 'C',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.saveDraft();
    });
    expect(hook.result.current.state.info).toBeTruthy();
    act(() => hook.result.current.actions.dismissInfo());
    expect(hook.result.current.state.info).toBeNull();
  });
});
