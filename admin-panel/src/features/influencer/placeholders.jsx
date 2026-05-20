/**
 * UI-INFLU-002 — Placeholders de las vistas del módulo Influencer.
 *
 * Cada una de las 4 vistas del módulo (Casting, Calendar, Library, Credits)
 * se materializa en sub-tareas posteriores:
 *
 *   - `InfluencerCasting`  → UI-INFLU-003 (empty state) + UI-INFLU-004 (con personas)
 *   - `InfluencerCalendar` → UI-INFLU-014
 *   - `InfluencerLibrary`  → reusa `media-library` con filtros del módulo
 *   - `InfluencerCredits`  → vista de balance + history (parte de UI-INFLU-013+)
 *
 * Mientras tanto, cada placeholder muestra una `<Card>` con el nombre de la vista
 * y un hint del HTML del diseñador. El shell del módulo (InfluencerShell) se
 * encarga del sub-nav, gating y banners. Cuando se implemente cada vista,
 * se reemplazará el placeholder por el componente real importado desde
 * `./casting/index.js`, etc.
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

export function InfluencerCalendar() {
  return (
    <Placeholder
      eyebrow="Ravit Studio"
      title="Calendario de publicación"
      description="Una semana, todos tus personajes, todas las redes."
      htmlRef="docs/influencer/05 _ Calendario _todos los personajes_.html"
    />
  );
}

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

export function InfluencerCredits() {
  return (
    <Placeholder
      eyebrow="Ravit Studio"
      title="Créditos"
      description="Balance del tenant + historial de movimientos."
      htmlRef="docs/influencer/01 _ Casting _Home_.html (sidebar `Créditos · 248`)"
    />
  );
}
