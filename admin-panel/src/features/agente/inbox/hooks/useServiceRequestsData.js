import { useEffect, useState } from 'react';

import {
  createQuote,
  createServiceRequest,
  getQuoteForSr,
  listServiceRequests,
  patchQuote,
  patchServiceRequest,
  sendQuote,
} from '../../../../services/coreApi.js';
import { computeQuoteTotals } from '../inboxData.js';

/**
 * Data layer for the contact side panel's "Solicitudes de servicio y
 * cotizaciones" section. Owns the service-request list + selection, the
 * quote-for-SR detail, the SR creation form and the quote draft (line items,
 * discount, tax) — plus every mutation handler ported verbatim from the legacy
 * `OperationsDesk`. Split out of `useContactPanelData` to keep each file
 * ≤ 400 LOC.
 *
 * @param {object} options
 * @param {object} options.session — admin session
 * @param {object|undefined} options.tenant — active tenant
 * @param {object|null} options.conversationDetail — the active conversation detail
 * @param {string|null} options.selectedConversationId — the active conversation id
 * @param {(notice: object|null) => void} options.setNotice — shared notice setter
 */
export function useServiceRequestsData({
  session,
  tenant,
  conversationDetail,
  selectedConversationId,
  setNotice,
}) {
  const [serviceRequests, setServiceRequests] = useState([]);
  const [selectedSrId, setSelectedSrId] = useState(null);
  const [srQuote, setSrQuote] = useState(null);
  const [srForm, setSrForm] = useState({ serviceType: '', problemSummary: '', urgency: 'normal' });
  const [quoteItems, setQuoteItems] = useState([{ description: '', qty: 1, unit_price: 0 }]);
  const [quoteDiscount, setQuoteDiscount] = useState(0);
  const [quoteTax, setQuoteTax] = useState(0);
  const [isBusy, setIsBusy] = useState(false);

  function refreshServiceRequests(contactId, silent = false) {
    if (!tenant?.id || !contactId) {
      setServiceRequests([]);
      setSelectedSrId(null);
      setSrQuote(null);
      return Promise.resolve();
    }
    return listServiceRequests(session, tenant.id, { contact_id: contactId })
      .then((items) => {
        setServiceRequests(items);
        setSelectedSrId((current) => current || items[0]?.id || null);
      })
      .catch((error) => {
        if (!silent) setNotice({ type: 'error', text: error.message });
      });
  }

  function refreshSrQuote(srId, silent = false) {
    if (!tenant?.id || !srId) {
      setSrQuote(null);
      return Promise.resolve();
    }
    return getQuoteForSr(session, tenant.id, srId)
      .then(setSrQuote)
      .catch((error) => {
        if (error.status === 404) {
          setSrQuote(null);
        } else if (!silent) {
          setNotice({ type: 'error', text: error.message });
        }
      });
  }

  useEffect(() => {
    const contactId = conversationDetail?.contact_id;
    setServiceRequests([]);
    setSelectedSrId(null);
    setSrQuote(null);
    if (contactId) refreshServiceRequests(contactId, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationDetail?.contact_id]);

  useEffect(() => {
    setSrQuote(null);
    if (selectedSrId) refreshSrQuote(selectedSrId, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSrId]);

  async function handleCreateServiceRequest(event) {
    event.preventDefault();
    if (!conversationDetail?.contact_id || !srForm.serviceType.trim()) {
      setNotice({ type: 'error', text: 'Tipo de servicio es obligatorio.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const sr = await createServiceRequest(session, tenant.id, {
        contact_id: conversationDetail.contact_id,
        conversation_id: selectedConversationId,
        vertical_code: tenant.vertical_code || '',
        service_type: srForm.serviceType.trim(),
        problem_summary: srForm.problemSummary.trim() || undefined,
        urgency: srForm.urgency,
      });
      setSrForm({ serviceType: '', problemSummary: '', urgency: 'normal' });
      await refreshServiceRequests(conversationDetail.contact_id);
      setSelectedSrId(sr.id);
      setNotice({ type: 'success', text: 'Solicitud de servicio registrada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handlePatchSrStatus(srId, newStatus) {
    setIsBusy(true);
    setNotice(null);
    try {
      await patchServiceRequest(session, tenant.id, srId, { status: newStatus });
      await refreshServiceRequests(conversationDetail?.contact_id);
      setNotice({ type: 'success', text: `Solicitud actualizada a "${newStatus}".` });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateQuote(event) {
    event.preventDefault();
    if (!selectedSrId) return;
    const validItems = quoteItems.filter((item) => item.description.trim());
    setIsBusy(true);
    setNotice(null);
    try {
      await createQuote(session, tenant.id, selectedSrId, {
        line_items: validItems.map((item) => ({
          description: item.description.trim(),
          qty: parseFloat(item.qty) || 1,
          unit_price: parseFloat(item.unit_price) || 0,
        })),
        discount_total: parseFloat(quoteDiscount) || 0,
        tax_total: parseFloat(quoteTax) || 0,
      });
      await refreshSrQuote(selectedSrId);
      await refreshServiceRequests(conversationDetail?.contact_id, true);
      setNotice({ type: 'success', text: 'Cotización creada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSendQuote() {
    if (!srQuote?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await sendQuote(session, tenant.id, srQuote.id);
      await refreshSrQuote(selectedSrId);
      setNotice({ type: 'success', text: 'Cotización enviada al contacto por WhatsApp.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleUpdateQuoteStatus(newStatus) {
    if (!srQuote?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await patchQuote(session, tenant.id, srQuote.id, { status: newStatus });
      await refreshSrQuote(selectedSrId);
      setNotice({ type: 'success', text: `Cotización actualizada a "${newStatus}".` });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function addQuoteItem() {
    setQuoteItems((current) => [...current, { description: '', qty: 1, unit_price: 0 }]);
  }

  function removeQuoteItem(index) {
    setQuoteItems((current) => current.filter((_, i) => i !== index));
  }

  function updateQuoteItem(index, field, value) {
    setQuoteItems((current) =>
      current.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  }

  return {
    state: {
      serviceRequests,
      selectedSrId,
      srQuote,
      srForm,
      quoteItems,
      quoteDiscount,
      quoteTax,
      isBusy,
      quoteTotals: computeQuoteTotals(quoteItems, quoteDiscount, quoteTax),
    },
    actions: {
      setSelectedSrId,
      setSrForm,
      setQuoteDiscount,
      setQuoteTax,
      handleCreateServiceRequest,
      handlePatchSrStatus,
      handleCreateQuote,
      handleSendQuote,
      handleUpdateQuoteStatus,
      addQuoteItem,
      removeQuoteItem,
      updateQuoteItem,
    },
  };
}
