/**
 * UI-INFLU-008..012 wiring — Orchestrator del wizard de 5 pasos para
 * crear un personaje (persona) del módulo Influencer.
 *
 * Responsabilidades:
 *
 *   1. Mapear `stepSlug` del URL (`step-1` .. `step-5`) al componente
 *      correcto. Cada Step ya existe como componente standalone
 *      (`Step1Face`, ..., `Step5Platforms`); este container solo los
 *      compone con state + callbacks reales.
 *   2. Mantener el `personaId` en sessionStorage entre pasos. El primer
 *      "Siguiente" del step 1 hace `POST /personas` (que crea la persona
 *      en estado `draft`) + `PUT /wizard/{id}/face`; los siguientes 4
 *      pasos solo hacen `PUT /wizard/{id}/{step}`.
 *   3. Mantener el `formState` acumulado (face/body/identity/voice/
 *      platforms) en sessionStorage para que recargar/cerrar pestaña no
 *      pierda lo ya completado. El backend también lo persiste, pero el
 *      sessionStorage da reactividad inmediata + survive de reloads.
 *   4. Submit final: POST `/wizard/{id}/submit` cambia status `draft → active`
 *      y redirige al casting con un toast de éxito.
 *
 * **NO maneja**: la conexión OAuth real con Instagram (delegado al
 * `Step5Platforms` via `onConnectInstagram`). El callback OAuth se cubre
 * en TASK-INFLU-014 cuando el endpoint público esté cableado.
 *
 * Diseño de URL: `/t/:tenantSlug/influencer/personas/new/step-:stepNum`
 * con `stepNum` entre 1 y 5. Cualquier otro valor → redirect a `step-1`.
 *
 * Persistencia: usamos `sessionStorage` por tenant + por "draft activo".
 * Key: `influencer.wizardDraft.{tenantId}`. Se limpia tras submit exitoso
 * o si el user navega a `/personas/new/reset`.
 */
import { useCallback, useEffect, useState } from 'react';
import { Navigate, useNavigate, useOutletContext, useParams } from 'react-router-dom';

import { AlertBanner, StateScreen } from '../../../components/ui/index.js';
import { LoadingScreen } from '../../../components/layout/LoadingScreen.jsx';
import { useAuth } from '../../../context/AuthContext.jsx';
import {
  createPersona,
  generateFaceVariations,
  generateVoiceSample,
  getPersona,
  wizardSaveBody,
  wizardSaveFace,
  wizardSaveIdentity,
  wizardSavePlatforms,
  wizardSaveVoice,
  wizardSubmit,
} from '../../../services/coreApi.js';
import { Step1Face } from './Step1Face.jsx';
import { Step2Body } from './Step2Body.jsx';
import { Step3Identity } from './Step3Identity.jsx';
import { Step4Voice } from './Step4Voice.jsx';
import { Step5Platforms } from './Step5Platforms.jsx';
import { WizardPreview } from './WizardPreview.jsx';

const TOTAL_STEPS = 5;
const STORAGE_PREFIX = 'influencer.wizardDraft';

// UI-INFLU-014.11: el key del sessionStorage ahora es por personaId,
// no por tenantId. Esto permite que el usuario tenga N drafts en
// paralelo (cada draft cachea su propio form state). Cuando aprieta
// "Crear nuevo" desde casting, se crea un draft con su propio key.
function storageKey(personaId) {
  return `${STORAGE_PREFIX}.${personaId}`;
}

