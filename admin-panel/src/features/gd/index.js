/**
 * Punto de entrada del módulo Gestión Documental.
 *
 * Reexporta el shell + componentes de dominio + placeholders para que el
 * resto del admin-panel los consuma sin acoplarse a la estructura interna.
 */
export { GdShell } from './shell/GdShell.jsx';
export { GdSidebar } from './shell/GdSidebar.jsx';
export { GdTopBar } from './shell/GdTopBar.jsx';
export { GdLanding } from './landing/GdLanding.jsx';

export { RadicadoCard } from './components/RadicadoCard.jsx';
export { PQRSDStatusChip } from './components/PQRSDStatusChip.jsx';
export {
  TerminoVencimientoBadge,
  computeStatus,
} from './components/TerminoVencimientoBadge.jsx';
export { WorkflowTimeline } from './components/WorkflowTimeline.jsx';
export { JustificacionRequiredField } from './components/JustificacionRequiredField.jsx';
export { InstitutionalLetterhead } from './components/InstitutionalLetterhead.jsx';

export { useGdScope, GD_SCOPE_LABELS } from './hooks/useGdScope.js';
export { useGdAudit } from './hooks/useGdAudit.js';

export * from './placeholders/index.jsx';
export * from './ventanilla/index.js';
export * from './buzon/index.js';
export * from './pqrsd/index.js';
export * from './correspondencia/index.js';
export * from './documentos/index.js';
export * from './plantillas/index.js';
export * from './firmas/index.js';
export * from './trd/index.js';
export * from './expedientes/index.js';
export * from './admin/index.js';
export * from './auditoria/index.js';
