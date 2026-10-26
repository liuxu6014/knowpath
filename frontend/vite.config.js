import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  base: '/',
  root: fileURLToPath(new URL('.', import.meta.url)),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: fileURLToPath(new URL('./index.html', import.meta.url)),
    },
  },
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:9099',
      '/health': process.env.VITE_API_TARGET || 'http://127.0.0.1:9099',
      '/media': process.env.VITE_API_TARGET || 'http://127.0.0.1:9099',
    },
  },
  preview: {
    port: 4173,
    host: '0.0.0.0',
    proxy: {
      '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:9099',
      '/health': process.env.VITE_API_TARGET || 'http://127.0.0.1:9099',
      '/media': process.env.VITE_API_TARGET || 'http://127.0.0.1:9099',
    },
  },
});
