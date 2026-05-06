import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    port: 47822,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:47821', changeOrigin: true }
    }
  }
});
