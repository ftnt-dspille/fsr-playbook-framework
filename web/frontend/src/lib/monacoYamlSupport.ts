/**
 * Idempotent register of the YAML / Jinja Monaco providers
 * (completion + step-args hover + jinja-path hover + jinja language).
 *
 * Called by every editor that wants the Jinja autocomplete experience —
 * MonacoYaml.svelte (the big editor), MonacoCode.svelte when its
 * language prop is `yaml` (inline value editors like set_variable
 * rows). Dedupes on the monaco namespace so we don't get duplicate
 * suggestions when multiple editors mount.
 *
 * Also registers the standalone `jinja` language and replaces the
 * YAML tokenizer with a combined YAML+Jinja one so `{{ … }}` /
 * `{% … %}` / `{# … #}` inside playbook YAML get proper highlighting.
 */
import { registerYamlCompletions } from './yamlCompletions';
import { registerYamlHover } from './yamlHover';
import { registerJinjaHover } from './jinjaHover';
import { registerJinja } from './jinja/registerJinja';
import { yamlJinjaTokens } from './jinja/yamlJinjaTokens';

const registered = new WeakSet<object>();

export function ensureYamlSupport(monaco: any): void {
  if (!monaco || registered.has(monaco)) return;
  registered.add(monaco);
  registerYamlCompletions(monaco);
  registerYamlHover(monaco);
  registerJinjaHover(monaco);
  registerJinja(monaco);
  // Replace the YAML monarch tokenizer with our combined YAML+Jinja
  // one so `{{ … }}` regions render with the jinja palette inside
  // every YAML buffer.
  //
  // Race note: monaco-editor's basic-languages bundle loads each
  // language's tokenizer ASYNCHRONOUSLY on first `editor.create({
  // language: 'yaml' })`. If we call setMonarchTokensProvider eagerly
  // here, the lazy yaml module loads a moment later and overwrites
  // our tokens, so `{{ … }}` inside a YAML buffer reverts to plain
  // string coloring. Belt-and-suspenders: install once now (covers
  // the already-loaded case), again via onLanguage (fires on the
  // first language request), and once more deferred via setTimeout
  // so we always land AFTER basic-languages' async load resolves.
  const apply = () => monaco.languages.setMonarchTokensProvider('yaml', yamlJinjaTokens);
  apply();
  monaco.languages.onLanguage('yaml', () => {
    apply();
    setTimeout(apply, 0);
    setTimeout(apply, 50);
  });
  setTimeout(apply, 250);

  // Disable Monaco's json language worker. The worker provides
  // validation / formatting / schema-driven IntelliSense — none of
  // which this app uses. The worker fails to load in our Vite dev
  // setup (`_FileAccessImpl.toUri` blows up because workers aren't
  // configured), so the only effect of leaving it on is a console
  // exception when the Jinja test modal mounts its JSON pane. Keep
  // tokens:true so syntax highlighting (main-thread) still works.
  disableJsonLanguageWorker(monaco);
}

function disableJsonLanguageWorker(monaco: any) {
  const configure = () => {
    const defaults = monaco.languages.json?.jsonDefaults;
    if (!defaults) return;
    defaults.setModeConfiguration?.({
      documentFormattingEdits: false,
      documentRangeFormattingEdits: false,
      completionItems: false,
      hovers: false,
      documentSymbols: false,
      tokens: true,
      colors: false,
      foldingRanges: false,
      diagnostics: false,
      selectionRanges: false
    });
    defaults.setDiagnosticsOptions?.({
      validate: false,
      allowComments: true,
      schemas: [],
      enableSchemaRequest: false
    });
  };
  if (monaco.languages.json) configure();
  else if (typeof monaco.languages.onLanguage === 'function') {
    monaco.languages.onLanguage('json', configure);
  }
}
