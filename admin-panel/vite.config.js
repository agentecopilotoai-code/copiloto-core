import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/admin/api': 'http://127.0.0.1:3000',
      '/admin/login': 'http://127.0.0.1:3000',
      '/admin/logout': 'http://127.0.0.1:3000',
    },
  },
});
