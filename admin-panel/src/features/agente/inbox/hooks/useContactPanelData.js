import { useEffect, useState } from 'react';

import {
  assignContactTags,
  createContactNote,
  listContactTags,
  unassignContactTag,
} from '../../../../services/coreApi.js';

/**
 * Data layer for the contact side panel's "Etiquetas y notas" section: the
 * tenant tag catalogue, the contact-tag assign/remove handlers and the quick
 * internal-note handler — every `coreApi` call ported verbatim from the legacy
 * `OperationsDesk`. The resource/agenda and service-request/quote state live
 * in the sibling `useScheduleData` / `useServiceRequestsData` hooks; splitting
 * the side panel's heavy state across dedicated hooks keeps every file
 * ≤ 400 LOC while preserving all behaviour.
 *
 * @param {object} options
 * @param {object} options.session — admin session
 * @param {object|undefined} options.tenant — active tenant
 * @param {object|null} options.conversationDetail — the active conversation detail
 * @param {(notice: object|null) => void} options.setNotice — shared notice setter
 * @param {() => Promise<void>} options.refreshConversations — inbox refresh
 * @param {() => Promise<void>} options.refreshDetail — conversation detail refresh
 */
export function useContactPanelData({
  session,
  tenant,
  conversationDetail,
  setNotice,
  refreshConversations,
  refreshDetail,
}) {
  const [contactTags, setContactTags] = useState([]);
  const [quickNote, setQuickNote] = useState('');
  const [pendingTagAssign, setPendingTagAssign] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    if (tenant?.id) {
      listContactTags(session, tenant.id)
        .then((items) => setContactTags(items || []))
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  async function handleAssignTagToContact(event) {
    event.preventDefault();
    const contactId = conversationDetail?.contact_id;
    if (!contactId || !pendingTagAssign) return;
    setIsBusy(true);
    try {
      await assignContactTags(session, tenant.id, contactId, [pendingTagAssign]);
      setPendingTagAssign('');
      setNotice({ type: 'success', text: 'Etiqueta asignada al contacto.' });
      await Promise.all([refreshConversations(), refreshDetail()]);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRemoveTagFromContact(tagId) {
    const contactId = conversationDetail?.contact_id;
    if (!contactId || !tagId) return;
    setIsBusy(true);
    try {
      await unassignContactTag(session, tenant.id, contactId, tagId);
      setNotice({ type: 'success', text: 'Etiqueta retirada.' });
      await Promise.all([refreshConversations(), refreshDetail()]);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleQuickNote(event) {
    event.preventDefault();
    const contactId = conversationDetail?.contact_id;
    if (!contactId || !quickNote.trim()) return;
    setIsBusy(true);
    try {
      await createContactNote(session, tenant.id, contactId, quickNote.trim());
      setQuickNote('');
      setNotice({ type: 'success', text: 'Nota interna registrada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  return {
    state: {
      contactTags,
      quickNote,
      pendingTagAssign,
      isBusy,
    },
    actions: {
      setQuickNote,
      setPendingTagAssign,
      handleAssignTagToContact,
      handleRemoveTagFromContact,
      handleQuickNote,
    },
  };
}
