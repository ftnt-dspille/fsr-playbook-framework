/**
 * Two-project Vitest setup:
 *
 *   1. jsdom  — fast unit tests, monaco-editor aliased to a tiny mock
 *               in src/lib/__mocks__/. Used by *.test.ts.
 *   2. browser — real Chromium via Playwright. No alias, so monaco-editor
 *                resolves to the real npm package. Used by *.browser.test.ts
 *                for integration assertions (completion popup opens,
 *                snippet expansion lands in the model, hover bubble
 *                appears, marker squiggles render). Run only these with
 *                `npx vitest run --project browser`.
 */
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';

const lib = new URL('./src/lib', import.meta.url).pathname;
const monacoMock = new URL('./src/lib/__mocks__/monaco-editor.ts', import.meta.url).pathname;

export default defineConfig({
  test: {
    projects: [
      {
        plugins: [svelte({ hot: false })],
        resolve: {
          alias: { $lib: lib, 'monaco-editor': monacoMock },
          conditions: ['browser']
        },
        test: {
          name: 'jsdom',
          environment: 'jsdom',
          include: ['src/**/*.test.ts'],
          exclude: ['src/**/*.browser.test.ts', 'node_modules/**'],
          setupFiles: ['./vitest.setup.ts']
        }
      },
      {
        plugins: [svelte({ hot: false })],
        resolve: {
          alias: { $lib: lib },
          conditions: ['browser']
        },
        test: {
          name: 'browser',
          include: ['src/**/*.browser.test.ts'],
          setupFiles: ['./vitest.browser.setup.ts'],
          browser: {
            enabled: true,
            provider: playwright(),
            headless: true,
            instances: [{ browser: 'chromium' }]
          }
        }
      }
    ]
  }
});
