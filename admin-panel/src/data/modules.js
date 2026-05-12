export const adminModules = [
  {
    id: 'tenant-setup',
    label: 'Tenant Setup',
    summary: 'Wizard de configuración general del tenant.',
    scope: ['Crear tenant', 'Editar settings', 'Horarios y escalamiento', 'PII policy y no_train'],
  },
  {
    id: 'services',
    label: 'Servicios',
    summary: 'Catálogo de servicios del negocio con precio, duración e instrucciones.',
    scope: ['Crear/editar servicios', 'Reordenar', 'Activar/desactivar', 'Instrucciones pre y post servicio'],
  },
  {
    id: 'whatsapp',
    label: 'WhatsApp',
    summary: 'Onboarding y salud del canal WhatsApp/WABA.',
    scope: ['Business ID', 'WABA ID', 'Phone Number ID', 'Referencias de token y app secret'],
  },
  {
    id: 'knowledge-storage',
    label: 'Storage S3',
    summary: 'Configuración del bucket/prefix de conocimiento por tenant.',
    scope: ['Backend local o S3', 'Bucket único por tenant', 'Credenciales fuera de DB', 'Prefix de documentos'],
  },
  {
    id: 'knowledge-studio',
    label: 'Knowledge Studio',
    summary: 'Gestión de documentos, FAQ y políticas por tenant.',
    scope: ['Estados draft/indexing/active/failed', 'Visibilidad por documento', 'Fuentes y archivos'],
  },
  {
    id: 'media-library',
    label: 'Medios y promociones',
    summary: 'Imágenes, videos y promociones que el bot puede enviar durante el booking.',
    scope: ['Subir fotos, videos y PDFs', 'Etiquetar y buscar', 'Crear promociones', 'Vincular promoción → servicio'],
    minRole: 'admin',
  },
  {
    id: 'contacts',
    label: 'Contactos',
    summary: 'CRM básico: perfil de contacto con historial, etiquetas y notas internas.',
    scope: ['Búsqueda y filtros', 'Perfil con historial', 'Etiquetas asignables', 'Notas internas'],
  },
  {
    id: 'campaigns',
    label: 'Campañas',
    summary: 'Mensajes masivos a segmentos de contactos vía templates aprobados.',
    scope: ['Segmentar por etiquetas y citas', 'Previsualizar destinatarios', 'Programar envío', 'Métricas de entrega'],
    minRole: 'admin',
  },
  {
    id: 'operations-desk',
    label: 'Operations Desk',
    summary: 'Inbox operativo para conversaciones y handoff humano.',
    scope: ['Conversaciones', 'Mensajes', 'Tomar/liberar handoff', 'Auditoría operacional'],
  },
  {
    id: 'go-live-readiness',
    label: 'Go-live Readiness',
    summary: 'Checklist automatizado para validar si un tenant puede entrar a producción controlada.',
    scope: ['Tenant activo', 'Settings y WhatsApp', 'Retrieval smoke test', 'Handoff y auditoría'],
  },
  {
    id: 'analytics',
    label: 'Analítica',
    summary: 'KPIs de conversaciones, citas, ingresos, retención y no-show del negocio.',
    scope: ['Rangos 7d/30d/90d', 'Top intenciones y servicios', 'Evolución diaria', 'Distribución por estado'],
  },
  {
    id: 'audit',
    label: 'Audit',
    summary: 'Trazabilidad de cambios y acciones administrativas.',
    scope: ['Logs de auditoría', 'Actor y entidad', 'Filtros por tenant', 'Evidencia para cumplimiento'],
  },
  {
    id: 'team',
    label: 'Equipo',
    summary: 'Miembros, roles e invitaciones del tenant.',
    scope: ['Invitar usuarios', 'Cambiar rol', 'Revocar acceso', 'Sincronización con Auth0'],
    minRole: 'admin',
  },
];

export const defaultModuleId = adminModules[0].id;
