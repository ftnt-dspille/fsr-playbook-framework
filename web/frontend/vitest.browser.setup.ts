/**
 * Browser-mode setup. Real Chromium has all the DOM APIs Monaco needs
 * (ResizeObserver, matchMedia, layout boxes, requestAnimationFrame),
 * so the only thing to wire here is Monaco's worker shim — using
 * editor-only languages without workers keeps the bundle slim and
 * avoids vite worker-resolution gymnastics in the test runner.
 *
 * @ts-expect-error Monaco's worker contract is loose; this stub is
 * intentionally minimal — Monaco falls back to inline tokenization
 * when getWorker returns no usable Worker.
 */
import '@testing-library/jest-dom/vitest';

// Monaco looks at self.MonacoEnvironment for worker URLs. With no
// configured worker URL it logs a one-time warning but continues to
// function for the editor.api surface — which is what our tests use.
// Monaco's editor.dispose() cancels in-flight language-service promises
// with a sentinel rejection (`Canceled`) that Vitest otherwise surfaces
// as an unhandled error. Swallow only that exact kind.
window.addEventListener('unhandledrejection', (e) => {
  const r: any = (e as any).reason;
  if (r && (r.name === 'Canceled' || r.message === 'Canceled')) {
    e.preventDefault();
  }
});

(self as any).MonacoEnvironment = {
  getWorker: () => {
    // Minimal Worker-like stub. Monaco posts messages to it for
    // language services; we don't assert on language-service output.
    return {
      postMessage: () => {},
      terminate: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      onmessage: null,
      onerror: null
    } as unknown as Worker;
  }
};
