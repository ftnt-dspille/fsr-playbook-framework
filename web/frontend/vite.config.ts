import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Port + API target are env-driven so the e2e suite can boot a second
// vite instance on a separate port that proxies to its own isolated
// backend, without colliding with the developer's running dev session.
const PORT = Number(process.env.VITE_PORT ?? 47822);
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://localhost:47821';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    port: PORT,
    strictPort: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true }
    }
  }
});
