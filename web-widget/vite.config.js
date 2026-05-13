// Vite config for the CDN-distributed embeddable chat widget (TASK-0070).
// Produces a single IIFE bundle that runs on any HTML page and an extracted
// CSS file. Both artifacts are uploaded to s3://copilotoia-cdn/widget/v1/.
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    target: 'es2019',
    minify: 'esbuild',
    cssMinify: true,
    sourcemap: false,
    emptyOutDir: true,
    outDir: 'dist',
    rollupOptions: {
      input: 'src/main.js',
      output: {
        format: 'iife',
        entryFileNames: 'widget.js',
        assetFileNames: (asset) =>
          asset.name && asset.name.endsWith('.css') ? 'widget.css' : '[name][extname]',
        inlineDynamicImports: true,
        manualChunks: undefined,
      },
    },
    cssCodeSplit: false,
    reportCompressedSize: true,
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
  },
});
