/**
 * UI-INFLU-002 — Placeholders de las vistas del módulo Influencer.
 *
 * Vistas materializadas (importadas desde sus features reales):
 *   - `InfluencerCasting`  → `./casting/InfluencerCasting.jsx` (UI-INFLU-003+004)
 *   - `InfluencerCalendar` → `./calendar/CalendarContainer.jsx`
 *     (UI-INFLU-014, wireado en moduleRegistry directamente)
 *
 * Aún placeholder (TODO):
 *   - `InfluencerLibrary`  → reusa `media-library` con filtros del módulo
 *   - `InfluencerCredits`  → vista de balance + history (UI-INFLU-016)
 */
import { Card, PageHeader } from '../../components/ui/index.js';

function Placeholder({ title, eyebrow, description, htmlRef }) {
  return (
    <div data-module="influencer">
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <Card padding="lg">
        <p style={{ margin: 0 }}>
          Próximamente. Esta vista se materializa en una tarea posterior del
          backlog. Diseño de referencia: <code>{htmlRef}</code>.
        </p>
      </Card>
    </div>
  );
}

// UI-INFLU-003 — `InfluencerCasting` ya tiene implementación real en
// `./casting/InfluencerCasting.jsx` (empty state). Reexportamos desde
// el barrel para mantener compatibilidad con `moduleRegistry.js`. La
// vista con personajes llega en UI-INFLU-004.
export { InfluencerCasting } from './casting/InfluencerCasting.jsx';

export function InfluencerLibrary() {
  return (
    <Placeholder
      eyebrow="Ravit Studio"
      title="Biblioteca"
      description="Banco de medios generados con tus personajes."
      htmlRef="reusa src/features/owner-admin/media-library con filtros del módulo"
    />
  );
}

