/**
 * UI-INFLU-005 wiring — Container que cablea `PersonaStudio` con el
 * endpoint `GET /v1/influencer/personas/{id}/studio` (TASK-INFLU-017).
 *
 * El componente `PersonaStudio.jsx` es presentacional: recibe el bundle
 * `{ persona, stats, next_post, platforms_connected, recent_generations }`
 * y lo renderiza. Este container resuelve el `personaId` del URL,
 * fetcha el bundle, y pasa los estados de loading/error al componente.
 *
 * Ruta: `/t/:tenantSlug/influencer/personas/:personaId/studio`.
 */
import { useEffect, useState } from 'react';
import { useOutletContext, useParams } from 'react-router-dom';

import { useAuth } from '../../../context/AuthContext.jsx';
import { getPersonaStudio } from '../../../services/coreApi.js';
import { PersonaStudio } from './PersonaStudio.jsx';

export function PersonaStudioContainer() {
  const { personaId } = useParams();
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const tenantId = activeTenant?.id;

  const [studio, setStudio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!session || !tenantId || !personaId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPersonaStudio(session, tenantId, personaId)
      .then((data) => {
        if (!cancelled) {
          setStudio(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          // `PersonaStudio` ya sabe mostrar un estado de error si recibe
          // `error` no nulo. Le pasamos el mensaje del request.
          setError(err.message || 'Error cargando el personaje');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, personaId]);

  return <PersonaStudio studio={studio} loading={loading} error={error} />;
}
