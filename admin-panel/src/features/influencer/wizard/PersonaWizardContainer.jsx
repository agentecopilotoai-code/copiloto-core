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
import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate, useOutletContext, useParams } from 'react-router-dom';

import { AlertBanner, StateScreen } from '../../../components/ui/index.js';
import { LoadingScreen } from '../../../components/layout/LoadingScreen.jsx';
import { useAuth } from '../../../context/AuthContext.jsx';
import {
  createPersona,
  generateFaceVariations,
  generateVoiceSample,
  getFaceVariationStatus,
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

function storageKey(tenantId) {
  return `${STORAGE_PREFIX}.${tenantId}`;
}

function loadDraft(tenantId) {
  if (!tenantId || typeof sessionStorage === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(storageKey(tenantId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveDraft(tenantId, draft) {
  if (!tenantId || typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.setItem(storageKey(tenantId), JSON.stringify(draft));
  } catch {
    // Cuotas de storage llenas o private browsing: ignoramos, el wizard
    // sigue funcionando contra backend pero pierde el resume local.
  }
}

function clearDraft(tenantId) {
  if (!tenantId || typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.removeItem(storageKey(tenantId));
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
  const { tenantSlug, stepSlug } = useParams();
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const navigate = useNavigate();

  const stepNum = parseStepNum(stepSlug);
  const tenantId = activeTenant?.id;

  // ──────────────────────────────────────────────────────────────────────
  // State: draft local persistido en sessionStorage. `personaId` se setea
  // tras el primer POST /personas (al apretar "Siguiente" en step 1).
  // ──────────────────────────────────────────────────────────────────────
  const [draft, setDraft] = useState(() => loadDraft(tenantId) ?? {
    personaId: null,
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
  // UI-INFLU-014.1 — state del WizardPreview persistente:
  //   pendingRequests: array de UUIDs de face_variation_requests en vuelo.
  //   selectedVariationIndex: índice de la variación visible en el preview
  //     grande (null = auto-select de la última).
  //   pendingCount: derivado de pendingRequests, pero lo mantenemos
  //     separado para optimistic UI (al apretar Generar incrementamos
  //     antes de tener el ID del request).
  const [pendingRequests, setPendingRequests] = useState([]);
  const [optimisticPending, setOptimisticPending] = useState(0);
  const [selectedVariationIndex, setSelectedVariationIndex] = useState(null);
  const [liveFormState, setLiveFormState] = useState({}); // form en vuelo del step actual

  // Sincronizar a sessionStorage cada vez que cambia el draft.
  useEffect(() => {
    if (tenantId) saveDraft(tenantId, draft);
  }, [tenantId, draft]);

  const updateDraft = useCallback((patch) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  }, []);

  // ──────────────────────────────────────────────────────────────────────
  // Persona creation (lazy): el row se crea en backend la primera vez que
  // el user hace "Siguiente" en step 1. Si ya existe en el draft, reuse.
  // ──────────────────────────────────────────────────────────────────────
  const ensurePersona = useCallback(async (handle) => {
    // Si tenemos un personaId en sessionStorage, validar que aún existe en
    // backend antes de reutilizarlo. Si no existe (404) — caso típico
    // cuando el INSERT fallaba por el bug de jsonb encoding y dejó stale
    // state en el navegador, o si el draft fue archivado/borrado en otra
    // pestaña — limpiamos y creamos uno nuevo abajo.
    if (draft.personaId) {
      try {
        await getPersona(session, tenantId, draft.personaId);
        return draft.personaId;
      } catch (err) {
        if (err?.status === 404) {
          // UI-INFLU-014.1: silencioso — el draft viejo no existe en
          // backend (típicamente porque el INSERT falló antes del fix
          // de jsonb, o el draft fue archivado en otra pestaña). Limpiamos
          // y recreamos sin mostrar toast — es ruido para el usuario.
          updateDraft({ personaId: null });
          // Continuamos al create de abajo.
        } else {
          throw err;
        }
      }
    }
    // Backend (`PersonaCreate` en `personas_models.py`) exige:
    //   - `name: str` (NO `display_name`).
    //   - `handle: str` con regex `[a-z0-9][a-z0-9_]{2,29}` (lowercase,
    //     alfanumérico o underscore, 3-30 chars, primer char letra/dígito).
    // El step 3 (Identity) sobrescribe ambos con los valores reales que
    // el user elija. Acá generamos placeholders válidos para que el
    // backend acepte la creación del draft.
    const draftHandle = handle && /^[a-z0-9][a-z0-9_]{2,29}$/.test(handle)
      ? handle
      // 13 dígitos de timestamp + prefijo `draft_` = 19 chars, dentro del
      // límite 3-30 y respeta regex (sin guion).
      : `draft_${Date.now()}`;
    const created = await createPersona(session, tenantId, {
      handle: draftHandle,
      name: handle || 'Personaje en construcción',
      status: 'draft',
    });
    updateDraft({ personaId: created.id });
    return created.id;
  }, [draft.personaId, session, tenantId, updateDraft]);

  // ──────────────────────────────────────────────────────────────────────
  // Step callbacks. Cada `handleNextN` persiste el step en backend y
  // navega al siguiente. `handleSaveDraftN` solo persiste sin avanzar.
  // ──────────────────────────────────────────────────────────────────────
  const goToStep = useCallback((n) => {
    navigate(`/t/${tenantSlug}/influencer/personas/new/step-${n}`);
  }, [navigate, tenantSlug]);

  // UI-INFLU-014.1 — Generación de UNA variación (=1 crédito). El botón
  // "Generar +1" del WizardPreview llama a esta función. El backend
  // construye el prompt con todos los jsonb pre-seleccionados (face +
  // body + identity + voice del draft); el frontend no manda el prompt,
  // solo el payload de overrides (vacío por ahora).
  const handleGenerateOneVariation = useCallback(async () => {
    setGlobalError(null);
    // Optimistic UI: incrementamos el contador de pending antes de
    // tener el ID del request — el WizardPreview muestra un thumbnail
    // con spinner inmediatamente.
    setOptimisticPending((n) => n + 1);
    try {
      const personaId = await ensurePersona(null);
      // Antes de generar, persiste el form del step actual al jsonb
      // correspondiente, así el prompt del backend incluye lo que el
      // usuario acaba de editar (no solo lo del último save).
      try {
        await flushLiveFormState(personaId);
      } catch {
        // Si el save falla, igual seguimos — el prompt usará lo que
        // ya estaba en backend, no es bloqueante para la generación.
      }
      const result = await generateFaceVariations(
        session, tenantId, personaId, { count: 1 },
      );
      // El POST devuelve el id del request; lo agregamos a pending y
      // descontamos el optimistic — el polling toma el relevo.
      setPendingRequests((prev) => [...prev, result.id]);
      setOptimisticPending((n) => Math.max(0, n - 1));
    } catch (err) {
      setOptimisticPending((n) => Math.max(0, n - 1));
      setGlobalError(`No se pudo generar la variación: ${err.message}`);
    }
  }, [ensurePersona, session, tenantId]);

  // Persistir el form en vuelo del step actual ANTES de generar. Cada
  // step llama a `onFormChange` con su state cada vez que cambia, y el
  // container lo guarda en `liveFormState` con el campo correspondiente.
  const flushLiveFormState = useCallback(async (personaId) => {
    const entries = Object.entries(liveFormState || {});
    for (const [field, payload] of entries) {
      if (!payload) continue;
      try {
        if (field === 'face') {
          await wizardSaveFace(session, tenantId, personaId, payload);
        } else if (field === 'body') {
          await wizardSaveBody(session, tenantId, personaId, payload);
        } else if (field === 'identity') {
          await wizardSaveIdentity(session, tenantId, personaId, payload);
        } else if (field === 'voice') {
          await wizardSaveVoice(session, tenantId, personaId, payload);
        }
      } catch {
        // Best-effort — si un PUT falla, seguimos con los demás.
      }
    }
  }, [liveFormState, session, tenantId]);

  // ─── Polling de face_variation_requests ──────────────────────────────
  // Cada 2s revisa cada request en `pendingRequests`. Cuando uno
  // completa, mueve los assets al draft.faceVariations y lo remueve
  // del pending. El polling se detiene cuando no hay nada pendiente.
  const pollIntervalRef = useRef(null);
  useEffect(() => {
    if (pendingRequests.length === 0 || !draft.personaId) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return undefined;
    }
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      const stillPending = [];
      for (const reqId of pendingRequests) {
        try {
          const resp = await getFaceVariationStatus(
            session, tenantId, draft.personaId, reqId,
          );
          if (resp.status === 'completed') {
            // Anexar los assets al draft (sin duplicar por id).
            setDraft((prev) => {
              const existing = prev.faceVariations || [];
              const existingIds = new Set(existing.map((v) => v.id));
              const incoming = (resp.assets || [])
                .filter((a) => !existingIds.has(a.id))
                .map((a) => ({
                  id: a.id, url: a.url, status: 'ready',
                  marked_canonical: a.marked_canonical,
                }));
              return {
                ...prev,
                faceVariations: [...existing, ...incoming],
              };
            });
            // El nuevo asset se auto-selecciona — el preview grande
            // muestra la última variación generada automáticamente.
            setSelectedVariationIndex(null);
          } else if (resp.status === 'failed') {
            setGlobalError(
              `La generación falló: ${resp.error_message || 'error desconocido'}`,
            );
          } else {
            stillPending.push(reqId);
          }
        } catch {
          // Si el GET falla, mantenemos el ID en pending para retry.
          stillPending.push(reqId);
        }
      }
      if (!cancelled) setPendingRequests(stillPending);
    };
    pollIntervalRef.current = setInterval(tick, 2000);
    // Tick inmediato para no esperar 2s al primer poll.
    tick();
    return () => {
      cancelled = true;
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [pendingRequests, draft.personaId, session, tenantId]);

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
    onCheckHandle: () => Promise.resolve({ available: true }),
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

  // Captura el form del step actual cada vez que cambia, para que el
  // botón "Generar +1" pueda usar el estado más reciente en el prompt.
  const captureFormState = useCallback((field) => (formState) => {
    setLiveFormState((prev) => ({ ...prev, [field]: formState }));
  }, []);

  const personaName = draft.identity?.name
    || draft.face?.display_name
    || 'Personaje en construcción';
  const variationsForPreview = (draft.faceVariations || []).map((v) => ({
    id: v.id,
    url: v.url || v.thumbnail_url,
    status: v.status || 'ready',
    marked_canonical: v.marked_canonical,
  }));
  const generationNumber = Math.max(1, variationsForPreview.length);
  const previewBusy = pendingRequests.length > 0 || optimisticPending > 0;

  return (
    <div data-module="influencer" data-view="wizard" style={{ padding: 16 }}>
      {globalError ? (
        <AlertBanner tone="warning" style={{ marginBottom: 16 }}>
          {globalError}
        </AlertBanner>
      ) : null}

      {/* UI-INFLU-014.1 — Layout 2 columnas persistente. La columna
          izquierda (WizardPreview) es la misma para los 5 steps; solo
          cambia la derecha (formulario del step actual). */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(280px, 1fr) minmax(0, 1.4fr)',
        gap: 24,
        alignItems: 'start',
      }}>
        <WizardPreview
          personaName={personaName}
          generationNumber={generationNumber}
          variations={variationsForPreview}
          selectedIndex={selectedVariationIndex}
          onSelectVariation={(idx) => setSelectedVariationIndex(idx)}
          onGenerate={handleGenerateOneVariation}
          pendingCount={pendingRequests.length + optimisticPending}
          creditCost={1}
          disabled={previewBusy && optimisticPending > 0}
        />

        <div>
          {stepNum === 1 ? (
            <Step1Face
              initialForm={draft.face || {}}
              onFormChange={captureFormState('face')}
              onNext={handleNextFace}
              onSaveDraft={handleSaveDraftFace}
            />
          ) : null}
          {stepNum === 2 ? (
            <Step2Body
              initialForm={draft.body || {}}
              onNext={step2Handlers.onNext}
              onSaveDraft={step2Handlers.onSaveDraft}
            />
          ) : null}
          {stepNum === 3 ? (
            <Step3Identity
              initialForm={draft.identity || {}}
              onNext={step3Handlers.onNext}
              onSaveDraft={step3Handlers.onSaveDraft}
              onCheckHandle={step3Handlers.onCheckHandle}
            />
          ) : null}
          {stepNum === 4 ? (
            <Step4Voice
              initialForm={draft.voice || {}}
              sampleUrl={draft.voiceSampleUrl}
              onGenerateSample={handleGenerateVoiceSample}
              onNext={step4Handlers.onNext}
              onSaveDraft={step4Handlers.onSaveDraft}
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
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

