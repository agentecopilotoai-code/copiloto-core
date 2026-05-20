/**
 * UI-INFLU-003 — Empty state del Casting del módulo Influencer.
 *
 * Se renderiza cuando `GET /v1/influencer/casting` devuelve `personas=[]`.
 * Reusa primitivas del design system (UI-001): `EmptyState`, `Button`,
 * `PageHeader`.
 *
 * Permission gate: la CTA "Crear personaje" renderiza siempre pero
 * queda deshabilitada (con tooltip) si el rol no tiene
 * `influencer.personas.write`.
 */
import { useNavigate, useParams } from 'react-router-dom';

import { Button, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';

export function CastingEmptyState() {
  const navigate = useNavigate();
  const { tenantSlug } = useParams();
  const { can } = usePermissions();
  const canWrite = can('influencer.personas.write');

  const handleCreate = () => {
    navigate(`/t/${tenantSlug}/influencer/personas/new/step-1`);
  };

  return (
    <div data-module="influencer" data-view="casting-empty">
      <PageHeader
        eyebrow="Ravit Studio"
        title="Tu casting está vacío"
        description="Crea tu primer personaje virtual para empezar a generar contenido con su voz."
      />
      <EmptyState
        size="lg"
        title="Aún no tienes personajes"
        description="Cada personaje será la cara de tu marca en posts, reels y anuncios. El wizard de 5 pasos te lleva de la mano."
        action={
          <Button
            variant="primary"
            size="lg"
            disabled={!canWrite}
            onClick={canWrite ? handleCreate : undefined}
            title={
              canWrite
                ? undefined
                : 'No tienes permiso para crear personajes (solo Manager/Admin/Owner)'
            }
          >
            Crear personaje
          </Button>
        }
      />
    </div>
  );
}
