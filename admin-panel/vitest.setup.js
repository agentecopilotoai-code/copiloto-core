import '@testing-library/jest-dom/vitest';
import * as axeMatchers from 'vitest-axe/matchers';
import { expect } from 'vitest';

// UI-013 — habilita `expect(...).toHaveNoViolations()` y similares de axe-core
// para los smokes de accesibilidad bajo `src/__tests__/a11y/`.
expect.extend(axeMatchers);

// UI-014 — Node 24 + JSDOM: parche para `new Request(..., { signal })`.
//
// JSDOM redefine globalThis.AbortController / AbortSignal con su propia
// implementación basada en WebIDL. Node 24 trae un undici interno (usado
// por el constructor global `Request`, que `@remix-run/router` invoca en
// `createClientSideRequest`) cuyo webidl exige que `init.signal` sea
// instancia de la clase nativa de AbortSignal de undici. Como JSDOM ya
// pisó la clase global, todo `signal` que llegue al Request falla el
// `instanceof` y se lanza:
//
//   TypeError: RequestInit: Expected signal ("AbortSignal {}") to be an
//   instance of AbortSignal.
//
// Esto rompe cualquier `router.navigate(...)` en los tests del router.
//
// Solución: envolvemos el constructor global `Request` con un Proxy que
// retira `signal` del init si éste no es del tipo nativo esperado. El
// signal en estos tests sólo sirve para que el router pueda cancelar
// navegaciones in-flight, lo cual no ejercitamos en unit tests. Esto
// preserva 100% del comportamiento que sí importa (URL, método, headers,
// body) y evita el instanceof check fallido.
//
// En Node 20 (CI) y en entornos sin JSDOM, `probeReq.signal` ya es
// instancia del global `AbortSignal` y el proxy es un no-op — el signal
// pasa intacto. Por eso es seguro instalarlo siempre.
//
// Refs: https://github.com/nodejs/undici/issues/2510
try {
  const OriginalRequest = globalThis.Request;
  if (typeof OriginalRequest === 'function') {
    // Detectamos si el constructor `Request` global acepta el `signal` que
    // produce el `AbortController` global. En entorno JSDOM bajo Node 24
    // estos pertenecen a clases distintas a las que la copia interna de
    // undici espera y el constructor lanza:
    //   "RequestInit: Expected signal ... to be an instance of AbortSignal."
    // Probamos construyendo un Request con un signal real y, si falla,
    // envolvemos el constructor con un Proxy que descarta `signal` del init.
    let needsPatch = false;
    try {
      const probeAc = new globalThis.AbortController();
      // eslint-disable-next-line no-new
      new OriginalRequest('http://localhost/__probe__', { signal: probeAc.signal });
    } catch {
      needsPatch = true;
    }
    if (needsPatch) {
      // El `signal` en los unit tests del router sólo sirve para que el
      // router pueda cancelar navegaciones in-flight (no lo ejercitamos).
      // Lo retiramos del init para que `new Request(...)` no haga el
      // instanceof check fallido contra la clase nativa de undici.
      globalThis.Request = new Proxy(OriginalRequest, {
        construct(target, args, newTarget) {
          const init = args[1];
          if (init && 'signal' in init) {
            const safeInit = { ...init };
            delete safeInit.signal;
            return Reflect.construct(target, [args[0], safeInit], newTarget);
          }
          return Reflect.construct(target, args, newTarget);
        },
      });
    }
  }
} catch {
  // no-op: si algo falla aquí, los tests fallarán por la causa raíz y
  // será más fácil diagnosticar que silenciado en una excepción de setup.
}
