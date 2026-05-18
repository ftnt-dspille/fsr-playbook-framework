<script lang="ts">
  /**
   * Jinja test modal — opened from the editor toolbar's "ƒ Jinja"
   * button. Three-pane scratchpad mirroring the FortiSOAR widget's
   * view.html layout:
   *
   *   Input (JSON) │ Template (Jinja) │ Output
   *
   * The Input pane is the *full* context handed to the engine, so
   * users can reference `vars.input.records[0]` etc. directly. We do
   * NOT auto-derive it from the playbook here — for that there's the
   * inline preview inside set_variable rows. This modal is a clean
   * scratchpad with no assumed wiring.
   *
   * "Insert example…" swaps the template only; the user's input JSON
   * is preserved (matches the widget's behavior). The "Load with
   * input" link in the example dropdown's tooltip is not provided;
   * use the example's input pane explicitly if needed.
   */
  import MonacoCode from './MonacoCode.svelte';
  import JinjaToolbar from './JinjaToolbar.svelte';
  import { callMcpTool } from '$lib/api';
  import { templateExamples, type JinjaTemplateExample } from '$lib/jinja/jinjaTemplates';
  import {
    translateJinjaError,
    parseErrorLineNumber,
    findUnclosedTagLine,
    setJinjaErrorMarker,
    scanTemplate,
    checkInputPaths,
    applyJinjaFindings
  } from '$lib/jinja/jinjaErrors';
  import { setInputContext } from '$lib/jinja/registerJinja';
  import { filterSignatures } from '$lib/jinja/jinjaFilters';

  const knownFilters = new Set(Object.keys(filterSignatures));

  type Props = { onClose: () => void };
  let { onClose }: Props = $props();

  let inputText = $state(
    JSON.stringify(
      { vars: { input: { records: [{ name: 'Ada Lovelace', email: 'ada@example.com' }] } } },
      null,
      2
    )
  );
  let template = $state("Hello, {{ vars.input.records[0].name | default('stranger') }}!");

  let output = $state<string>('');
  let outputKind = $state<'idle' | 'rendered' | 'error'>('idle');
  let busy = $state(false);
  let pickedExampleId = $state<string>('');
  let savedInputBeforeExample = $state<string | null>(null);

  // Captured from MonacoCode.onEditor so we can paint inline error
  // markers on the template buffer when render fails (matches the
  // widget's setTemplateErrorMarker behavior).
  let templateEditor = $state<any>(null);
  let templateMonaco = $state<any>(null);

  // Re-scan the template on every change so unclosed `{{ }}` / `{% %}`,
  // mismatched end tags, and unknown filter names get red squiggles
  // *before* the user clicks Render (mirrors widget's scanTemplate +
  // checkInputPaths). Also push the parsed Input JSON into the
  // shared jinja member-completion context so `vars.input.records[0].`
  // autocompletes against the user's actual JSON.
  let parsedInput = $derived.by(() => {
    if (inputJsonError) return null;
    try {
      return inputText.trim() ? JSON.parse(inputText) : null;
    } catch {
      return null;
    }
  });

  $effect(() => {
    setInputContext(parsedInput);
  });

  // Live scan: every template/input edit runs scanTemplate +
  // checkInputPaths and applies markers. Render also calls
  // runScanAndApply() so the same logic gates a Render error path.
  // Debounced 250 ms so we don't repaint mid-token.
  let scanTimer: any = null;

  function runScanAndApply() {
    if (!templateEditor || !templateMonaco) return false;
    const structural = scanTemplate(template, knownFilters);
    const pathFindings = parsedInput ? checkInputPaths(template, parsedInput) : [];
    const all = [...structural, ...pathFindings];
    applyJinjaFindings(templateEditor, templateMonaco, all);
    return all.length > 0;
  }

  $effect(() => {
    if (!templateEditor || !templateMonaco) return;
    void template;
    void parsedInput;
    if (scanTimer) clearTimeout(scanTimer);
    scanTimer = setTimeout(runScanAndApply, 250);
  });

  let inputJsonError = $derived.by(() => {
    if (!inputText.trim()) return null;
    try {
      const v = JSON.parse(inputText);
      if (typeof v !== 'object' || v === null || Array.isArray(v)) {
        return 'Input must be a JSON object.';
      }
      return null;
    } catch (e: any) {
      return e?.message ?? 'Invalid JSON';
    }
  });

  async function run() {
    if (inputJsonError) return;
    busy = true;
    output = '';
    outputKind = 'idle';
    setJinjaErrorMarker(templateEditor, templateMonaco, null, '');

    // Render triggers an immediate scan too (the live $effect is
    // debounced, so a fast Render click could fire before the scan
    // catches up). Findings are merged with the engine's reply
    // below.
    runScanAndApply();

    try {
      const ctx = inputText.trim() ? JSON.parse(inputText) : {};
      const res = await callMcpTool<{ output?: unknown; error?: string }>('render_jinja', {
        template,
        context: ctx
      });
      const rawErr = !res.ok ? res.error : res.result?.error;
      if (rawErr) {
        const translated = translateJinjaError(rawErr);
        output = `Error: ${translated}`;
        outputKind = 'error';
        const line = parseErrorLineNumber(rawErr) ?? findUnclosedTagLine(template);
        setJinjaErrorMarker(templateEditor, templateMonaco, line, translated);
      } else {
        const val = res.result?.output;
        output = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
        outputKind = 'rendered';
      }
    } catch (e: any) {
      output = `Error: ${e?.message ?? String(e)}`;
      outputKind = 'error';
    } finally {
      busy = false;
    }
  }

  function loadExample(ev: Event) {
    const id = (ev.target as HTMLSelectElement).value;
    pickedExampleId = id;
    if (!id) return;
    const t = templateExamples.find((x) => x.id === id) as JinjaTemplateExample | undefined;
    if (!t) return;
    // Stash current input so the user can revert; replace template
    // only, mirroring the widget's behavior.
    savedInputBeforeExample = inputText;
    template = t.template;
  }

  function loadExampleInput() {
    if (!pickedExampleId) return;
    const t = templateExamples.find((x) => x.id === pickedExampleId);
    if (!t) return;
    savedInputBeforeExample = inputText;
    inputText = JSON.stringify(t.input, null, 2);
  }

  function revertInput() {
    if (savedInputBeforeExample === null) return;
    inputText = savedInputBeforeExample;
    savedInputBeforeExample = null;
  }

  function formatInput() {
    if (inputJsonError) return;
    try {
      inputText = JSON.stringify(JSON.parse(inputText), null, 2);
    } catch {
      // already gated by inputJsonError; no-op
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run();
  }

  async function copyTemplate() {
    try {
      await navigator.clipboard.writeText(template);
    } catch {
      // best-effort
    }
  }

  // Portal the dialog to <body> so a transformed/contained ancestor
  // can't anchor the `position: fixed` overlay below the page chrome.
  // Copy the active data-theme from <html> onto the portaled node so
  // CSS variables (defined on :root[data-theme=…]) cascade to the
  // dialog even when it's adopted into a sibling subtree.
  function portal(node: HTMLElement) {
    const theme = document.documentElement.getAttribute('data-theme');
    if (theme) node.setAttribute('data-theme', theme);
    document.body.appendChild(node);
    return { destroy: () => node.parentNode?.removeChild(node) };
  }
</script>

<svelte:window onkeydown={onKey} />

<div
  use:portal
  role="dialog"
  tabindex="-1"
  aria-modal="true"
  aria-label="Test Jinja expression"
  style="position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.55);"
  class="flex items-center justify-center p-6"
>
  <div
    class="flex h-[85vh] w-[1280px] max-w-full flex-col rounded-lg border shadow-2xl"
    style="background: var(--bg-panel, #0c0c0f); border-color: var(--border-soft, #1d1d22); color: var(--text-default, #e4e4e7);"
  >
    <header class="flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-2">
      <div class="flex items-center gap-3">
        <span class="text-[13px] font-semibold text-[var(--text-default)]">Test Jinja expression</span>
        <span class="text-[11px] text-[var(--text-muted)]">⌘/Ctrl-Enter to render • Esc to close</span>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[11px] text-[var(--text-default)] hover:bg-[var(--bg-elevated)]"
          onclick={copyTemplate}
          title="Copy the current template to the clipboard"
        >Copy template</button>
        <button type="button" class="rounded px-2 py-0.5 text-[14px] text-[var(--text-muted)] hover:text-[var(--text-default)]" onclick={onClose} aria-label="Close">✕</button>
      </div>
    </header>

    <div class="grid flex-1 grid-cols-3 gap-3 overflow-hidden p-3">
      <!-- ── Input ─────────────────────────────────────────────────── -->
      <section class="flex flex-col overflow-hidden">
        <div class="mb-1 flex items-center justify-between">
          <span class="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">Input (JSON)</span>
          <div class="flex gap-1">
            {#if savedInputBeforeExample !== null}
              <button
                type="button"
                class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[11px] text-[var(--text-default)] hover:bg-[var(--bg-elevated)]"
                onclick={revertInput}
                title="Revert to the input you had before loading an example"
              >Revert</button>
            {/if}
            <button
              type="button"
              class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[11px] text-[var(--text-default)] hover:bg-[var(--bg-elevated)] disabled:opacity-60"
              onclick={formatInput}
              disabled={!!inputJsonError}
            >Format</button>
          </div>
        </div>
        <p class="mb-1 text-[11px] text-[var(--text-muted)]">JSON object available to the template (e.g. <code class="font-mono">vars.input.records[0]</code>).</p>
        <div class="flex-1 overflow-hidden">
          <MonacoCode language="json" value={inputText} onInput={(v) => (inputText = v)} height="100%" />
        </div>
        {#if inputJsonError}
          <p class="mt-1 text-[11px] text-red-400">Input JSON is malformed: {inputJsonError}</p>
        {/if}
      </section>

      <!-- ── Template ──────────────────────────────────────────────── -->
      <section class="flex flex-col overflow-hidden">
        <div class="mb-1 flex items-center justify-between gap-2">
          <span class="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">Jinja template <span class="text-red-400">*</span></span>
          <div class="flex items-center gap-1">
            {#if templateEditor && templateMonaco}
              <JinjaToolbar editor={templateEditor} monaco={templateMonaco} />
            {/if}
            {#if pickedExampleId}
              <button
                type="button"
                class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[11px] text-[var(--text-default)] hover:bg-[var(--bg-elevated)]"
                onclick={loadExampleInput}
                title="Also load this example's input JSON"
              >+ input</button>
            {/if}
            <select
              class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[11px] text-[var(--text-default)]"
              value={pickedExampleId}
              onchange={loadExample}
              aria-label="Insert example template"
              title="Replaces the template only — input JSON is preserved"
            >
              <option value="">Insert example…</option>
              {#each templateExamples as t}
                <option value={t.id}>{t.label}</option>
              {/each}
            </select>
          </div>
        </div>
        <p class="mb-1 text-[11px] text-[var(--text-muted)]">Write a Jinja expression. Reference the input as <code class="font-mono">{`{{ vars.input.records[0] }}`}</code>.</p>
        <div class="flex-1 overflow-hidden">
          <MonacoCode
            language="jinja"
            value={template}
            onInput={(v) => (template = v)}
            height="100%"
            onEditor={(ed, m) => { templateEditor = ed; templateMonaco = m; }}
          />
        </div>
      </section>

      <!-- ── Output ────────────────────────────────────────────────── -->
      <section class="flex flex-col overflow-hidden">
        <div class="mb-1 flex items-center justify-between">
          <span class="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">Output</span>
          <button
            type="button"
            class="rounded border border-[var(--border-soft)] bg-[var(--brand)] px-3 py-0.5 text-[11px] font-semibold text-[var(--brand-fg)] hover:opacity-90 disabled:opacity-60"
            onclick={run}
            disabled={busy || !!inputJsonError}
          >{busy ? 'Rendering…' : 'Render →'}</button>
        </div>
        <p class="mb-1 text-[11px] text-[var(--text-muted)]">Result of <code class="font-mono">render_jinja</code>.</p>
        <pre
          class="flex-1 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-3 font-mono text-[12px] {outputKind === 'error' ? 'text-red-400' : 'text-[var(--text-default)]'} whitespace-pre-wrap"
>{output || (busy ? '…' : 'Press Render to evaluate the template against the input JSON.')}</pre>
      </section>
    </div>
  </div>
</div>
