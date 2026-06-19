/**
 * Configure `self.MonacoEnvironment` so Monaco can spawn the base
 * editor worker. Without this, Monaco logs:
 *
 *   "You must define a function MonacoEnvironment.getWorkerUrl or
 *    MonacoEnvironment.getWorker"
 *
 * …and silently degrades features (link detection, tokenization
 * helpers, etc.). We register ONLY the base editor worker —
 * language-specific workers (json, css, html, typescript) aren't
 * needed because `disableJsonLanguageWorker` in monacoYamlSupport
 * turns off every json feature that would require them.
 *
 * Import this module once, BEFORE any other module imports
 * `monaco-editor`. The +layout does that.
 */
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

// Idempotent — multiple imports of the module just re-assign the
// same MonacoEnvironment object.
(self as any).MonacoEnvironment = {
  getWorker: (_workerId: string, _label: string) => new editorWorker()
};