function loadDraft(personaId) {
  if (!personaId || typeof sessionStorage === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(storageKey(personaId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveDraft(personaId, draft) {
  if (!personaId || typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.setItem(storageKey(personaId), JSON.stringify(draft));
  } catch {
    // Cuotas de storage llenas o private browsing: ignoramos.
  }
}

function clearDraft(personaId) {
  if (!personaId || typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.removeItem(storageKey(personaId));
  } catch {
    /* ignore */
  }
}

/**
 * Convierte el `stepSlug` del URL (`'step-3'`) al número (3). Devuelve
 * `null` para slugs inválidos — el caller hace `<Navigate to=step-1/>`.
 */
function parseStepNum(stepSlug) {
  if (!stepSlug || typeof stepSlug !== 'string') return null;
  const match = stepSlug.match(/^step-([1-5])$/);
  return match ? Number(match[1]) : null;
}

export function PersonaWizardContainer() {
  // UI-INFLU-014.11: el `personaId` ahora viene del URL
  // (`/personas/:personaId/wizard/:stepSlug`). Si no viene (caller
  // usó la ruta legacy `/personas/new/:stepSlug`), redirigimos al
  // flow "Crear personaje" que hace POST y nos manda con un ID.
  const { tenantSlug, stepSlug, personaId: personaIdFromUrl } = useParams();
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const navigate = useNavigate();

  const stepNum = parseStepNum(stepSlug);
  const tenantId = activeTenant?.id;
  const personaId = personaIdFromUrl || null;

  // ──────────────────────────────────────────────────────────────────────
  // State: draft local persistido en sessionStorage por personaId.
  // Inicializa con cache del personaId del URL (si existe).
  // ──────────────────────────────────────────────────────────────────────
  const [draft, setDraft] = useState(() => loadDraft(personaId) ?? {
    personaId,
    face: null,
    body: null,
    identity: null,
    voice: null,
    platforms: null,
    voiceSampleUrl: null,
    faceVariations: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [globalError, setGlobalError] = useState(null);

  // Si el personaId del URL cambia, recargar el draft desde su cache.
  useEffect(() => {
    if (!personaId) return;
    if (draft.personaId === personaId) return;
    const stored = loadDraft(personaId);
    setDraft(stored || {
      personaId, face: null, body: null, identity: null,
      voice: null, platforms: null, voiceSampleUrl: null,
      faceVariations: [],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personaId]);

  // Sincronizar a sessionStorage cada vez que cambia el draft.
  useEffect(() => {
    if (personaId) saveDraft(personaId, draft);
  }, [personaId, draft]);

  const updateDraft = useCallback((patch) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  }, []);

  // UI-INFLU-014.11: el personaId viene del URL. Esta función SOLO
  // devuelve el ID (el create se hizo en `CreatePersonaAndRedirect`).
  // Si el ID del URL no existe en backend (404), navigate al casting.
  const ensurePersona = useCallback(async () => {
    if (!personaId) {
      navigate(`/t/${tenantSlug}/influencer/influencer-casting`, { replace: true });
      throw new Error('no personaId in URL');
    }
    return personaId;
  }, [personaId, navigate, tenantSlug]);

  // ──────────────────────────────────────────────────────────────────────
  // Step callbacks. Cada `handleNextN` persiste el step en backend y
  // navega al siguiente. `handleSaveDraftN` solo persiste sin avanzar.
  // ──────────────────────────────────────────────────────────────────────
  const goToStep = useCallback((n) => {
    navigate(`/t/${tenantSlug}/influencer/personas/new/step-${n}`);
  }, [navigate, tenantSlug]);

  // STEP 1 — Face. UI-INFLU-014.3 SÍNCRONO:
  //   * Cada click = 1 crédito = 1 variación (count=1).
  //   * Persistimos el face antes de generar para que el prompt del
  //     backend incluya lo más reciente.
  //   * El POST del backend ahora es SÍNCRONO (mismo patrón que el
  //     smoke test): llama a Grok, espera la imagen, persiste el asset
  //     y devuelve la URL inmediato. CERO polling. Anexamos la nueva
  //     variación directamente a `draft.faceVariations`.
  const [optimisticPending, setOptimisticPending] = useState(0);
  const handleGenerateVariations = useCallback(async (payload) => {
    setGlobalError(null);
    setOptimisticPending((n) => n + 1);
    try {
      const personaId = await ensurePersona(null);
      // Persistir el face primero (best-effort) para que el prompt del
      // backend use los valores actuales del usuario.
      const facePayload = (() => {
        const clone = { ...(payload || {}) };
        delete clone.count;
        return clone;
      })();
      try {
        await wizardSaveFace(session, tenantId, personaId, facePayload);
        updateDraft({ face: facePayload });
      } catch {
        // Si falla el save, igual seguimos.
      }
      const result = await generateFaceVariations(
        session, tenantId, personaId, { count: payload?.count ?? 1 },
      );
      // Response síncrono: assets ya pobladas — anexar al draft.
      const incoming = (result?.assets || []).map((a) => ({
        id: a.id, url: a.url, status: 'ready',
        marked_canonical: a.marked_canonical,
      }));
      setDraft((prev) => {
        const existing = prev.faceVariations || [];
        const existingIds = new Set(existing.map((v) => v.id));
        const fresh = incoming.filter((a) => !existingIds.has(a.id));
        return { ...prev, faceVariations: [...existing, ...fresh] };
      });
    } catch (err) {
      setGlobalError(`No se pudo generar la variación: ${err.message}`);
    } finally {
      setOptimisticPending((n) => Math.max(0, n - 1));
    }
  }, [ensurePersona, session, tenantId, updateDraft]);

  const handleNextFace = useCallback(async (payload) => {
    setGlobalError(null);
    try {
      const personaId = await ensurePersona(null);
      await wizardSaveFace(session, tenantId, personaId, payload);
      updateDraft({ face: payload });
      goToStep(2);
    } catch (err) {
      setGlobalError(`Error guardando cara: ${err.message}`);
    }
  }, [ensurePersona, session, tenantId, updateDraft, goToStep]);

  const handleSaveDraftFace = useCallback(async (payload) => {
    try {
      const personaId = await ensurePersona(null);
      await wizardSaveFace(session, tenantId, personaId, payload);
      updateDraft({ face: payload });
    } catch (err) {
      setGlobalError(`Error guardando borrador: ${err.message}`);
    }
  }, [ensurePersona, session, tenantId, updateDraft]);

  // STEPS 2..4 — body/identity/voice (mismo patrón: persist + advance)
  const makeStepHandlers = (saveFn, fieldName, nextStep) => ({
    onNext: async (payload) => {
      setGlobalError(null);
      try {
        await saveFn(session, tenantId, draft.personaId, payload);
        updateDraft({ [fieldName]: payload });
        goToStep(nextStep);
      } catch (err) {
        setGlobalError(`Error en paso ${nextStep - 1}: ${err.message}`);
      }
    },
    onSaveDraft: async (payload) => {
      try {
        await saveFn(session, tenantId, draft.personaId, payload);
        updateDraft({ [fieldName]: payload });
      } catch (err) {
        setGlobalError(`Error guardando borrador: ${err.message}`);
      }
    },
  });

  const step2Handlers = makeStepHandlers(wizardSaveBody, 'body', 3);
  const step3Handlers = {
    ...makeStepHandlers(wizardSaveIdentity, 'identity', 4),
    // Step 3 también acepta `onCheckHandle` para validar handle único —
    // por ahora dejamos un stub local; el backend valida en el PUT.
    // UI-INFLU-014.8: el step espera un BOOLEAN (`taken`). Antes
    // devolvíamos `{ available: true }` que como object es truthy →
    // siempre marcaba "Handle ya en uso". Devolvemos `false` (no taken)
    // — el backend valida unicidad real en el PUT/POST.
    onCheckHandle: () => Promise.resolve(false),
  };
  const step4Handlers = makeStepHandlers(wizardSaveVoice, 'voice', 5);

  // STEP 4 helper — generar muestra de voz
  const handleGenerateVoiceSample = useCallback(async (payload) => {
    setGlobalError(null);
    try {
      const result = await generateVoiceSample(session, tenantId, draft.personaId, payload);
      updateDraft({ voiceSampleUrl: result.sample_url || result.url });
      return result;
    } catch (err) {
      setGlobalError(`No se pudo generar la muestra: ${err.message}`);
      throw err;
    }
  }, [session, tenantId, draft.personaId, updateDraft]);

  // STEP 5 — Platforms + Activate (submit final)
  const handleActivate = useCallback(async (payload) => {
    if (!draft.personaId) {
      setGlobalError('No hay personaje en draft; vuelve al paso 1.');
      return;
    }
    setSubmitting(true);
    setGlobalError(null);
    try {
      await wizardSavePlatforms(session, tenantId, draft.personaId, payload);
      await wizardSubmit(session, tenantId, draft.personaId);
      clearDraft(tenantId);
      navigate(`/t/${tenantSlug}/influencer/influencer-casting`, {
        state: { toast: { kind: 'success', message: '¡Personaje creado!' } },
      });
    } catch (err) {
      setGlobalError(`Error al activar el personaje: ${err.message}`);
      setSubmitting(false);
    }
  }, [draft.personaId, session, tenantId, tenantSlug, navigate]);

  const handleConnectInstagram = useCallback(() => {
    // UI-INFLU-014 follow-up: launch Instagram OAuth. Por ahora abre
    // un toast indicando que está pendiente — el componente Step5 ya
    // tolera que esto sea un no-op.
    setGlobalError('Conexión con Instagram pendiente (UI-INFLU-014 follow-up).');
  }, []);

  // ──────────────────────────────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────────────────────────────

  // Guard: slug inválido → step-1
  if (stepNum === null) {
    return <Navigate to={`/t/${tenantSlug}/influencer/personas/new/step-1`} replace />;
  }

  // Guard: steps 2..5 requieren personaId (sino el user saltó steps).
  if (stepNum > 1 && !draft.personaId) {
    return (
      <StateScreen
        title="Empieza por el paso 1"
        description="Necesitas completar el paso 1 (Cara) antes de continuar."
        primaryAction={{
          label: 'Ir al paso 1',
          onClick: () => goToStep(1),
        }}
      />
    );
  }

  if (!session || !tenantId) return <LoadingScreen />;

  if (submitting) {
    return (
      <LoadingScreen message="Activando personaje..." />
    );
  }

  return (
    <div data-module="influencer" data-view="wizard">
      {globalError ? (
        <AlertBanner tone="warning" style={{ marginBottom: 16 }}>
          {globalError}
        </AlertBanner>
      ) : null}
      {stepNum === 1 ? (
        <Step1Face
          initialForm={draft.face || {}}
          initialVariations={draft.faceVariations || []}
          onGenerateVariations={handleGenerateVariations}
          onNext={handleNextFace}
          onSaveDraft={handleSaveDraftFace}
          onBack={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
          pendingCount={optimisticPending}
        />
      ) : null}
      {/* UI-INFLU-014.8: steps 2-5 envueltos en grid 2-col con
          WizardPreview persistente a la izquierda. Step1Face mantiene
          su propio preview interno (no se duplica). */}
      {stepNum >= 2 && stepNum <= 5 ? (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(280px, 1fr) minmax(0, 1.4fr)',
          gap: 24, alignItems: 'start',
        }}>
          <WizardPreview
            personaName={draft.identity?.name || 'Personaje en construcción'}
            variations={draft.faceVariations || []}
            onSelectVariation={(id) => {
              // Marca canonical la seleccionada (local — el backend
              // persiste cuando se activa el personaje en step 5).
              const next = (draft.faceVariations || []).map((v) => ({
                ...v, canonical: v.id === id,
              }));
              updateDraft({ faceVariations: next });
            }}
            onGenerate={() => {
              // Reutiliza handleGenerateVariations con el último face
              // payload conocido del draft.
              handleGenerateVariations({
                ...(draft.face || {}), count: 1,
              });
            }}
            pendingCount={optimisticPending}
          />
          <div>
            {stepNum === 2 ? (
              <Step2Body
                initialForm={draft.body || {}}
                onNext={step2Handlers.onNext}
                onSaveDraft={step2Handlers.onSaveDraft}
                onBack={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
              />
            ) : null}
            {stepNum === 3 ? (
              <Step3Identity
                initialForm={draft.identity || {}}
                onNext={step3Handlers.onNext}
                onSaveDraft={step3Handlers.onSaveDraft}
                onCheckHandle={step3Handlers.onCheckHandle}
                onBack={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
              />
            ) : null}
            {stepNum === 4 ? (
              <Step4Voice
                initialForm={draft.voice || {}}
                sampleUrl={draft.voiceSampleUrl}
                onGenerateSample={handleGenerateVoiceSample}
                onNext={step4Handlers.onNext}
                onSaveDraft={step4Handlers.onSaveDraft}
                onBack={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
              />
            ) : null}
            {stepNum === 5 ? (
              <Step5Platforms
                initialAccounts={draft.platforms?.accounts || []}
                initialMode={draft.platforms?.mode || 'manual_approval'}
                initialAutoRespondDms={draft.platforms?.auto_respond_dms || false}
                onConnectInstagram={handleConnectInstagram}
                onActivate={handleActivate}
                onSaveDraft={(p) => updateDraft({ platforms: p })}
                onBack={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

