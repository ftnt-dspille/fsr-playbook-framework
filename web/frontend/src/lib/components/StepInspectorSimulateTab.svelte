<script lang="ts">
  /**
   * Samples tab — unified "what would this step return at runtime?"
   * editor. Two persistence shapes, depending on step type:
   *
   *  manual_input → `# fsrpb:samples` sidecar comment in the YAML.
   *      Stores `samples.<playbook>.<step>.input.<field>`. Resolves
   *      at `vars.steps.<step>.input.<field>` in downstream Jinja.
   *
   *  connector / record_crud / fetch / ingest / utility → `arguments.
   *      mock_result` on the step itself. FSR honors mock_result at
   *      runtime when mock mode is on; the debug runner honors it
   *      offline. Authoring it means downstream consumers see real
   *      shape without a live FSR call.
   *
   * Step types that compute their output deterministically
   * (set_variable, decision, start/stop/end) don't expose either
   * shape — for those, this tab shows a short note instead of a form.
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import { writeSamples, getVisualFromBuffer } from '../api';
  import { playbookStore } from '../playbookStore.svelte';
  import { visualStore } from '../visualEditStore.svelte';

  type Props = { node: VisualNode; playbook: VisualPlaybook; playbookIdx: number };
  let { node, playbook, playbookIdx }: Props = $props();

  // Step types whose output is deterministic from their args; sampling
  // makes no sense. Everything else can either take sidecar samples
  // (manual_input) or a mock_result (connector/record/etc).
  const NO_SAMPLE_TYPES = new Set([
    'set_variable', 'decision', 'start', 'stop', 'end', 'terminate',
    'start_on_create', 'start_on_update'
  ]);

  let isManualInput = $derived(node.type === 'manual_input');
  let isMockable = $derived(!isManualInput && !NO_SAMPLE_TYPES.has(node.type));

  // ─── manual_input prompt wireframe ───────────────────────────────────
  // Mocks up what an FSR user will see when this step fires. Title +
  // description + inputs as labeled placeholders + option buttons.
  // Pure presentation — no Jinja round-trip, no interactive form.

  type Option = { display: string; primary?: boolean };

  let promptTitle = $derived.by<string>(() => {
    if (!isManualInput) return '';
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    const inputBlock = (a.input as Record<string, unknown> | undefined)?.schema as
      | Record<string, unknown> | undefined;
    return String(a.title ?? inputBlock?.title ?? '');
  });

  let promptDescription = $derived.by<string>(() => {
    if (!isManualInput) return '';
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    const inputBlock = (a.input as Record<string, unknown> | undefined)?.schema as
      | Record<string, unknown> | undefined;
    return String(a.description ?? inputBlock?.description ?? '');
  });

  let promptOptions = $derived.by<Option[]>(() => {
    if (!isManualInput) return [];
    // Source 1 (most common): node.arguments.options — the visual store
    //   normalises both friendly `options:` and wire
    //   `arguments.response_mapping.options` onto this single key (see
    //   StepInspectorBranchesTab.svelte).
    // Source 2 (fallback): wire-form arguments.response_mapping.options
    //   for nodes loaded directly from raw wire shape without
    //   normalisation.
    // Source 3 (last resort): outgoing edges with branch_kind:'branch'
    //   — guarantees the preview matches the canvas even when the
    //   options array is somehow missing.
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    const direct = a.options;
    const respOpts = (a.response_mapping as { options?: unknown[] } | undefined)?.options;
    const fromArgs: Option[] = [];
    for (const raw of [direct, respOpts]) {
      if (!Array.isArray(raw)) continue;
      for (const o of raw) {
        if (!o || typeof o !== 'object') continue;
        const rec = o as Record<string, unknown>;
        const display = String(rec.display ?? rec.option ?? '');
        if (display) fromArgs.push({ display, primary: Boolean(rec.primary) });
      }
      if (fromArgs.length) break;
    }
    if (fromArgs.length) return fromArgs;
    // Edge fallback: every outgoing branch edge becomes one button.
    return playbook.edges
      .filter((e) => e.source === node.id && e.branch_kind === 'branch')
      .map((e) => ({ display: String(e.label ?? ''), primary: false }))
      .filter((o) => o.display);
  });

  let isApproval = $derived.by(() => {
    if (!isManualInput) return false;
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    return Boolean(a.is_approval);
  });

  // ─── manual_input sample form (sidecar samples) ──────────────────────

  type Input = {
    name: string;
    label?: string;
    kind?: string;
    required?: boolean;
  };

  let inputs = $derived.by<Input[]>(() => {
    if (!isManualInput) return [];
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    const list = (a.inputs ?? a.inputVariables) as unknown[] | undefined;
    if (!Array.isArray(list)) return [];
    return list
      .filter((e): e is Record<string, unknown> => !!e && typeof e === 'object')
      .map((e) => ({
        name: String(e.name ?? ''),
        label: e.label ? String(e.label) : undefined,
        kind: e.kind ? String(e.kind) : undefined,
        required: Boolean(e.required)
      }))
      .filter((e) => e.name);
  });

  let allSamples = $state<Record<string, Record<string, unknown>>>({});
  let initialLoaded = $state(false);

  $effect(() => {
    const yaml = playbookStore.currentYaml;
    if (!yaml) return;
    getVisualFromBuffer(yaml).then((g) => {
      allSamples = g.samples ?? {};
      initialLoaded = true;
    }).catch(() => {
      initialLoaded = true;
    });
  });

  let pbSamples = $derived(allSamples[playbook.name] ?? {});
  let stepSample = $derived(
    (pbSamples[node.id] as { input?: Record<string, unknown> } | undefined)?.input ?? {}
  );

  let values = $state<Record<string, string>>({});
  let dirty = $state(false);
  let saveStatus = $state<'' | 'saving' | 'saved' | 'error'>('');
  let saveError = $state<string | null>(null);

  $effect(() => {
    if (!initialLoaded || !isManualInput) return;
    const next: Record<string, string> = {};
    for (const inp of inputs) {
      const v = stepSample[inp.name];
      next[inp.name] = v === undefined || v === null ? '' : String(v);
    }
    values = next;
    dirty = false;
  });

  function onFieldInput(name: string, e: Event) {
    const v = (e.currentTarget as HTMLInputElement).value;
    values[name] = v;
    dirty = true;
    saveStatus = '';
  }

  function coerce(raw: string, kind?: string): unknown {
    if (raw === '') return null;
    const k = (kind ?? '').toLowerCase();
    if (k.includes('int') || k.includes('number')) {
      const n = Number(raw);
      return Number.isFinite(n) ? n : raw;
    }
    if (k.includes('bool') || k.includes('checkbox')) {
      return raw === 'true' || raw === '1' || raw === 'yes';
    }
    return raw;
  }

  async function saveSidecar() {
    saveStatus = 'saving';
    saveError = null;
    const inputPayload: Record<string, unknown> = {};
    for (const inp of inputs) {
      const raw = values[inp.name] ?? '';
      if (raw === '') continue;
      inputPayload[inp.name] = coerce(raw, inp.kind);
    }

    const nextPb = { ...pbSamples };
    if (Object.keys(inputPayload).length === 0) {
      delete nextPb[node.id];
    } else {
      nextPb[node.id] = { input: inputPayload };
    }
    const nextAll: Record<string, Record<string, unknown>> = { ...allSamples };
    if (Object.keys(nextPb).length === 0) {
      delete nextAll[playbook.name];
    } else {
      nextAll[playbook.name] = nextPb;
    }

    try {
      const r = await writeSamples(playbookStore.currentYaml, nextAll);
      if (!r.ok) throw new Error('write failed');
      playbookStore.replaceYaml(r.yaml, 'samples-tab');
      if (visualStore.state.graph) {
        visualStore.state.graph = { ...visualStore.state.graph, samples: nextAll };
      }
      allSamples = nextAll;
      dirty = false;
      saveStatus = 'saved';
    } catch (e: any) {
      saveStatus = 'error';
      saveError = String(e?.message ?? e);
    }
  }

  function clearSidecar() {
    for (const inp of inputs) values[inp.name] = '';
    dirty = true;
    saveStatus = '';
  }

  // ─── mock_result editor (everything mockable) ────────────────────────

  // Existing mock_result on the step, formatted for the textarea.
  let existingMock = $derived(
    (node.arguments as Record<string, unknown> | undefined)?.mock_result
  );
  let hasMock = $derived(existingMock !== undefined && existingMock !== null);

  let mockText = $state<string>('');
  let mockDirty = $state(false);
  let mockParseError = $state<string | null>(null);
  let mockSaveStatus = $state<'' | 'saving' | 'saved' | 'error'>('');

  // Hydrate the textarea from current mock_result whenever it changes
  // (e.g. saveAsMock fired from the Verify tab).
  $effect(() => {
    if (!isMockable) return;
    mockText = hasMock ? JSON.stringify(existingMock, null, 2) : '';
    mockDirty = false;
    mockParseError = null;
  });

  function onMockInput(e: Event) {
    mockText = (e.currentTarget as HTMLTextAreaElement).value;
    mockDirty = true;
    mockSaveStatus = '';
    // Live parse-check so the Save button can disable on bad JSON.
    if (mockText.trim() === '') {
      mockParseError = null;
      return;
    }
    try {
      JSON.parse(mockText);
      mockParseError = null;
    } catch (err: any) {
      mockParseError = err?.message ?? 'invalid JSON';
    }
  }

  function saveMock() {
    mockSaveStatus = 'saving';
    try {
      const nextArgs = { ...(node.arguments ?? {}) } as Record<string, unknown>;
      if (mockText.trim() === '') {
        delete nextArgs.mock_result;
      } else {
        nextArgs.mock_result = JSON.parse(mockText);
      }
      visualStore.setArgs(playbookIdx, node.id, nextArgs);
      mockSaveStatus = 'saved';
      mockDirty = false;
    } catch (e: any) {
      mockSaveStatus = 'error';
      mockParseError = e?.message ?? 'save failed';
    }
  }

  function clearMock() {
    const nextArgs = { ...(node.arguments ?? {}) } as Record<string, unknown>;
    delete nextArgs.mock_result;
    visualStore.setArgs(playbookIdx, node.id, nextArgs);
    mockText = '';
    mockDirty = false;
    mockSaveStatus = '';
  }

  // Skeleton placeholder for empty mocks — gives the user a starting
  // point that matches FSR's connector-op output envelope.
  let mockPlaceholder = $derived(
    node.family === 'connector_op'
      ? '{\n  "status": "Success",\n  "result": { … }\n}'
      : node.family === 'record_crud'
        ? '{\n  "@id": "/api/3/alerts/<uuid>",\n  "uuid": "…",\n  "name": "Sample"\n}'
        : '{\n  "key": "value"\n}'
  );
</script>

<section class="space-y-4">
  {#if !isManualInput && !isMockable}
    <p class="text-[11px] italic text-[var(--text-faint)]">
      <code class="font-mono">{node.type}</code> steps compute their output
      deterministically from their args — no sample data needed.
    </p>
  {/if}

  {#if isManualInput}
    <!-- Prompt wireframe — what a user sees in the FSR UI when this
         step pauses execution. Pure visual mockup; templated strings
         stay as {{ … }} so the author can spot their own placeholders. -->
    <section class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-3">
      <div class="mb-2 flex items-center justify-between">
        <h3 class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Prompt preview
        </h3>
        <span class="text-[9px] text-[var(--text-faint)]">what the user sees</span>
      </div>

      <div class="rounded border border-[var(--border)] bg-[var(--bg-elev)] p-3 shadow-sm">
        {#if isApproval}
          <div class="mb-2 text-[9px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
            Approval required
          </div>
        {/if}
        {#if promptTitle}
          <div class="text-sm font-semibold text-[var(--text-default)]">{promptTitle}</div>
        {:else}
          <div class="text-sm italic text-[var(--text-faint)]">(no title)</div>
        {/if}

        {#if promptDescription}
          <!-- FSR allows HTML in description. We render as plain text
               here (no innerHTML — avoids XSS from author markup) but
               preserve line breaks so multi-line descriptions read right. -->
          <p class="mt-1 whitespace-pre-wrap text-xs text-[var(--text-muted)]">{promptDescription}</p>
        {/if}

        {#if inputs.length > 0}
          <div class="mt-3 space-y-2">
            {#each inputs as inp (inp.name)}
              <div>
                <div class="text-[10px] font-medium text-[var(--text-muted)]">
                  {inp.label ?? inp.name}
                  {#if inp.required}<span class="ml-1 text-rose-500">*</span>{/if}
                </div>
                <div class="mt-0.5 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs italic text-[var(--text-faint)]">
                  {inp.kind === 'checkbox' ? '☐' : `enter ${inp.label ?? inp.name}…`}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        {#if promptOptions.length > 0}
          <div class="mt-3 flex flex-wrap gap-2">
            {#each promptOptions as opt}
              <span class={'rounded px-3 py-1 text-xs font-medium ' +
                (opt.primary
                  ? 'bg-[var(--brand)] text-white'
                  : 'border border-[var(--border-soft)] text-[var(--text-default)]')}>
                {opt.display}
              </span>
            {/each}
          </div>
        {:else}
          <p class="mt-3 text-[10px] italic text-[var(--text-faint)]">(no buttons configured — add an option to <code class="font-mono">arguments.response_mapping.options</code>)</p>
        {/if}
      </div>

      <p class="mt-2 text-[10px] text-[var(--text-faint)]">
        Templated <code class="font-mono">{`{{ … }}`}</code> in title/description resolves against runtime
        data — preview shows the author's raw text.
      </p>
    </section>

    <section>
      <div>
        <h3 class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Sample answers
        </h3>
        <p class="mt-1 text-[11px] text-[var(--text-faint)]">
          What a user would enter at runtime. Saved to a
          <code class="font-mono">fsrpb:samples</code> comment block;
          downstream steps resolve <code class="font-mono">vars.steps.{node.id}.input.&lt;field&gt;</code>
          against these without a live FSR run. They never reach the FSR push payload.
        </p>
      </div>

      {#if inputs.length === 0}
        <p class="mt-3 text-[11px] italic text-[var(--text-faint)]">
          This step has no declared inputs. Add some under
          <code class="font-mono">arguments.inputs</code> first.
        </p>
      {:else}
        <form
          onsubmit={(e) => { e.preventDefault(); void saveSidecar(); }}
          class="mt-3 space-y-2"
        >
          {#each inputs as inp (inp.name)}
            <label class="block">
              <span class="block text-[10px] font-medium text-[var(--text-muted)]">
                {inp.label ?? inp.name}
                {#if inp.kind}<span class="ml-1 text-[var(--text-faint)]">({inp.kind})</span>{/if}
                {#if inp.required}<span class="ml-1 text-rose-500">*</span>{/if}
              </span>
              <input
                type={inp.kind?.toLowerCase().includes('int') || inp.kind?.toLowerCase().includes('number') ? 'number' : 'text'}
                value={values[inp.name] ?? ''}
                oninput={(e) => onFieldInput(inp.name, e)}
                placeholder={inp.kind === 'ipv4' ? 'e.g. 1.2.3.4' : ''}
                class="mt-0.5 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-xs"
              />
            </label>
          {/each}

          <div class="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={!dirty || saveStatus === 'saving'}
              class="rounded border border-[var(--border-soft)] bg-[var(--brand)] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
            >{saveStatus === 'saving' ? 'Saving…' : 'Save sample'}</button>
            <button
              type="button"
              onclick={clearSidecar}
              class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)]"
            >Clear</button>
            {#if saveStatus === 'saved'}
              <span class="text-[10px] text-emerald-600 dark:text-emerald-400">Saved</span>
            {:else if saveStatus === 'error'}
              <span class="text-[10px] text-rose-600 dark:text-rose-400">{saveError ?? 'Error'}</span>
            {/if}
          </div>
        </form>
      {/if}

      {#if Object.keys(stepSample).length > 0}
        <details class="mt-2 text-[11px] text-[var(--text-muted)]">
          <summary class="cursor-pointer">Current sample (resolves at <code class="font-mono">vars.steps.{node.id}.input</code>)</summary>
          <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(stepSample, null, 2)}</pre>
        </details>
      {/if}
    </section>
  {/if}

  {#if isMockable}
    <section>
      <div>
        <h3 class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Mock output
          {#if hasMock}
            <span class="ml-1 rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] text-emerald-700 dark:text-emerald-400">set</span>
          {/if}
        </h3>
        <p class="mt-1 text-[11px] text-[var(--text-faint)]">
          Pretend this step returned the JSON below — instead of running it live.
          Saved to <code class="font-mono">arguments.mock_result</code>; honored by
          the debug runner and by FSR in mock mode. Downstream
          <code class="font-mono">vars.steps.{node.id}.&lt;key&gt;</code> resolves
          against this shape.
        </p>
      </div>

      <textarea
        aria-label="Mock result JSON"
        rows="8"
        class={'mt-2 block w-full resize-y rounded border bg-[var(--bg-canvas)] px-2 py-1 font-mono text-xs ' +
          (mockParseError ? 'border-rose-500' : 'border-[var(--border-soft)]')}
        placeholder={mockPlaceholder}
        value={mockText}
        oninput={onMockInput}
      ></textarea>
      {#if mockParseError}
        <p class="mt-1 text-[10px] text-rose-600 dark:text-rose-400">JSON: {mockParseError}</p>
      {/if}
      <div class="mt-1 flex items-center gap-2">
        <button
          type="button"
          onclick={saveMock}
          disabled={!mockDirty || !!mockParseError || mockSaveStatus === 'saving'}
          class="rounded border border-[var(--border-soft)] bg-[var(--brand)] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        >{mockSaveStatus === 'saving' ? 'Saving…' : (hasMock ? 'Update mock' : 'Save mock')}</button>
        {#if hasMock}
          <button
            type="button"
            onclick={clearMock}
            class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)]"
          >Remove mock</button>
        {/if}
        {#if mockSaveStatus === 'saved'}
          <span class="text-[10px] text-emerald-600 dark:text-emerald-400">Saved</span>
        {/if}
      </div>
      <p class="mt-2 text-[10px] text-[var(--text-faint)]">
        Tip: clicking <strong>Run this step</strong> in the Verify tab on a connector op,
        then <strong>Save as mock</strong>, populates this field for you.
      </p>
    </section>
  {/if}
</section>
