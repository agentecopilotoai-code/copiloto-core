/**
 * Placeholders provisorios para vistas del módulo GD que aún no están
 * implementadas en sub-bloques de UI. Cada placeholder:
 *  - Muestra el GdShell + breadcrumb + título.
 *  - Indica al usuario que la vista está en construcción y a qué bloque
 *    pertenece.
 *
 * Estos placeholders desaparecen conforme se implementan las vistas reales
 * en los bloques UI-2..UI-15. Sirven para que el módulo sea navegable
 * desde el primer día sin romper deep-links.
 */
import React from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { GdLanding } from '../landing/GdLanding.jsx';
import {
  VentanillaHome,
  NuevoRadicadoEntrada,
  NuevoRadicadoSalida,
  ColaVentanilla,
  RadicadoFicha,
  AnulacionesPendientes,
  BuscarRadicados,
  ReportesVentanilla,
} from '../ventanilla/index.js';
import {
  MiBuzon,
  BuzonDependencia,
  TareaFicha,
  ReasignacionMasiva,
} from '../buzon/index.js';
import {
  PanelPQRSD,
  ListaPQRSD,
  FichaPQRSD,
  ReportesPQRSD,
} from '../pqrsd/index.js';
import {
  CorrespondenciaInterna,
  CorrespondenciaExterna,
  CorrespondenciaFicha,
} from '../correspondencia/index.js';
import {
  Biblioteca,
  DocumentoFicha,
} from '../documentos/index.js';
import {
  AdminPlantillas,
  GenerarDocumento,
} from '../plantillas/index.js';
import {
  PorFirmar,
  EvidenciaFirma,
  AdminFirmantes,
} from '../firmas/index.js';
import {
  TablaTRD,
  TablaTVD,
  ClasificarConTRD,
} from '../trd/index.js';
import {
  ExpedienteFicha,
  BuscarExpedientes,
} from '../expedientes/index.js';
import {
  AdminUsuarios,
  AdminEstructura,
  AdminCatalogos,
  AdminParametros,
  CalendarioLaboral,
  PlantillasNotificacion,
  RetencionLogs,
  Backup,
  Integraciones,
  Seguridad,
  SaludSistema,
} from '../admin/index.js';
import {
  BandejaAuditoria,
  EventoAuditoriaFicha,
  ReportesConsolidados,
  VistaAuditor,
} from '../auditoria/index.js';
import {
  BusquedaSemantica,
  Asistente,
  DeteccionPII,
  PanelUsoIA,
  ConfigModelosIA,
} from '../ia/index.js';

function ShellWrapper({ title, bloqueNum: _bn, children, ...shellProps }) {
  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: title },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>{title}</h1>
          <p className="subtitle">
            Vista en construcción — disponible en la siguiente entrega.
          </p>
        </div>
      </div>
      {children || (
        <div className="empty">
          <p className="muted">
            Esta sección estará disponible próximamente.
          </p>
        </div>
      )}
    </GdShell>
  );
}

// Ventanilla — vistas reales (bloques UI-2 / UI-3):
export const GdVentanillaHome = (p) => <VentanillaHome {...p} />;
export const GdNuevoRadicado = (p) => <NuevoRadicadoEntrada {...p} />;
export const GdNuevoRadicadoSalida = (p) => <NuevoRadicadoSalida {...p} />;
export const GdColaVU = (p) => <ColaVentanilla {...p} />;
export const GdRadicadoFicha = (p) => <RadicadoFicha {...p} />;
export const GdAnulacionesPendientes = (p) => <AnulacionesPendientes {...p} />;
export const GdBuscarRadicados = (p) => <BuscarRadicados {...p} />;
export const GdReportesVentanilla = (p) => <ReportesVentanilla {...p} />;

// Buzón (UI-4) — vistas reales:
export const GdBuzonHome = (p) => <MiBuzon {...p} />;
export const GdBuzonDependencia = (p) => <BuzonDependencia {...p} />;
export const GdTareaFicha = (p) => <TareaFicha {...p} />;
export const GdReasignacionMasiva = (p) => <ReasignacionMasiva {...p} />;

