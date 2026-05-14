/**
 * Tarjeta genérica para mostrar cuando un usuario no tiene la capability
 * requerida en el tenant activo. No reemplaza el 403 del servidor — sólo
 * evita que la UI pinte controles que el backend rechazará.
 */
export function AccessDenied({ capability, mode = 'R', children }) {
  return (
    <section className="module-card" role="status" aria-live="polite">
      <h2>Acceso restringido</h2>
      <p className="hint">
        Tu rol en este tenant no permite{' '}
        <strong>{mode === 'RW' ? 'editar' : 'ver'}</strong>{' '}
        <code>{capability}</code>. Cambia de tenant o pide a un admin del
        tenant que te promocione.
      </p>
      {children}
    </section>
  );
}
