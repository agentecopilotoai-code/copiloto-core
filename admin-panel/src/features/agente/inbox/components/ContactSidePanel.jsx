import { ContactTagsSection } from './contact-panel/ContactTagsSection.jsx';
import { ContactScheduleSection } from './contact-panel/ContactScheduleSection.jsx';
import { ContactServiceRequestsSection } from './contact-panel/ContactServiceRequestsSection.jsx';

/**
 * ContactSidePanel — the contact side panel for the active conversation. The
 * legacy `OperationsDesk` rendered the contact's tags + notes, the resource /
 * agenda builder and the service-request / quote workflow inline; this splits
 * them into ≤ 400-LOC sub-components under `contact-panel/` composed here. All
 * state + mutation handlers come from the `useContactPanelData` hook.
 *
 * @param {object} props
 * @param {object} props.contact — the `useContactPanelData` `{ state, actions }` bundle
 * @param {object} props.schedule — the `useScheduleData` `{ state, actions }` bundle
 * @param {object} props.serviceRequests — the `useServiceRequestsData` bundle
 * @param {object|null} props.conversationDetail
 * @param {object|null} props.selectedConversation
 */
export function ContactSidePanel({
  contact,
  schedule,
  serviceRequests,
  conversationDetail,
  selectedConversation,
}) {
  const { state, actions } = contact;
  const { state: schState, actions: schActions } = schedule;
  const { state: srState, actions: srActions } = serviceRequests;
  const tags = conversationDetail?.contact_tags
    || selectedConversation?.contact_tags
    || [];
  const hasContact = Boolean(conversationDetail?.contact_id);

  return (
    <>
      <ContactTagsSection
        tags={tags}
        contactTags={state.contactTags}
        pendingTagAssign={state.pendingTagAssign}
        quickNote={state.quickNote}
        isBusy={state.isBusy}
        onPendingTagChange={actions.setPendingTagAssign}
        onQuickNoteChange={actions.setQuickNote}
        onAssignTag={actions.handleAssignTagToContact}
        onRemoveTag={actions.handleRemoveTagFromContact}
        onQuickNote={actions.handleQuickNote}
      />

      <ContactScheduleSection
        resourceForm={schState.resourceForm}
        editingResourceId={schState.editingResourceId}
        imageAssets={schState.imageAssets}
        resources={schState.resources}
        appointments={schState.appointments}
        appointmentFeedback={schState.appointmentFeedback}
        calendarDate={schState.calendarDate}
        calendarData={schState.calendarData}
        isCalendarLoading={schState.isCalendarLoading}
        appointmentForm={schState.appointmentForm}
        rescheduleForm={schState.rescheduleForm}
        paymentDrafts={schState.paymentDrafts}
        hasContact={hasContact}
        isBusy={schState.isBusy}
        onResourceFormChange={schActions.setResourceForm}
        onCreateResource={schActions.handleCreateResource}
        onEditResource={schActions.handleEditResource}
        onCancelResourceEdit={schActions.handleCancelResourceEdit}
        onCalendarDateChange={schActions.setCalendarDate}
        onLoadCalendar={schActions.loadCalendar}
        onAppointmentFormChange={schActions.setAppointmentForm}
        onCreateAppointment={schActions.handleCreateAppointment}
        onRescheduleFormChange={schActions.setRescheduleForm}
        onRescheduleAppointment={schActions.handleRescheduleAppointment}
        onPaymentDraftsChange={schActions.setPaymentDrafts}
        onGeneratePaymentLink={schActions.handleGeneratePaymentLink}
        onSendPaymentLink={schActions.handleSendPaymentLink}
        onMarkPaymentStatus={schActions.handleMarkPaymentStatus}
        onCancelAppointment={schActions.handleCancelAppointment}
      />

      <ContactServiceRequestsSection
        serviceRequests={srState.serviceRequests}
        selectedSrId={srState.selectedSrId}
        srQuote={srState.srQuote}
        srForm={srState.srForm}
        quoteItems={srState.quoteItems}
        quoteDiscount={srState.quoteDiscount}
        quoteTax={srState.quoteTax}
        quoteTotals={srState.quoteTotals}
        hasContact={hasContact}
        isBusy={srState.isBusy}
        onSrFormChange={srActions.setSrForm}
        onCreateServiceRequest={srActions.handleCreateServiceRequest}
        onSelectSr={srActions.setSelectedSrId}
        onPatchSrStatus={srActions.handlePatchSrStatus}
        onQuoteItemChange={srActions.updateQuoteItem}
        onAddQuoteItem={srActions.addQuoteItem}
        onRemoveQuoteItem={srActions.removeQuoteItem}
        onQuoteDiscountChange={srActions.setQuoteDiscount}
        onQuoteTaxChange={srActions.setQuoteTax}
        onCreateQuote={srActions.handleCreateQuote}
        onSendQuote={srActions.handleSendQuote}
        onUpdateQuoteStatus={srActions.handleUpdateQuoteStatus}
      />
    </>
  );
}
