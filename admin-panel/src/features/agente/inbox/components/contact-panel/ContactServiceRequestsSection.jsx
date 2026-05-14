import { formatDate } from '../../inboxData.js';

/**
 * ContactServiceRequestsSection — the "Solicitudes de servicio y cotizaciones"
 * panel: the SR creation form, the SR list, the SR status actions and the
 * quote create-form / quote-detail table. Presentational; every mutation
 * handler lives in `useContactPanelData`. Ported verbatim from the legacy
 * `OperationsDesk`, including the `JSON.parse(srQuote.line_items)` fallback.
 *
 * @param {object} props — the SR/quote state slice + handlers (see below)
 */
export function ContactServiceRequestsSection({
  serviceRequests,
  selectedSrId,
  srQuote,
  srForm,
  quoteItems,
  quoteDiscount,
  quoteTax,
  quoteTotals,
  hasContact,
  isBusy,
  onSrFormChange,
  onCreateServiceRequest,
  onSelectSr,
  onPatchSrStatus,
  onQuoteItemChange,
  onAddQuoteItem,
  onRemoveQuoteItem,
  onQuoteDiscountChange,
  onQuoteTaxChange,
  onCreateQuote,
  onSendQuote,
  onUpdateQuoteStatus,
}) {
  const selectedSr = serviceRequests.find((sr) => sr.id === selectedSrId);

  return (
    <div className="service-requests-panel">
      <div>
        <strong>Solicitudes de servicio y cotizaciones</strong>
        <p className="hint">
          Registra solicitudes de servicio del contacto y genera cotizaciones orientativas
          enviables por WhatsApp.
        </p>
      </div>

      <form className="schedule-form" onSubmit={onCreateServiceRequest}>
        <label>
          Tipo de servicio
          <input
            onChange={(event) =>
              onSrFormChange({ ...srForm, serviceType: event.target.value })}
            placeholder="diagnostico / corte / baño / instalacion"
            value={srForm.serviceType}
          />
        </label>
        <label>
          Urgencia
          <select
            onChange={(event) => onSrFormChange({ ...srForm, urgency: event.target.value })}
            value={srForm.urgency}
          >
            <option value="low">Baja</option>
            <option value="normal">Normal</option>
            <option value="high">Alta</option>
            <option value="emergency">Emergencia</option>
          </select>
        </label>
        <label className="wide">
          Descripción del problema
          <textarea
            onChange={(event) =>
              onSrFormChange({ ...srForm, problemSummary: event.target.value })}
            placeholder="Descripción breve de la solicitud..."
            value={srForm.problemSummary}
          />
        </label>
        <button
          className="secondary-action"
          disabled={isBusy || !hasContact || !srForm.serviceType.trim()}
          type="submit"
        >
          Crear solicitud
        </button>
      </form>

      {serviceRequests.length > 0 && (
        <div className="sr-list">
          {serviceRequests.map((sr) => (
            <button
              className={`sr-card ${sr.id === selectedSrId ? 'active' : ''}`}
              key={sr.id}
              onClick={() => onSelectSr(sr.id)}
              type="button"
            >
              <span>{sr.service_type}</span>
              <small>{sr.vertical_code} · {sr.urgency} · <strong>{sr.status}</strong></small>
              {sr.problem_summary && <small>{sr.problem_summary}</small>}
            </button>
          ))}
        </div>
      )}

      {selectedSrId && (
        <div className="sr-detail">
          <div className="action-row">
            {['open', 'qualified'].includes(selectedSr?.status) && (
              <button
                className="secondary-action"
                disabled={isBusy}
                onClick={() => onPatchSrStatus(selectedSrId, 'cancelled')}
                type="button"
              >
                Cancelar solicitud
              </button>
            )}
            {selectedSr?.status === 'open' && (
              <button
                className="secondary-action"
                disabled={isBusy}
                onClick={() => onPatchSrStatus(selectedSrId, 'qualified')}
                type="button"
              >
                Marcar calificada
              </button>
            )}
          </div>

          {!srQuote ? (
            <form className="quote-form" onSubmit={onCreateQuote}>
              <strong>Nueva cotización</strong>
              {quoteItems.map((item, index) => (
                <div className="quote-item-row" key={index}>
                  <input
                    onChange={(event) =>
                      onQuoteItemChange(index, 'description', event.target.value)}
                    placeholder="Descripción del ítem"
                    value={item.description}
                  />
                  <input
                    min="0.01"
                    onChange={(event) => onQuoteItemChange(index, 'qty', event.target.value)}
                    placeholder="Cant."
                    step="0.01"
                    type="number"
                    value={item.qty}
                  />
                  <input
                    min="0"
                    onChange={(event) =>
                      onQuoteItemChange(index, 'unit_price', event.target.value)}
                    placeholder="Precio unit."
                    step="0.01"
                    type="number"
                    value={item.unit_price}
                  />
                  <span className="item-total">
                    {((parseFloat(item.qty) || 0) * (parseFloat(item.unit_price) || 0))
                      .toLocaleString('es-CO')}
                  </span>
                  {quoteItems.length > 1 && (
                    <button
                      className="secondary-action"
                      onClick={() => onRemoveQuoteItem(index)}
                      type="button"
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              <button className="secondary-action" onClick={onAddQuoteItem} type="button">
                + Agregar ítem
              </button>
              <div className="quote-totals-row">
                <label>
                  Descuento
                  <input
                    min="0"
                    onChange={(event) => onQuoteDiscountChange(event.target.value)}
                    step="0.01"
                    type="number"
                    value={quoteDiscount}
                  />
                </label>
                <label>
                  Impuestos
                  <input
                    min="0"
                    onChange={(event) => onQuoteTaxChange(event.target.value)}
                    step="0.01"
                    type="number"
                    value={quoteTax}
                  />
                </label>
                <div className="grand-total">
                  Total: <strong>{quoteTotals.grandTotal.toLocaleString('es-CO')} COP</strong>
                </div>
              </div>
              <button
                className="primary-action"
                disabled={isBusy || !quoteItems.some((item) => item.description.trim())}
                type="submit"
              >
                Crear cotización
              </button>
            </form>
          ) : (
            <div className="quote-detail">
              <div className="quote-header">
                <strong>Cotización</strong>
                <span className={`status-pill status-${srQuote.status}`}>{srQuote.status}</span>
              </div>
              <table className="quote-items-table">
                <thead>
                  <tr><th>Descripción</th><th>Cant.</th><th>P. Unit.</th><th>Total</th></tr>
                </thead>
                <tbody>
                  {(Array.isArray(srQuote.line_items)
                    ? srQuote.line_items
                    : JSON.parse(srQuote.line_items || '[]')).map((item, index) => (
                    <tr key={index}>
                      <td>{item.description}</td>
                      <td>{item.qty}</td>
                      <td>{Number(item.unit_price).toLocaleString('es-CO')}</td>
                      <td>{(item.qty * item.unit_price).toLocaleString('es-CO')}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan="3">Subtotal</td>
                    <td>{Number(srQuote.subtotal).toLocaleString('es-CO')}</td>
                  </tr>
                  <tr>
                    <td colSpan="3">Descuento</td>
                    <td>-{Number(srQuote.discount_total).toLocaleString('es-CO')}</td>
                  </tr>
                  <tr>
                    <td colSpan="3">Impuestos</td>
                    <td>+{Number(srQuote.tax_total).toLocaleString('es-CO')}</td>
                  </tr>
                  <tr className="total-row">
                    <td colSpan="3"><strong>Total</strong></td>
                    <td>
                      <strong>
                        {Number(srQuote.grand_total).toLocaleString('es-CO')} {srQuote.currency}
                      </strong>
                    </td>
                  </tr>
                </tfoot>
              </table>
              {srQuote.valid_until && (
                <small>Válida hasta: {formatDate(srQuote.valid_until)}</small>
              )}
              <div className="action-row">
                {srQuote.status === 'draft' && (
                  <button
                    className="primary-action"
                    disabled={isBusy}
                    onClick={onSendQuote}
                    type="button"
                  >
                    Enviar por WhatsApp
                  </button>
                )}
                {srQuote.status === 'sent' && (
                  <button
                    className="secondary-action"
                    disabled={isBusy}
                    onClick={() => onUpdateQuoteStatus('accepted')}
                    type="button"
                  >
                    Marcar aceptada
                  </button>
                )}
                {['sent', 'draft'].includes(srQuote.status) && (
                  <button
                    className="secondary-action"
                    disabled={isBusy}
                    onClick={() => onUpdateQuoteStatus('rejected')}
                    type="button"
                  >
                    Marcar rechazada
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
