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

// Documentos + plantillas + firmas (UI-8)
export const GdBiblioteca = (p) => (
  <ShellWrapper {...p} title="Biblioteca documental" bloqueNum={8} />
);
export const GdPlantillas = (p) => (
  <ShellWrapper {...p} title="Plantillas documentales" bloqueNum={8} />
);
export const GdPorFirmar = (p) => (
  <ShellWrapper {...p} title="Documentos por firmar" bloqueNum={8} />
);

// TRD/TVD (UI-9)
export const GdTrdHome = (p) => (
  <ShellWrapper {...p} title="TRD / TVD" bloqueNum={9} />
);
export const GdExpedientes = (p) => (
  <ShellWrapper {...p} title="Expedientes electrónicos" bloqueNum={9} />
);

// Admin (UI-10)
export const GdAdminUsuarios = (p) => (
  <ShellWrapper {...p} title="Administración de usuarios" bloqueNum={10} />
);
export const GdAdminEstructura = (p) => (
  <ShellWrapper {...p} title="Estructura orgánica" bloqueNum={10} />
);
export const GdAdminCatalogos = (p) => (
  <ShellWrapper {...p} title="Catálogos institucionales" bloqueNum={10} />
);
export const GdAdminParametros = (p) => (
  <ShellWrapper {...p} title="Parámetros institucionales" bloqueNum={10} />
);
export const GdAdminPerifericos = (p) => (
  <ShellWrapper {...p} title="Periféricos autorizados" bloqueNum={14} />
);
export const GdSeguridad = (p) => (
  <ShellWrapper {...p} title="Seguridad" bloqueNum={10} />
);

// Auditoría (UI-11)
export const GdAuditoria = (p) => (
  <ShellWrapper {...p} title="Auditoría" bloqueNum={11} />
);
export const GdReportes = (p) => (
  <ShellWrapper {...p} title="Reportes consolidados" bloqueNum={11} />
);

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
