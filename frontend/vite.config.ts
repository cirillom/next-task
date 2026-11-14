import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';
import { localizedShell } from './i18n-shell.mjs';

export default defineConfig({
  plugins: [svelte(), localizedShell()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    fs: { allow: ['..'] },
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
});

