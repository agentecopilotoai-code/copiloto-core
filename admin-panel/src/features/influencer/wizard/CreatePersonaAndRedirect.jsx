/**
 * UI-INFLU-014.11 — Cuando el usuario aprieta "Crear nuevo personaje"
 * desde el casting, esta ruta:
 *
 *   1. Hace `POST /v1/influencer/personas` para crear un draft en
 *      blanco (nombre genérico + handle único basado en timestamp).
 *   2. Redirige a `/personas/{id}/wizard/step-1` con ese `personaId`.
 *
 * Esto reemplaza el "eager-create" que hacía el container al montar
 * (que creaba un personaje vacío en cuanto el usuario abría el wizard
 * aunque viniera de una recarga). Ahora cada draft es una página
 * dedicada con su propio URL.
 */
import { useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate, useOutletContext, useParams } from 'react-router-dom';

import { AlertBanner, Card } from '../../../components/ui/index.js';
import { useAuth } from '../../../context/AuthContext.jsx';
import { createPersona } from '../../../services/coreApi.js';


export function CreatePersonaAndRedirect() {
  const { tenantSlug } = useParams();
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const navigate = useNavigate();

  const [error, setError] = useState(null);
  const [newId, setNewId] = useState(null);
  const createdRef = useRef(false);
  const tenantId = activeTenant?.id;

  useEffect(() => {
    if (createdRef.current) return undefined;
    if (!session || !tenantId) return undefined;
    createdRef.current = true;
    (async () => {
      try {
        const created = await createPersona(session, tenantId, {
          // Handle único basado en timestamp; validates [a-z0-9_]{3,30}.
          handle: `draft_${Date.now()}`,
          name: 'Personaje en construcción',
          status: 'draft',
        });
        setNewId(created.id);
      } catch (err) {
        setError(err?.message || 'No se pudo crear el personaje');
      }
    })();
    return undefined;
  }, [session, tenantId]);

  if (newId) {
    return (
      <Navigate
        to={`/t/${tenantSlug}/influencer/personas/${newId}/wizard/step-1`}
        replace
      />
    );
  }

  if (error) {
    return (
      <Card padding="lg">
        <AlertBanner tone="warning">
          {error}
        </AlertBanner>
        <button
          type="button"
          onClick={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
          style={{ marginTop: 16 }}
        >
          Volver al casting
        </button>
      </Card>
    );
  }

  return (
    <Card padding="lg">
      <p role="status" aria-live="polite" style={{ margin: 0 }}>
        Creando personaje…
      </p>
    </Card>
  );
}
