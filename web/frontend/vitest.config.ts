import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: {
    alias: {
      $lib: new URL('./src/lib', import.meta.url).pathname,
      'monaco-editor': new URL('./src/lib/__mocks__/monaco-editor.ts', import.meta.url).pathname
    },
    conditions: ['browser']
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    setupFiles: ['./vitest.setup.ts']
  }
});