// PQRSD (UI-5) — vistas reales:
export const GdPqrsdPanel = (p) => <PanelPQRSD {...p} />;
export const GdPqrsdLista = (p) => <ListaPQRSD {...p} />;
export const GdPqrsdFicha = (p) => <FichaPQRSD {...p} />;
// Variantes con filtros pre-seleccionados (los rolesusan estas).
export const GdPqrsdMias = (p) => (
  <ListaPQRSD {...p} titulo="Mis PQRSD" filtrosIniciales={{ responsable: 'me' }} />
);
export const GdPqrsdSinAsignar = (p) => (
  <ListaPQRSD {...p} titulo="Sin asignar" filtrosIniciales={{ estado: 'nueva' }} />
);
export const GdPqrsdVencimientos = (p) => (
  <ListaPQRSD {...p} titulo="Por vencer" filtrosIniciales={{ vencimiento: 'proximo' }} />
);
export const GdPqrsdVencidas = (p) => (
  <ListaPQRSD {...p} titulo="Vencidas" filtrosIniciales={{ vencimiento: 'vencido' }} />
);
export const GdPqrsdReportes = (p) => <ReportesPQRSD {...p} />;

// Correspondencia (UI-7) — vistas reales:
export const GdCorrespondenciaInterna = (p) => <CorrespondenciaInterna {...p} />;
export const GdCorrespondenciaExterna = (p) => <CorrespondenciaExterna {...p} />;
export const GdCorrespondenciaFicha = (p) => <CorrespondenciaFicha {...p} />;

// Documentos + plantillas + firmas (UI-8) — vistas reales:
export const GdBiblioteca = (p) => <Biblioteca {...p} />;
export const GdDocumentoFicha = (p) => <DocumentoFicha {...p} />;
export const GdPlantillas = (p) => <AdminPlantillas {...p} />;
export const GdGenerarDocumento = (p) => <GenerarDocumento {...p} />;
export const GdPorFirmar = (p) => <PorFirmar {...p} />;
export const GdEvidenciaFirma = (p) => <EvidenciaFirma {...p} />;
export const GdAdminFirmantes = (p) => <AdminFirmantes {...p} />;

// TRD/TVD + Expedientes (UI-9) — vistas reales:
export const GdTrdHome = (p) => <TablaTRD {...p} />;
export const GdTvdHome = (p) => <TablaTVD {...p} />;
export const GdClasificarConTRD = (p) => <ClasificarConTRD {...p} />;
export const GdExpedientes = (p) => <BuscarExpedientes {...p} />;
export const GdExpedienteFicha = (p) => <ExpedienteFicha {...p} />;

// Admin sistema (UI-10) — vistas reales:
export const GdAdminUsuarios = (p) => <AdminUsuarios {...p} />;
export const GdAdminEstructura = (p) => <AdminEstructura {...p} />;
export const GdAdminCatalogos = (p) => <AdminCatalogos {...p} />;
export const GdAdminParametros = (p) => <AdminParametros {...p} />;
export const GdCalendario = (p) => <CalendarioLaboral {...p} />;
export const GdPlantillasNotif = (p) => <PlantillasNotificacion {...p} />;
export const GdRetencionLogs = (p) => <RetencionLogs {...p} />;
export const GdBackup = (p) => <Backup {...p} />;
export const GdIntegraciones = (p) => <Integraciones {...p} />;
export const GdSeguridad = (p) => <Seguridad {...p} />;
export const GdSaludSistema = (p) => <SaludSistema {...p} />;

// Periféricos (UI-14) — pendiente:
export const GdAdminPerifericos = (p) => (
  <ShellWrapper {...p} title="Periféricos autorizados" bloqueNum={14} />
);

// Auditoría + Reportes consolidados (UI-11) — vistas reales:
export const GdAuditoria = (p) => <BandejaAuditoria {...p} />;
export const GdAuditoriaEvento = (p) => <EventoAuditoriaFicha {...p} />;
export const GdReportes = (p) => <ReportesConsolidados {...p} />;
export const GdVistaAuditor = (p) => <VistaAuditor {...p} />;

// IA embebida (UI-12) — vistas reales:
export const GdBuscarSemantico = (p) => <BusquedaSemantica {...p} />;
export const GdAsistente = (p) => <Asistente {...p} />;
export const GdDeteccionPII = (p) => <DeteccionPII {...p} />;
export const GdPanelUsoIA = (p) => <PanelUsoIA {...p} />;
export const GdConfigModelosIA = (p) => <ConfigModelosIA {...p} />;

// Búsqueda global → vista real bloque UI-3
export const GdBuscar = (p) => <BuscarRadicados {...p} />;

// Consulta (rol consulta) - reusa búsqueda en modo R
export const GdConsulta = (p) => <BuscarRadicados {...p} />;

// Landing (bienvenida)
export function GdHome(props) {
  return (
    <GdShell
      {...props}
      breadcrumbs={[{ label: 'Gestión Documental' }]}
      currentPath="/gd"
    >
      <GdLanding {...props} />
    </GdShell>
  );
}
