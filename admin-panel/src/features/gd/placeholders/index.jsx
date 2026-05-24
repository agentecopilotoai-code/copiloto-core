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
} from '../ventanilla/index.js';

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

// Ventanilla — vistas reales (bloque UI-2):
export const GdVentanillaHome = (p) => <VentanillaHome {...p} />;
export const GdNuevoRadicado = (p) => <NuevoRadicadoEntrada {...p} />;
export const GdNuevoRadicadoSalida = (p) => <NuevoRadicadoSalida {...p} />;
export const GdColaVU = (p) => <ColaVentanilla {...p} />;
// Ficha de radicado pendiente para bloque UI-3.
export const GdRadicadoFicha = (p) => (
  <ShellWrapper {...p} title="Ficha de radicado" bloqueNum={3} />
);

// Buzón (UI-4)
export const GdBuzonHome = (p) => (
  <ShellWrapper {...p} title="Mi buzón" bloqueNum={4} />
);
export const GdBuzonDependencia = (p) => (
  <ShellWrapper {...p} title="Buzón de dependencia" bloqueNum={4} />
);

// PQRSD (UI-5/UI-6)
export const GdPqrsdPanel = (p) => (
  <ShellWrapper {...p} title="Panel PQRSD" bloqueNum={5} />
);
export const GdPqrsdFicha = (p) => (
  <ShellWrapper {...p} title="Ficha PQRSD" bloqueNum={5} />
);

// Correspondencia (UI-7)
export const GdCorrespondenciaInterna = (p) => (
  <ShellWrapper {...p} title="Correspondencia interna" bloqueNum={7} />
);
export const GdCorrespondenciaExterna = (p) => (
  <ShellWrapper {...p} title="Correspondencia externa" bloqueNum={7} />
);

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

// Búsqueda global
export const GdBuscar = (p) => (
  <ShellWrapper {...p} title="Búsqueda global" bloqueNum={3} />
);

// Consulta (rol consulta)
export const GdConsulta = (p) => (
  <ShellWrapper {...p} title="Consulta" bloqueNum={3} />
);

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
