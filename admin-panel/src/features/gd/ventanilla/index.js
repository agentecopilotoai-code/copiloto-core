/**
 * Punto de entrada del sub-módulo Ventanilla Única (GD-UI EP-002).
 */
export { VentanillaHome } from './VentanillaHome.jsx';
export { NuevoRadicadoEntrada } from './NuevoRadicadoEntrada.jsx';
export { NuevoRadicadoSalida } from './NuevoRadicadoSalida.jsx';
export { ColaVentanilla } from './ColaVentanilla.jsx';
export {
  RadicadoConstanciaPreview,
} from './RadicadoConstanciaPreview.jsx';
export {
  VerificarConstanciaPublica,
} from './VerificarConstanciaPublica.jsx';
export {
  useCrearRadicadoEntrada,
  useCrearRadicadoSalida,
  useColaPendientesClasificacion,
  useClasificarRadicado,
} from './useGdRadicados.js';
