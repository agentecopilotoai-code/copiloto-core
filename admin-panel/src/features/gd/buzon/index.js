/**
 * Punto de entrada del sub-módulo Buzón de trabajo (EP-003).
 */
export { MiBuzon } from './MiBuzon.jsx';
export { BuzonDependencia } from './BuzonDependencia.jsx';
export { TareaFicha } from './TareaFicha.jsx';
export { ReasignacionMasiva } from './ReasignacionMasiva.jsx';
export { UsuarioPicker } from './UsuarioPicker.jsx';
export {
  CARPETAS,
  useMiBuzon,
  useBuzonDependencia,
  useCargaEquipo,
  useTarea,
  useAccionTarea,
  useUsuariosDependencia,
  useTareasPendientesUsuario,
  useReasignarTareasLote,
} from './useGdBuzon.js';
