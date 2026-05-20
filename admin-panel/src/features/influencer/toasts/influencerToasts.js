/**
 * UI-INFLU-007 — Helpers para los 4 toasts específicos del módulo
 * Influencer. Cada uno devuelve el shape esperado por `useToast().push()`.
 */

/**
 * "Generación completada · 4 imágenes listas" — success con thumbnail
 * del primer asset (URL S3 o data URL).
 */
export function generationCompletedToast({ count, thumbnailUrl, onOpen }) {
  const safeCount = Math.max(1, Number(count) || 1);
  return {
    tone: 'success',
    title: 'Generación completada',
    message: `${safeCount} ${safeCount === 1 ? 'asset listo' : 'assets listos'}`,
    thumbnail: thumbnailUrl || null,
    action: onOpen ? { label: 'Ver', onClick: onOpen } : null,
  };
}


/**
 * "Crédito insuficiente · faltan N" — warn con CTA top-up.
 */
export function insufficientCreditsToast({ shortBy, onTopUp }) {
  return {
    tone: 'warn',
    title: 'Crédito insuficiente',
    message: `Faltan ${shortBy} créditos para completar esta acción.`,
    action: onTopUp ? { label: 'Top-up', onClick: onTopUp } : null,
  };
}


/**
 * "Provider Grok temporalmente caído · usando OpenAI" — info auto-dismiss 8s.
 */
export function providerFallbackToast({ failedProvider, usingProvider }) {
  return {
    tone: 'info',
    title: `Provider ${failedProvider} temporalmente caído`,
    message: `Usando ${usingProvider} mientras tanto.`,
    timeout: 8000,
  };
}


/**
 * "Publicación a Instagram falló · token expirado" — error con CTA
 * reconectar OAuth.
 */
export function publishFailedToast({ platform, reason, onReconnect }) {
  const reasonLabel = reason === 'token_expired'
    ? 'Token expirado'
    : reason === 'rate_limit'
      ? 'Límite de rate excedido'
      : reason === 'content_rejected'
        ? 'Contenido rechazado por la plataforma'
        : 'Error desconocido';
  return {
    tone: 'error',
    title: `Publicación a ${platform} falló`,
    message: reasonLabel,
    action: onReconnect ? { label: 'Reconectar', onClick: onReconnect } : null,
  };
}
