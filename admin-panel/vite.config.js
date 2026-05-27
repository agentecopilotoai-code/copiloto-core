import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // PERF-NEW-2 (audit #3) — vendor split. Sin esto, react/router/etc
    // rebundlean en `index-*.js` con cada code change → invalida cache
    // HTTP del browser. Con `manualChunks` el vendor queda en su propio
    // chunk hash-stable, los users no re-descargan ~120 KB de libs por
    // cada deploy que solo cambie nuestro código.
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/admin/api': 'http://127.0.0.1:3000',
      '/admin/login': 'http://127.0.0.1:3000',
      '/admin/logout': 'http://127.0.0.1:3000',
    },
  },
});
