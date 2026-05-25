import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// D-ROUTES-01 (2026-05-25): base movido a '/' para que las URLs literales
// en el navegador sean `/gd/t/{slug}/...`, `/admin/...`, etc. (sin prefijo
// `/admin/` para los módulos tenant-scoped). El backend FastAPI sirve los
// assets de `dist/assets/*` directamente en `/assets/*` y hace SPA fallback
// para `/admin/*`, `/gd/*`, `/influencer/*`, `/chatbot/*` (ver
// `app/admin/routes.py`).
export default defineConfig({
  base: '/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    // Proxy de endpoints del BFF al backend admin-panel (puerto 3000).
    // Los endpoints siguen bajo `/admin/api/*` y `/admin/login|logout|callback`
    // porque la API del BFF no cambia — solo cambia la URL del SPA.
    proxy: {
      '/admin/api': 'http://127.0.0.1:3000',
      '/admin/login': 'http://127.0.0.1:3000',
      '/admin/logout': 'http://127.0.0.1:3000',
      '/admin/callback': 'http://127.0.0.1:3000',
    },
  },
});
