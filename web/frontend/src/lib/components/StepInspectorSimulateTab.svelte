<script lang="ts">
  /**
   * Simulate tab for `manual_input` steps.
   *
   * Renders the step's declared inputs as a real form, lets the author
   * fill in synthetic answers, and persists them to the YAML's
   * `# fsrpb:samples` sidecar block. Downstream steps' Verify/Render
   * then resolves Jinja like `{{ vars.steps.Get_IP.input.ip_address }}`
   * against these values without a live FSR run.
   *
   * Values live in YAML comments — they round-trip through save but
   * never reach the FSR push payload (parser drops comments).
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import { writeSamples, getVisualFromBuffer } from '../api';
  import { playbookStore } from '../playbookStore.svelte';
  import { visualStore } from '../visualEditStore.svelte';

  type Props = { node: VisualNode; playbook: VisualPlaybook };
  let { node, playbook }: Props = $props();

  type Input = {
    name: string;
    label?: string;
    kind?: string;
    required?: boolean;
  };

  // The IR stores inputs under `arguments.inputs` (friendly) or
  // `arguments.inputVariables` (canonical). Accept both so this works
  // regardless of which form the YAML uses.
  let inputs = $derived.by<Input[]>(() => {
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

  // Current sample for this step, if any. Stored under
  // `samples[playbook.name][node.id].input.<name>`.
  let allSamples = $state<Record<string, Record<string, unknown>>>({});
  let initialLoaded = $state(false);

  $effect(() => {
    // Reload samples whenever the active YAML changes (e.g. after a
    // save) so this tab reflects the persisted state. Cheap: same call
    // the visual editor already makes on edit.
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

  // Local edit buffer — string-typed so the form is fully controlled.
  // Coerced to the right scalar at save time based on `kind`.
  let values = $state<Record<string, string>>({});
  let dirty = $state(false);
  let saveStatus = $state<'' | 'saving' | 'saved' | 'error'>('');
  let saveError = $state<string | null>(null);

  // Hydrate the edit buffer once samples land. Re-runs only when
  // the underlying sample shape actually changes (e.g. user navigated
  // to a different node).
  $effect(() => {
    if (!initialLoaded) return;
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

  async function save() {
    saveStatus = 'saving';
    saveError = null;
    const inputPayload: Record<string, unknown> = {};
    for (const inp of inputs) {
      const raw = values[inp.name] ?? '';
      if (raw === '') continue;  // Skip blanks so the sidecar stays minimal.
      inputPayload[inp.name] = coerce(raw, inp.kind);
    }

    // Replace just this step's entry under this playbook; leave other
    // playbooks / steps untouched.
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
      // Splice the new YAML back in so other surfaces (Monaco, the
      // backend autosave loop) see the samples block immediately.
      playbookStore.replaceYaml(r.yaml, 'simulate-tab');
      // Critical: mirror the new samples onto the in-memory graph too.
      // The visual canvas auto-renders YAML from `state.graph` via
      // `/api/visual/write` on the next dirty flush; without this
      // update the round-trip would emit the OLD (or empty) samples
      // block and clobber what we just wrote.
      if (visualStore.state.graph) {
        visualStore.state.graph = {
          ...visualStore.state.graph,
          samples: nextAll
        };
      }
      allSamples = nextAll;
      dirty = false;
      saveStatus = 'saved';
    } catch (e: any) {
      saveStatus = 'error';
      saveError = String(e?.message ?? e);
    }
  }

  function clear() {
    for (const inp of inputs) values[inp.name] = '';
    dirty = true;
    saveStatus = '';
  }
</script>

<section class="space-y-3">
  <div>
    <h3 class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Sample answers</h3>
    <p class="mt-1 text-[11px] text-[var(--text-faint)]">
      Fill in what a user would enter at runtime. Values are saved to a
      <code class="font-mono">fsrpb:samples</code> comment block in the YAML — they let
      downstream steps' Verify tab render their Jinja against real-looking
      data, but they never reach the FSR push payload.
    </p>
  </div>

  {#if inputs.length === 0}
    <p class="text-[11px] italic text-[var(--text-faint)]">
      This step has no declared inputs. Add some under
      <code class="font-mono">arguments.inputs</code> first.
    </p>
  {:else}
    <form
      onsubmit={(e) => { e.preventDefault(); void save(); }}
      class="space-y-2"
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
          onclick={clear}
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
    <details class="text-[11px] text-[var(--text-muted)]">
      <summary class="cursor-pointer">Current sample (resolves at <code class="font-mono">vars.steps.{node.id}.input</code>)</summary>
      <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(stepSample, null, 2)}</pre>
    </details>
  {/if}
</section>
