/**
 * Coverage push for useMediaLibraryData — exercises upload/delete/edit
 * for media assets and create/update/delete for promotions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  createPromotion: vi.fn(),
  deleteMediaAsset: vi.fn(),
  deletePromotion: vi.fn(),
  listMediaAssets: vi.fn(),
  listPromotions: vi.fn(),
  listServices: vi.fn(),
  updateMediaAsset: vi.fn(),
  updatePromotion: vi.fn(),
  uploadMediaAsset: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useMediaLibraryData } from './useMediaLibraryData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-1' };
const ASSET = { id: 'm-1', label: 'logo', tags: ['brand'] };
const PROMO = { id: 'p-1', name: 'Promo Marzo', is_active: true };

function setup({ tenant = TENANT } = {}) {
  return renderHook(() => useMediaLibraryData({ session: SESSION, tenant }));
}

beforeEach(() => {
  vi.clearAllMocks();
  coreApi.listMediaAssets.mockResolvedValue([ASSET]);
  coreApi.listPromotions.mockResolvedValue([PROMO]);
  coreApi.listServices.mockResolvedValue([{ id: 'svc-1', name: 'Servicio 1' }]);
});

describe('useMediaLibraryData', () => {
  it('loads assets, promotions and services on mount', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));
    expect(hook.result.current.state.promotions).toHaveLength(1);
    expect(hook.result.current.state.services).toHaveLength(1);
    expect(hook.result.current.state.assetsById.get('m-1')).toBeTruthy();
    expect(hook.result.current.state.servicesById.get('svc-1')).toBeTruthy();
  });

  it('surfaces an error notice when the reload fails', async () => {
    coreApi.listMediaAssets.mockRejectedValueOnce(new Error('boom'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.notice?.type).toBe('error'));
    expect(hook.result.current.state.notice.text).toMatch(/biblioteca/);
  });

  it('openUpload + closeUpload toggle the drawer', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));
    act(() => hook.result.current.actions.openUpload());
    expect(hook.result.current.state.uploadOpen).toBe(true);
    act(() => hook.result.current.actions.closeUpload());
    expect(hook.result.current.state.uploadOpen).toBe(false);
  });

  it('pickFile clears the form when given null', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));
    act(() => hook.result.current.actions.pickFile(null));
    expect(hook.result.current.state.uploadForm.file).toBeNull();
  });

  it('pickFile accepts a small image and pre-fills the label', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    const file = new File(['x'], 'banner.png', { type: 'image/png' });
    act(() => hook.result.current.actions.pickFile(file));
    expect(hook.result.current.state.uploadForm.file).toBe(file);
    expect(hook.result.current.state.uploadForm.kind).toBe('image');
    expect(hook.result.current.state.uploadForm.label).toBe('banner');
  });

  it('pickFile rejects a file over the size limit', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    // Create a file that's "too big" by faking the size attribute. The
    // image kind limit is small enough that a 50MB stub trips it.
    const oversized = new File(['x'], 'huge.png', { type: 'image/png' });
    Object.defineProperty(oversized, 'size', { value: 50 * 1024 * 1024 });
    act(() => hook.result.current.actions.pickFile(oversized));
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.uploadForm.file).toBeNull();
  });

  it('upload rejects when no file is selected', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.upload();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.uploadMediaAsset).not.toHaveBeenCalled();
  });

  it('upload rejects when the label is empty', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    const file = new File(['x'], 'a.png', { type: 'image/png' });
    act(() =>
      hook.result.current.actions.setUploadForm({
        kind: 'image',
        file,
        label: '   ',
        description: '',
        tags: '',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.upload();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.uploadMediaAsset).not.toHaveBeenCalled();
  });

  it('upload calls uploadMediaAsset and reloads on success', async () => {
    coreApi.uploadMediaAsset.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    const file = new File(['x'], 'a.png', { type: 'image/png' });
    act(() =>
      hook.result.current.actions.setUploadForm({
        kind: 'image',
        file,
        label: 'Logo',
        description: 'desc',
        tags: 'a, b',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.upload();
    });
    expect(coreApi.uploadMediaAsset).toHaveBeenCalled();
  });

  it('upload surfaces error notice on failure', async () => {
    coreApi.uploadMediaAsset.mockRejectedValueOnce(new Error('up-fail'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    const file = new File(['x'], 'a.png', { type: 'image/png' });
    act(() =>
      hook.result.current.actions.setUploadForm({
        kind: 'image',
        file,
        label: 'Logo',
        description: '',
        tags: '',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.upload();
    });
    expect(hook.result.current.state.notice?.text).toBe('up-fail');
  });

  it('deleteAsset deletes the asset (auto-confirm in tests)', async () => {
    coreApi.deleteMediaAsset.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.deleteAsset(ASSET);
    });
    expect(coreApi.deleteMediaAsset).toHaveBeenCalledWith(SESSION, 'tenant-1', 'm-1');
  });

  it('deleteAsset surfaces error notice on failure', async () => {
    coreApi.deleteMediaAsset.mockRejectedValueOnce(new Error('del-fail'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.deleteAsset(ASSET);
    });
    expect(hook.result.current.state.notice?.text).toBe('del-fail');
  });

  it('editAssetTags prompts then patches tags', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('x, y, z');
    coreApi.updateMediaAsset.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.editAssetTags(ASSET);
    });
    expect(coreApi.updateMediaAsset).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'm-1',
      { tags: ['x', 'y', 'z'] },
    );
    promptSpy.mockRestore();
  });

  it('editAssetTags is a no-op when the user cancels the prompt', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue(null);
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.editAssetTags(ASSET);
    });
    expect(coreApi.updateMediaAsset).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('openCreatePromo and openEditPromo toggle the promo drawer', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    act(() => hook.result.current.actions.openCreatePromo());
    expect(hook.result.current.state.promoOpen).toBe(true);
    expect(hook.result.current.state.editingPromoId).toBeNull();

    act(() => hook.result.current.actions.openEditPromo(PROMO));
    expect(hook.result.current.state.editingPromoId).toBe('p-1');
    expect(hook.result.current.state.promoForm.name).toBe('Promo Marzo');

    act(() => hook.result.current.actions.closePromo());
    expect(hook.result.current.state.promoOpen).toBe(false);
  });

  it('submitPromo rejects when name is empty', async () => {
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.submitPromo();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.createPromotion).not.toHaveBeenCalled();
  });

  it('submitPromo creates a new promotion', async () => {
    coreApi.createPromotion.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    act(() =>
      hook.result.current.actions.setPromoForm({
        ...hook.result.current.state.promoForm,
        name: 'Promo Nueva',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submitPromo();
    });
    expect(coreApi.createPromotion).toHaveBeenCalled();
  });

  it('submitPromo updates an existing promotion when editing', async () => {
    coreApi.updatePromotion.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    act(() => hook.result.current.actions.openEditPromo(PROMO));
    await act(async () => {
      await hook.result.current.actions.submitPromo();
    });
    expect(coreApi.updatePromotion).toHaveBeenCalled();
  });

  it('submitPromo surfaces error notice on failure', async () => {
    coreApi.createPromotion.mockRejectedValueOnce(new Error('create-fail'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    act(() =>
      hook.result.current.actions.setPromoForm({
        ...hook.result.current.state.promoForm,
        name: 'New',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submitPromo();
    });
    expect(hook.result.current.state.notice?.text).toBe('create-fail');
  });

  it('removePromo deletes the promotion (auto-confirm in tests)', async () => {
    coreApi.deletePromotion.mockResolvedValueOnce({});
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.removePromo(PROMO);
    });
    expect(coreApi.deletePromotion).toHaveBeenCalledWith(SESSION, 'tenant-1', 'p-1');
  });

  it('removePromo surfaces error notice on failure', async () => {
    coreApi.deletePromotion.mockRejectedValueOnce(new Error('del-fail'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.assets.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.removePromo(PROMO);
    });
    expect(hook.result.current.state.notice?.text).toBe('del-fail');
  });

  it('dismissNotice clears any notice', async () => {
    coreApi.listMediaAssets.mockRejectedValueOnce(new Error('boom'));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.state.notice?.type).toBe('error'));
    act(() => hook.result.current.actions.dismissNotice());
    expect(hook.result.current.state.notice).toBeNull();
  });
});
