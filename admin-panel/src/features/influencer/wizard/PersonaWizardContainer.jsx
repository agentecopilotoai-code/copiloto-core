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

  // STEP 1 — Face
  const handleGenerateVariations = useCallback(async (payload) => {
    setGlobalError(null);
    try {
      const personaId = await ensurePersona(null);
      const result = await generateFaceVariations(session, tenantId, personaId, payload);
      // Auto-marca la PRIMERA variación como canonical si ninguna lo es.
      // Sin esto, el "Siguiente paso" exige que el user click manual en una
      // miniatura — UX confusa para flujos como "Aleatorio IA al azar".
      // El user puede cambiar la canonical clickeando otra miniatura.
      const rawVariations = result?.variations || result || [];
      const variations = Array.isArray(rawVariations) ? rawVariations : [];
      const hasCanonical = variations.some((v) => v?.canonical);
      const withDefault = hasCanonical || variations.length === 0
        ? variations
        : variations.map((v, i) => ({ ...v, canonical: i === 0 }));
      updateDraft({ faceVariations: withDefault });
      return { ...result, variations: withDefault };
    } catch (err) {
      setGlobalError(`No se pudieron generar variaciones: ${err.message}`);
      throw err;
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

