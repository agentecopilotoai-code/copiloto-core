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
  // UI-INFLU-014.2: face_variation_request IDs en vuelo (polling).
  const [pendingRequests, setPendingRequests] = useState([]);

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
    // Si tenemos un personaId cacheado, validamos que aún exista. El 404
    // se silencia (sin toast) — el draft viejo se considera stale y
    // recreamos uno nuevo abajo. Esto cubre el caso donde un INSERT
    // anterior falló o el draft fue archivado en otra pestaña.
    if (draft.personaId) {
      try {
        await getPersona(session, tenantId, draft.personaId);
        return draft.personaId;
      } catch (err) {
        if (err?.status !== 404) throw err;
        updateDraft({ personaId: null });
        // fall-through al create.
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

  // STEP 1 — Face. UI-INFLU-014.2:
  //   * Cada click = 1 crédito = 1 variación (count=1).
  //   * Persistimos el face actual antes de generar para que el prompt
  //     del backend incluya lo más reciente.
  //   * Agregamos el request_id al pendingRequests; el useEffect de
  //     polling lo procesa hasta status='completed' y mueve los assets
  //     a draft.faceVariations.
  const handleGenerateVariations = useCallback(async (payload) => {
    setGlobalError(null);
    try {
      const personaId = await ensurePersona(null);
      // Persistir el face primero (best-effort) para que el prompt del
      // backend use los valores actuales del usuario.
      const facePayload = (() => {
        const clone = { ...(payload || {}) };
        delete clone.count;  // count va por separado a la API.
        return clone;
      })();
      try {
        await wizardSaveFace(session, tenantId, personaId, facePayload);
        updateDraft({ face: facePayload });
      } catch {
        // Si falla el save, igual seguimos — el prompt usará lo último
        // que estaba en backend.
      }
      const result = await generateFaceVariations(
        session, tenantId, personaId, { count: payload?.count ?? 1 },
      );
      // El POST devuelve { id, status, ... } — agregamos al pending y
      // el polling se encarga.
      if (result?.id) {
        setPendingRequests((prev) => [...prev, result.id]);
      }
    } catch (err) {
      setGlobalError(`No se pudo generar la variación: ${err.message}`);
    }
  }, [ensurePersona, session, tenantId, updateDraft]);

  // ─── Polling de face_variation_requests ──────────────────────────────
  // FIX del loop infinito (reportado por el usuario):
  //   1. La dependencia del useEffect es `pendingRequests.length > 0`
  //      (boolean), NO `pendingRequests` (array). Sin esto, cada mutación
  //      del array re-corría el effect, creando un setInterval nuevo
  //      acumulado además del existente → poll cada milisegundos.
  //   2. Usamos un ref para leer el array actualizado dentro del tick.
  //      El closure capturaría el array inicial; sin el ref, no veríamos
  //      requests agregados después de armar el interval.
  const pendingRef = useRef(pendingRequests);
  useEffect(() => { pendingRef.current = pendingRequests; }, [pendingRequests]);

  const hasPending = pendingRequests.length > 0;
  useEffect(() => {
    if (!hasPending || !draft.personaId) return undefined;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      const snapshot = pendingRef.current;
      if (snapshot.length === 0) return;
      const stillPending = [];
      const newAssets = [];
      for (const reqId of snapshot) {
        try {
          const resp = await getFaceVariationStatus(
            session, tenantId, draft.personaId, reqId,
          );
          if (resp.status === 'completed') {
            for (const a of resp.assets || []) {
              newAssets.push({
                id: a.id, url: a.url, status: 'ready',
                marked_canonical: a.marked_canonical,
              });
            }
          } else if (resp.status === 'failed') {
            setGlobalError(
              `La generación falló: ${resp.error_message || 'error desconocido'}`,
            );
          } else {
            stillPending.push(reqId);
          }
        } catch {
          stillPending.push(reqId);
        }
      }
      if (cancelled) return;
      if (newAssets.length > 0) {
        setDraft((prev) => {
          const existingIds = new Set((prev.faceVariations || []).map((v) => v.id));
          const fresh = newAssets.filter((a) => !existingIds.has(a.id));
          return {
            ...prev,
            faceVariations: [...(prev.faceVariations || []), ...fresh],
          };
        });
      }
      if (stillPending.length !== snapshot.length) {
        setPendingRequests(stillPending);
      }
    };
    const interval = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [hasPending, draft.personaId, session, tenantId]);

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
          pendingCount={pendingRequests.length}
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
  );
}

