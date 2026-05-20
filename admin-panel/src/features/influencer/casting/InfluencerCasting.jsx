/**
 * UI-INFLU-003 — wrapper que carga `/v1/influencer/casting` y decide
 * entre `CastingEmptyState` (personas=[]) y la vista con personajes
 * (`CastingWithPersonas`, montado en UI-INFLU-004).
 *
 * Mientras UI-INFLU-004 no aterrice, este componente siempre renderiza
 * el empty state — el HTTP request se evita si el caller ya sabe que
 * el casting está vacío (caso primera vez en el tenant).
 */
import { useEffect, useState } from 'react';

import { Card } from '../../../components/ui/index.js';
import { Casting } from './Casting.jsx';
import { CastingEmptyState } from './CastingEmptyState.jsx';

export function InfluencerCasting({ casting: castingProp = null, loading: loadingProp = false }) {
  const [casting, setCasting] = useState(castingProp);
  const [loading, setLoading] = useState(loadingProp);

  useEffect(() => {
    // UI-INFLU-004 inyectará el fetch real (coreApi.getCasting). Por
    // ahora aceptamos `casting` como prop para que el caller (o tests)
    // puedan inyectar un valor; sin prop, asumimos lista vacía.
    if (castingProp === null) {
      setCasting({ kpis: { active_personas: 0 }, personas: [] });
      setLoading(false);
    }
  }, [castingProp]);

  if (loading) {
    return (
      <Card padding="lg">
        <p style={{ margin: 0 }} role="status" aria-live="polite">
          Cargando casting…
        </p>
      </Card>
    );
  }

  if (!casting || (casting.personas?.length ?? 0) === 0) {
    return <CastingEmptyState />;
  }

  // UI-INFLU-004 — vista con personajes (KPIs + filtros + grid).
  return <Casting casting={casting} />;
}
