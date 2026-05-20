/**
 * UI-INFLU-006 — Empty states transversales del módulo Influencer.
 *
 * Cada componente reusa la primitiva `EmptyState` (UI-001) y declara su
 * propio título + descripción + acción primaria. Compartidos por
 * múltiples vistas (calendar, studio, library, posts).
 */
import { EmptyState } from '../../../../components/ui/index.js';
import { usePermissions } from '../../../../permissions/index.js';


export function NoGenerationsEmpty({ onGenerate }) {
  return (
    <EmptyState
      title="Aún no hay generaciones"
      description="Cuando generes la primera foto, reel o anuncio aparecerán aquí."
      action={
        <button type="button" onClick={onGenerate}>Generar contenido</button>
      }
    />
  );
}


export function NoScheduledPostsEmpty({ onSchedule }) {
  return (
    <EmptyState
      title="No hay posts programados esta semana"
      description="Aprueba un borrador o programa uno nuevo para que aparezca en el calendario."
      action={
        <button type="button" onClick={onSchedule}>Programar post</button>
      }
    />
  );
}


export function NoPlatformsConnectedEmpty({ onConnect }) {
  return (
    <EmptyState
      title="Sin plataformas conectadas"
      description="Conecta Instagram, TikTok o YouTube para publicar contenido."
      action={
        <button type="button" onClick={onConnect}>Conectar plataforma</button>
      }
    />
  );
}


export function NoCreditsEmpty({ onTopUp }) {
  const { can } = usePermissions();
  const canTopUp = can('influencer.credits.topup');
  return (
    <EmptyState
      title="Sin créditos disponibles"
      description="Las acciones de generación están pausadas hasta que recargues tu balance."
      action={
        <button
          type="button"
          disabled={!canTopUp}
          title={canTopUp ? undefined : 'Solo Admin/Owner puede comprar créditos'}
          onClick={canTopUp ? onTopUp : undefined}
        >
          Comprar créditos
        </button>
      }
    />
  );
}


export function ProviderUnavailableEmpty({ onRetry }) {
  return (
    <EmptyState
      title="Servicio temporalmente no disponible"
      description="El proveedor de IA está caído. Estamos intentando con el siguiente del fallback chain — vuelve a intentarlo en unos segundos."
      action={
        <button type="button" onClick={onRetry}>Reintentar</button>
      }
    />
  );
}
