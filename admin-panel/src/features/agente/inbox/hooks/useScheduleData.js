import { useEffect, useState } from 'react';

import {
  cancelAppointment,
  createAppointment,
  createResource,
  generateAppointmentPaymentLink,
  getTenantAvailability,
  listAppointmentFeedback,
  listAppointments,
  listMediaAssets,
  listResources,
  sendAppointmentPaymentLink,
  updateAppointment,
  updateAppointmentPaymentStatus,
  updateResource,
} from '../../../../services/coreApi.js';
import {
  buildResourcePayload,
  emptyResourceForm,
  mergeAppointmentPayment,
  resourceFormFromRecord,
  todayISO,
} from '../inboxData.js';

/**
 * Data layer for the contact side panel's "Recursos y agenda" section: the
 * resource builder, the daily availability calendar, the appointment
 * scheduling / reschedule / cancel state and the appointment payment-link
 * workflow. Every `coreApi` call and business rule is ported verbatim from the
 * legacy `OperationsDesk`. Split out of `useContactPanelData` to keep each
 * file ≤ 400 LOC.
 *
 * @param {object} options
 * @param {object} options.session — admin session
 * @param {object|undefined} options.tenant — active tenant
 * @param {object|null} options.conversationDetail — the active conversation detail
 * @param {string|null} options.selectedConversationId — the active conversation id
 * @param {(notice: object|null) => void} options.setNotice — shared notice setter
 */
