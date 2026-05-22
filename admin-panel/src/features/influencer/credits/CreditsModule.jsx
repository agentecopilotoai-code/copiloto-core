/**
 * UI-INFLU-016 wiring — Vista de créditos del módulo Influencer.
 *
 * Muestra:
 *   - Balance actual (gauge prominente).
 *   - Pricing por kind de generación (foto/reel/historia/carrusel/ad).
 *   - Últimas 50 transacciones del ledger (kind, monto, ref, actor, fecha).
 *   - CTA "Comprar créditos" (gate por `influencer.credits.topup` —
 *     solo Owner/Admin; Manager NO).
 *
 * Endpoints:
 *   - GET /v1/influencer/credits/balance — `{ balance, transactions: [...] }`
 *   - GET /v1/influencer/pricing — lista `[{kind, cost_credits}, ...]`
 *   - POST /v1/influencer/credits/topup — body `{ amount, payment_ref }`
 *
 * El composer de top-up usa un modal mínimo (no integramos Stripe aún —
 * el endpoint backend ya tiene la lógica con `payment_ref` opcional).
 */
import { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import {
  AlertBanner,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  KpiTile,
  Modal,
  PageHeader,
  StateScreen,
  StatusBadge,
} from '../../../components/ui/index.js';
import { LoadingScreen } from '../../../components/layout/LoadingScreen.jsx';
import { useAuth } from '../../../context/AuthContext.jsx';
import { usePermissions } from '../../../permissions/index.js';
import {
  getCreditsBalance,
  getPricing,
  topUpCredits,
} from '../../../services/coreApi.js';

const KIND_LABELS = {
  photo: 'Foto',
  reel: 'Reel / video corto',
  carousel: 'Carrusel',
  story: 'Historia',
  ad: 'Anuncio',
  face_variation: 'Variación de cara',
  voice_sample: 'Muestra de voz',
};

function TopUpModal({ open, onClose, onConfirm, busy }) {
  const [amount, setAmount] = useState(100);
  const [paymentRef, setPaymentRef] = useState('');
  const [error, setError] = useState(null);

  if (!open) return null;

  const handleSubmit = async () => {
    setError(null);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('El monto debe ser un número positivo.');
      return;
    }
    try {
      await onConfirm({ amount, payment_ref: paymentRef || `manual-${Date.now()}` });
    } catch (err) {
      setError(err.message || 'Error procesando el top-up');
    }
  };

  return (
    <Modal isOpen={open} onClose={onClose} title="Comprar créditos">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label>
          <div style={{ marginBottom: 4 }}>Cantidad de créditos</div>
          <input
            type="number"
            min={1}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            style={{ width: '100%', padding: 8 }}
          />
        </label>
        <label>
          <div style={{ marginBottom: 4 }}>Referencia de pago (opcional)</div>
          <input
            type="text"
            value={paymentRef}
            onChange={(e) => setPaymentRef(e.target.value)}
            placeholder="ej. stripe_pi_xxx"
            style={{ width: '100%', padding: 8 }}
          />
        </label>
        {error ? <AlertBanner tone="warning">{error}</AlertBanner> : null}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={busy}>
            {busy ? 'Procesando...' : 'Confirmar compra'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function formatDelta(delta) {
  const n = Number(delta);
  if (n > 0) return `+${n}`;
  return String(n);
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-419', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function CreditsModule() {
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const { can } = usePermissions();
  const tenantId = activeTenant?.id;

  const canTopUp = can('influencer.credits.topup', 'RW');

  const [balance, setBalance] = useState(0);
  const [transactions, setTransactions] = useState([]);
  const [pricing, setPricing] = useState([]);
  const [loading, setLoading] = useState(true);
  const [topUpOpen, setTopUpOpen] = useState(false);
  const [topUpBusy, setTopUpBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!session || !tenantId) return undefined;
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      getCreditsBalance(session, tenantId),
      getPricing(session, tenantId),
    ]).then(([balRes, priceRes]) => {
      if (cancelled) return;
      if (balRes.status === 'fulfilled') {
        setBalance(balRes.value?.balance ?? 0);
        setTransactions(balRes.value?.transactions ?? []);
      }
      if (priceRes.status === 'fulfilled') {
        setPricing(priceRes.value?.pricing ?? priceRes.value ?? []);
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, refreshKey]);

  const handleTopUpConfirm = useCallback(async ({ amount, payment_ref }) => {
    setTopUpBusy(true);
    try {
      await topUpCredits(session, tenantId, { amount, payment_ref });
      setTopUpOpen(false);
      setRefreshKey((k) => k + 1);
    } finally {
      setTopUpBusy(false);
    }
  }, [session, tenantId]);

  if (loading) return <LoadingScreen />;

  if (!can('influencer.credits.read')) {
    return (
      <StateScreen
        title="Sin acceso a créditos"
        description="Tu rol no tiene permiso para ver el balance de créditos del módulo."
      />
    );
  }

  return (
    <div data-module="influencer" data-view="credits">
      <PageHeader
        eyebrow="Ravit Studio · Créditos"
        title={`Balance: ${balance} créditos`}
        description="Cada generación consume créditos según el tipo de contenido."
        actions={
          canTopUp ? (
            <Button onClick={() => setTopUpOpen(true)}>Comprar créditos</Button>
          ) : null
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        <KpiTile label="Balance actual" value={balance} />
        <KpiTile
          label="Movimientos (últimos 50)"
          value={transactions.length}
        />
        <KpiTile
          label="Tipos de generación"
          value={pricing.length}
        />
      </div>

      <Card padding="lg" style={{ marginBottom: 24 }}>
        <CardHeader>Precios por tipo de contenido</CardHeader>
        <CardBody>
          {pricing.length === 0 ? (
            <p style={{ margin: 0, color: 'var(--text-muted, #777)' }}>
              Sin pricing configurado.
            </p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {pricing.map((p) => (
                <li
                  key={p.kind}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 0',
                    borderBottom: '1px solid var(--border-subtle, #eee)',
                  }}
                >
                  <span>{KIND_LABELS[p.kind] || p.kind}</span>
                  <strong>{p.cost_credits} créditos</strong>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card padding="lg">
        <CardHeader>Últimos movimientos</CardHeader>
        <CardBody>
          {transactions.length === 0 ? (
            <p style={{ margin: 0, color: 'var(--text-muted, #777)' }}>
              Sin movimientos todavía. Empieza a generar contenido para ver el ledger.
            </p>
          ) : (
            <DataTable
              columns={[
                { key: 'created_at', label: 'Fecha', render: (row) => formatDate(row.created_at) },
                {
                  key: 'delta',
                  label: 'Movimiento',
                  render: (row) => (
                    <StatusBadge tone={Number(row.delta) >= 0 ? 'success' : 'warning'}>
                      {formatDelta(row.delta)}
                    </StatusBadge>
                  ),
                },
                { key: 'balance_after', label: 'Balance' },
                { key: 'reason', label: 'Motivo' },
                { key: 'ref', label: 'Ref', render: (row) => row.ref || '—' },
              ]}
              rows={transactions}
              rowKey={(row) => row.id}
            />
          )}
        </CardBody>
      </Card>

      <TopUpModal
        open={topUpOpen}
        onClose={() => setTopUpOpen(false)}
        onConfirm={handleTopUpConfirm}
        busy={topUpBusy}
      />
    </div>
  );
}
