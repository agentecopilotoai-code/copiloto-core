import { useEffect, useState } from 'react';

import {
  createContactTag,
  deleteContactTag,
  getRetentionPreview,
  getTenantPaymentSettings,
  listContactTags,
  listRetentionPolicies,
  updateContactTag,
  updateRetentionPolicies,
  updateTenantPaymentSettings,
} from '../../../../services/coreApi.js';
import { RETENTION_ANONYMIZABLE, RETENTION_ENTITIES } from '../tenantSetupData.js';

// Tags, payment settings and retention policies — the "side panel" state of the
// wizard.  Extracted from useTenantSetupData to keep each hook under 400 LOC.
export function useTenantSetupSidePanels({ session, currentTenantId, runAction, setNotice }) {
  const [contactTags, setContactTags] = useState([]);
  const [tagForm, setTagForm] = useState({ name: '', color: '#4f6ef7', description: '' });
  const [editingTagId, setEditingTagId] = useState(null);
  const [paymentSettings, setPaymentSettings] = useState({
    provider: 'none',
    currency: 'COP',
    default_amount: '',
    api_key_configured: false,
    webhook_secret_configured: false,
  });
  const [paymentForm, setPaymentForm] = useState({ apiKey: '', webhookSecret: '' });
  const [retentionPolicies, setRetentionPolicies] = useState([]);
  const [retentionPreview, setRetentionPreview] = useState([]);

  async function refreshContactTags(tenantId = currentTenantId, showNotice = false) {
    if (!tenantId) return;
    try {
      const tags = await listContactTags(session, tenantId);
      setContactTags(tags || []);
      if (showNotice) setNotice({ type: 'success', text: 'Etiquetas recargadas.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    }
  }

  useEffect(() => {
    if (!currentTenantId) return;
    refreshContactTags(currentTenantId);
  }, [currentTenantId]);

  useEffect(() => {
    if (!currentTenantId) return;
    let mounted = true;
    getTenantPaymentSettings(session, currentTenantId)
      .then((data) => {
        if (!mounted) return;
        setPaymentSettings({
          provider: data.provider || 'none',
          currency: data.currency || 'COP',
          default_amount: data.default_amount ?? '',
          api_key_configured: Boolean(data.api_key_configured),
          webhook_secret_configured: Boolean(data.webhook_secret_configured),
        });
        setPaymentForm({ apiKey: '', webhookSecret: '' });
      })
      .catch(() => {
        // Keep defaults if the call fails.
      });
    return () => {
      mounted = false;
    };
  }, [currentTenantId, session]);

  async function refreshRetention(tenantId = currentTenantId) {
    if (!tenantId) return;
    try {
      const [policiesRes, previewRes] = await Promise.all([
        listRetentionPolicies(session, tenantId),
        getRetentionPreview(session, tenantId),
      ]);
      const byEntity = new Map(
        (policiesRes?.policies || []).map((row) => [row.entity, row]),
      );
      const merged = RETENTION_ENTITIES.map((entity) => {
        const existing = byEntity.get(entity);
        return {
          entity,
          retention_days: existing?.retention_days ?? (entity === 'audit_logs' ? 1825 : 90),
          anonymize_instead_of_delete: existing?.anonymize_instead_of_delete ?? false,
        };
      });
      setRetentionPolicies(merged);
      setRetentionPreview(previewRes?.preview || []);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    }
  }

  useEffect(() => {
    if (!currentTenantId) return;
    refreshRetention(currentTenantId);
  }, [currentTenantId]);

  function updateRetentionRow(entity, patch) {
    setRetentionPolicies((rows) =>
      rows.map((row) => (row.entity === entity ? { ...row, ...patch } : row)),
    );
  }

  async function handleSaveRetention(event) {
    event.preventDefault();
    if (!currentTenantId) return;
    const payload = retentionPolicies.map((row) => ({
      entity: row.entity,
      retention_days: Number(row.retention_days),
      anonymize_instead_of_delete:
        RETENTION_ANONYMIZABLE.has(row.entity) && Boolean(row.anonymize_instead_of_delete),
    }));
    const updated = await runAction(
      () => updateRetentionPolicies(session, currentTenantId, payload),
      'Política de retención guardada.',
    );
    if (updated) await refreshRetention(currentTenantId);
  }

  async function handleSavePaymentSettings(event) {
    event.preventDefault();
    if (!currentTenantId) return;
    const payload = {
      provider: paymentSettings.provider,
      currency: (paymentSettings.currency || 'COP').toUpperCase(),
      default_amount: paymentSettings.default_amount === '' || paymentSettings.default_amount === null
        ? null
        : Number(paymentSettings.default_amount),
      api_key: paymentForm.apiKey || null,
      webhook_secret: paymentForm.webhookSecret || null,
    };
    const updated = await runAction(
      () => updateTenantPaymentSettings(session, currentTenantId, payload),
      'Configuración de pagos guardada.',
    );
    if (updated) {
      setPaymentSettings({
        provider: updated.provider || 'none',
        currency: updated.currency || 'COP',
        default_amount: updated.default_amount ?? '',
        api_key_configured: Boolean(updated.api_key_configured),
        webhook_secret_configured: Boolean(updated.webhook_secret_configured),
      });
      setPaymentForm({ apiKey: '', webhookSecret: '' });
    }
  }

  async function handleSaveTag(event) {
    event.preventDefault();
    if (!currentTenantId || !tagForm.name.trim()) return;
    const payload = {
      name: tagForm.name.trim(),
      color: tagForm.color || null,
      description: tagForm.description || null,
    };
    const action = editingTagId
      ? () => updateContactTag(session, currentTenantId, editingTagId, payload)
      : () => createContactTag(session, currentTenantId, payload);
    const saved = await runAction(action, editingTagId ? 'Etiqueta actualizada.' : 'Etiqueta creada.');
    if (saved) {
      setTagForm({ name: '', color: '#4f6ef7', description: '' });
      setEditingTagId(null);
      await refreshContactTags();
    }
  }

  async function handleDeleteTag(tagId) {
    if (!currentTenantId) return;
    const ok = await runAction(
      () => deleteContactTag(session, currentTenantId, tagId),
      'Etiqueta eliminada.',
    );
    if (ok !== null) await refreshContactTags();
  }

  function startEditingTag(tag) {
    setEditingTagId(tag.id);
    setTagForm({
      name: tag.name,
      color: tag.color || '#4f6ef7',
      description: tag.description || '',
    });
  }

  function cancelEditingTag() {
    setEditingTagId(null);
    setTagForm({ name: '', color: '#4f6ef7', description: '' });
  }

  return {
    state: {
      contactTags,
      tagForm,
      editingTagId,
      paymentSettings,
      paymentForm,
      retentionPolicies,
      retentionPreview,
    },
    actions: {
      setPaymentSettings,
      setPaymentForm,
      setTagForm,
      refreshContactTags,
      refreshRetention,
      updateRetentionRow,
      handleSaveRetention,
      handleSavePaymentSettings,
      handleSaveTag,
      handleDeleteTag,
      startEditingTag,
      cancelEditingTag,
    },
  };
}