export function useScheduleData({
  session,
  tenant,
  conversationDetail,
  selectedConversationId,
  setNotice,
}) {
  const [resources, setResources] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [appointmentFeedback, setAppointmentFeedback] = useState({});
  const [resourceForm, setResourceForm] = useState(() => emptyResourceForm(tenant?.vertical_code || ''));
  const [editingResourceId, setEditingResourceId] = useState(null);
  const [imageAssets, setImageAssets] = useState([]);
  const [calendarDate, setCalendarDate] = useState(todayISO);
  const [calendarData, setCalendarData] = useState(null);
  const [isCalendarLoading, setIsCalendarLoading] = useState(false);
  const [appointmentForm, setAppointmentForm] = useState({
    endsAt: '', notes: '', resourceId: '', serviceCode: '', startsAt: '',
  });
  const [rescheduleForm, setRescheduleForm] = useState({
    appointmentId: '', endsAt: '', resourceId: '', startsAt: '',
  });
  const [paymentDrafts, setPaymentDrafts] = useState({});
  const [isBusy, setIsBusy] = useState(false);

  function refreshScheduleData(silent = false) {
    if (!tenant?.id) return Promise.resolve();
    listMediaAssets(session, tenant.id, { kind: 'image' })
      .then((items) => setImageAssets(Array.isArray(items) ? items : []))
      .catch(() => setImageAssets([]));
    return Promise.all([
      listResources(session, tenant.id),
      listAppointments(session, tenant.id),
    ]).then(([resourceItems, appointmentItems]) => {
      setResources(resourceItems);
      setAppointments(appointmentItems);
      setAppointmentForm((current) => ({
        ...current, resourceId: current.resourceId || resourceItems[0]?.id || '',
      }));
      setRescheduleForm((current) => ({
        ...current, resourceId: current.resourceId || resourceItems[0]?.id || '',
      }));

      // Fetch feedback for the visible slice so the agent can see the rating.
      const visible = appointmentItems.slice(0, 8);
      Promise.allSettled(
        visible.map((appointment) =>
          listAppointmentFeedback(session, tenant.id, appointment.id)
            .then((items) => [appointment.id, items])),
      ).then((results) => {
        const next = {};
        results.forEach((entry) => {
          if (entry.status === 'fulfilled') {
            const [appointmentId, items] = entry.value;
            if (Array.isArray(items) && items.length > 0) next[appointmentId] = items[0];
          }
        });
        setAppointmentFeedback(next);
      });
    }).catch((error) => {
      if (!silent) setNotice({ type: 'error', text: error.message });
    });
  }

  async function loadCalendar(targetDate = calendarDate) {
    if (!tenant?.id || !targetDate) return;
    setIsCalendarLoading(true);
    try {
      const data = await getTenantAvailability(session, tenant.id, { date: targetDate });
      setCalendarData(data);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsCalendarLoading(false);
    }
  }

  useEffect(() => {
    refreshScheduleData(true);
    setResourceForm((current) => ({ ...current, verticalCode: tenant?.vertical_code || '' }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  useEffect(() => {
    if (tenant?.id) loadCalendar(calendarDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id, calendarDate]);

  async function handleCreateResource(event) {
    event.preventDefault();
    if (!resourceForm.code.trim() || !resourceForm.name.trim()) {
      setNotice({ type: 'error', text: 'Código y nombre del recurso son obligatorios.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const payload = buildResourcePayload(resourceForm);
      if (editingResourceId) {
        await updateResource(session, tenant.id, editingResourceId, payload);
      } else {
        await createResource(session, tenant.id, payload);
      }
      setResourceForm(emptyResourceForm(tenant?.vertical_code || ''));
      setEditingResourceId(null);
      await refreshScheduleData();
      setNotice({
        type: 'success',
        text: editingResourceId
          ? 'Recurso actualizado.'
          : 'Recurso creado y disponible para agenda.',
      });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function handleEditResource(resource) {
    setEditingResourceId(resource.id);
    setResourceForm(resourceFormFromRecord(resource, tenant?.vertical_code || ''));
  }

  function handleCancelResourceEdit() {
    setEditingResourceId(null);
    setResourceForm(emptyResourceForm(tenant?.vertical_code || ''));
  }

  async function handleCreateAppointment(event) {
    event.preventDefault();
    if (
      !conversationDetail?.contact_id || !appointmentForm.resourceId
      || !appointmentForm.serviceCode.trim() || !appointmentForm.startsAt || !appointmentForm.endsAt
    ) {
      setNotice({ type: 'error', text: 'Selecciona conversación, recurso, servicio e intervalo.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      await createAppointment(session, tenant.id, {
        contact_id: conversationDetail.contact_id,
        conversation_id: selectedConversationId,
        ends_at: new Date(appointmentForm.endsAt).toISOString(),
        notes: appointmentForm.notes.trim() || undefined,
        resource_id: appointmentForm.resourceId,
        service_code: appointmentForm.serviceCode.trim(),
        starts_at: new Date(appointmentForm.startsAt).toISOString(),
      });
      setAppointmentForm({
        endsAt: '', notes: '', resourceId: appointmentForm.resourceId, serviceCode: '', startsAt: '',
      });
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Cita agendada sin conflicto de recurso.' });
    } catch (error) {
      setNotice({
        type: 'error',
        text: typeof error.message === 'string' ? error.message : 'No fue posible agendar la cita.',
      });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRescheduleAppointment(event) {
    event.preventDefault();
    if (
      !rescheduleForm.appointmentId || !rescheduleForm.resourceId
      || !rescheduleForm.startsAt || !rescheduleForm.endsAt
    ) {
      setNotice({ type: 'error', text: 'Selecciona cita, recurso y nuevo intervalo.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      await updateAppointment(session, tenant.id, rescheduleForm.appointmentId, {
        ends_at: new Date(rescheduleForm.endsAt).toISOString(),
        resource_id: rescheduleForm.resourceId,
        starts_at: new Date(rescheduleForm.startsAt).toISOString(),
      });
      setRescheduleForm({
        appointmentId: '', endsAt: '', resourceId: rescheduleForm.resourceId, startsAt: '',
      });
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Cita reprogramada sin violar agenda.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCancelAppointment(appointmentId) {
    setIsBusy(true);
    setNotice(null);
    try {
      await cancelAppointment(session, tenant.id, appointmentId);
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Cita cancelada; el recurso queda liberado.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function applyPaymentSummary(appointmentId, summary) {
    if (!summary) return;
    setAppointments((current) =>
      current.map((appointment) =>
        (appointment.id === appointmentId
          ? mergeAppointmentPayment(appointment, summary)
          : appointment)),
    );
  }

  async function handleGeneratePaymentLink(appointment) {
    const draft = paymentDrafts[appointment.id] || {};
    const amount = draft.amount !== undefined && draft.amount !== ''
      ? Number(draft.amount)
      : appointment.payment_amount;
    if (!amount || Number(amount) <= 0) {
      setNotice({ type: 'error', text: 'Indica un monto mayor a 0 para generar el link.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const summary = await generateAppointmentPaymentLink(session, tenant.id, appointment.id, {
        amount: Number(amount),
        currency: draft.currency || appointment.payment_currency || undefined,
        description: draft.description || undefined,
      });
      applyPaymentSummary(appointment.id, summary);
      setNotice({ type: 'success', text: 'Link de pago generado.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSendPaymentLink(appointmentId) {
    setIsBusy(true);
    setNotice(null);
    try {
      const summary = await sendAppointmentPaymentLink(session, tenant.id, appointmentId);
      applyPaymentSummary(appointmentId, summary);
      setNotice({ type: 'success', text: 'Link enviado por WhatsApp.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleMarkPaymentStatus(appointmentId, paymentStatus) {
    setIsBusy(true);
    setNotice(null);
    try {
      const summary = await updateAppointmentPaymentStatus(session, tenant.id, appointmentId, {
        payment_status: paymentStatus,
      });
      applyPaymentSummary(appointmentId, summary);
      setNotice({ type: 'success', text: `Estado de pago actualizado a "${paymentStatus}".` });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  return {
    state: {
      resources,
      appointments,
      appointmentFeedback,
      resourceForm,
      editingResourceId,
      imageAssets,
      calendarDate,
      calendarData,
      isCalendarLoading,
      appointmentForm,
      rescheduleForm,
      paymentDrafts,
      isBusy,
    },
    actions: {
      setResourceForm,
      setCalendarDate,
      setAppointmentForm,
      setRescheduleForm,
      setPaymentDrafts,
      loadCalendar,
      handleCreateResource,
      handleEditResource,
      handleCancelResourceEdit,
      handleCreateAppointment,
      handleRescheduleAppointment,
      handleCancelAppointment,
      handleGeneratePaymentLink,
      handleSendPaymentLink,
      handleMarkPaymentStatus,
    },
  };
}
