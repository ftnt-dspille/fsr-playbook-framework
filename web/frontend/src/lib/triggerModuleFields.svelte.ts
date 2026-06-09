/**
 * Module-aware field catalog for `vars.input.records[0].*` completions
 * and hovers. The trigger module is parsed out of the YAML (the
 * `start_on_create` / `start_on_update` / `start` step's
 * `arguments.module: <name>`); fields come from
 * `/api/ref/modules/<m>/fields`.
 *
 * Public surface:
 *   - extractTriggerModule(yaml) — small line-based YAML scanner that
 *     finds the first trigger step's module name, or null.
 *   - triggerModuleFieldsStore.fieldsFor(module) — async, cached.
 *
 * The store is intentionally async-aware: the Monaco completion
 * provider's `provideCompletionItems` is async, so an awaited fetch
 * on the first keystroke is fine. Subsequent keystrokes hit the
 * in-memory cache.
 */

const TRIGGER_TYPES = new Set(['start', 'start_on_create', 'start_on_update']);

/** Indent (in spaces) of the first non-blank char of `line`. -1 if blank. */
function indentOf(line: string): number {
  const m = line.match(/^(\s*)\S/);
  return m ? m[1].length : -1;
}

/** Strip `?$limit=…` / other querystring tails — the bare module name
 *  is what /api/ref/modules/<m>/fields expects. */
function bareModule(s: string): string {
  const q = s.indexOf('?');
  return (q < 0 ? s : s.slice(0, q)).trim().replace(/^["']|["']$/g, '');
}

/** Scan the YAML buffer for every distinct `globalVars.<name>` reference
 *  and return the sorted unique list. No backend dependency — purely
 *  derives autocomplete from names the user has already typed.
 *  Stop-gap until /api/ref/global-vars (trained store) exists. */
export function extractGlobalVarNames(yaml: string): string[] {
  if (!yaml) return [];
  const names = new Set<string>();
  for (const m of yaml.matchAll(/globalVars\.([A-Za-z_][\w]*)/g)) {
    names.add(m[1]);
  }
  return [...names].sort();
}

/** Find the first trigger step in the YAML and return its
 *  `arguments.module:` value, or null. Single-pass, no YAML parse —
 *  we just scan for `type: start*` followed by an `arguments:` block
 *  containing `module:` at the same step's indent + 2. */
export function extractTriggerModule(yaml: string): string | null {
  if (!yaml) return null;
  const lines = yaml.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    const ind = indentOf(ln);
    if (ind === -1) continue;
    const stripped = ln.slice(ind);
    // Allow both `type: x` and `- type: x` (step opener on same line).
    const m = stripped.match(/^(?:-\s+)?type:\s*([A-Za-z_][\w]*)\s*$/);
    if (!m || !TRIGGER_TYPES.has(m[1])) continue;
    // Walk downward looking for `module:`. Step-body keys (type,
    // arguments, next, …) sit at the SAME indent as the matched
    // `type:` line; nested keys like arguments.module are deeper.
    // Stop conditions:
    //   - indent < ind  → left the step entirely.
    //   - indent == ind AND line starts with `- ` → next sibling step.
    for (let j = i + 1; j < lines.length; j++) {
      const t = lines[j];
      const ti = indentOf(t);
      if (ti === -1) continue;
      if (ti < ind) break;
      const stripped2 = t.slice(ti);
      if (ti === ind && stripped2.startsWith('- ')) break;
      const mm = stripped2.match(/^module:\s*(.+)$/);
      if (mm) return bareModule(mm[1]) || null;
    }
  }
  return null;
}

/** Field-name cache keyed by module. Promise-valued so concurrent
 *  callers dedupe to one fetch. */
const fieldsCache = new Map<string, Promise<string[]>>();

async function fetchFields(module: string): Promise<string[]> {
  try {
    const r = await fetch(`/api/ref/modules/${encodeURIComponent(module)}/fields`);
    if (!r.ok) return [];
    const data = await r.json();
    const fields: any[] = data.fields ?? [];
    // The API returns objects like { name, type, ... } or bare strings,
    // depending on shape. Accept both; prefer the `name` key when present.
    return fields
      .map((f) => (typeof f === 'string' ? f : f?.name))
      .filter((n): n is string => typeof n === 'string' && n.length > 0);
  } catch {
    return [];
  }
}

/** Live sample records from FSR — used by the picker to show real
 *  field values alongside the path so authors can verify that
 *  `.severity` (or whatever they're about to reference) actually
 *  exists on the trigger's records. Keyed by module name. */
const sampleCache = new Map<string, Promise<Array<Record<string, unknown>>>>();

/** The record the user picked as "what `vars.input.records[0]` looks
 *  like" for the current session. Used by the picker / verify so the
 *  preview values match a real example the user OK'd. Reactive state
 *  so consumers re-render on change.
 *
 *  Persisted to localStorage keyed by module so the pick survives
 *  page reloads — without this, every refresh wipes the sample and
 *  inline `→ RENDERS TO` previews go blank until the user re-picks.
 *  The "last picked module" is also stored so the active sample is
 *  restored even if the user opens the editor without first hitting
 *  the trigger step's picker. */
const SAMPLE_KEY = (mod: string) => `fsrpb:sample-record:${mod}`;
const SAMPLE_LAST_KEY = 'fsrpb:sample-record:_last-module';

function loadInitialSample(): { picked: Record<string, unknown> | null; module: string } {
  if (typeof localStorage === 'undefined') return { picked: null, module: '' };
  try {
    const mod = localStorage.getItem(SAMPLE_LAST_KEY) || '';
    if (!mod) return { picked: null, module: '' };
    const raw = localStorage.getItem(SAMPLE_KEY(mod));
    if (!raw) return { picked: null, module: mod };
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { picked: parsed as Record<string, unknown>, module: mod };
    }
  } catch {
    // corrupt entry — fall through to empty state
  }
  return { picked: null, module: '' };
}

const sampleState: { picked: Record<string, unknown> | null; module: string } =
  $state(loadInitialSample());

export const sampleRecordsStore = {
  async fetch(module: string, limit = 10): Promise<Array<Record<string, unknown>>> {
    if (!module) return [];
    const cacheKey = `${module}::${limit}`;
    let p = sampleCache.get(cacheKey);
    if (!p) {
      p = (async () => {
        try {
          const r = await fetch(
            `/api/ref/sample-record/${encodeURIComponent(module)}?limit=${limit}`
          );
          if (!r.ok) return [];
          const data = await r.json();
          const recs = (data?.records ?? []) as Array<Record<string, unknown>>;
          return Array.isArray(recs) ? recs : [];
        } catch {
          return [];
        }
      })();
      sampleCache.set(cacheKey, p);
    }
    return p;
  },
  /** What the user picked as the canonical sample for this session. */
  get picked(): Record<string, unknown> | null {
    return sampleState.picked;
  },
  get pickedModule(): string {
    return sampleState.module;
  },
  pick(module: string, rec: Record<string, unknown> | null): void {
    sampleState.module = module;
    sampleState.picked = rec;
    // Invalidate the render context so the next preview rebuilds
    // against the new pick instead of reusing the cached one keyed
    // by YAML text (which hasn't changed). Lazy-import to avoid a
    // module-graph cycle (jinjaRender imports this store).
    import('./jinjaRender.svelte').then((m) => m.invalidateJinjaContext()).catch(() => {});
    if (typeof localStorage === 'undefined') return;
    try {
      if (rec) {
        localStorage.setItem(SAMPLE_KEY(module), JSON.stringify(rec));
        localStorage.setItem(SAMPLE_LAST_KEY, module);
      } else {
        localStorage.removeItem(SAMPLE_KEY(module));
        // Only clear _last-module if the unpinned module was the active one.
        if (localStorage.getItem(SAMPLE_LAST_KEY) === module) {
          localStorage.removeItem(SAMPLE_LAST_KEY);
        }
      }
    } catch {
      // quota / disabled storage — best-effort
    }
  },
  _reset(): void {
    sampleCache.clear();
    sampleState.picked = null;
    sampleState.module = '';
    if (typeof localStorage === 'undefined') return;
    try {
      // Wipe every fsrpb:sample-record:* key — covers test cleanup.
      const toDelete: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('fsrpb:sample-record:')) toDelete.push(k);
      }
      for (const k of toDelete) localStorage.removeItem(k);
    } catch {
      // best-effort
    }
  }
};


/** FSR dynamic-variables ("globalVars") catalog — fetched once, cached.
 *  Backend route /api/ref/global-vars wraps FSR's
 *  /api/wf/api/dynamic-variable/?offset=0&limit=2147483647. */
let globalVarsPromise: Promise<{ name: string; value: string | null }[]> | null = null;

export const globalVarsStore = {
  async list(): Promise<{ name: string; value: string | null }[]> {
    if (!globalVarsPromise) {
      globalVarsPromise = (async () => {
        try {
          const r = await fetch('/api/ref/global-vars');
          if (!r.ok) return [];
          const data = (await r.json()) as Array<{ name?: string; value?: string | null }>;
          return data
            .filter((d) => typeof d?.name === 'string' && d.name.length > 0)
            .map((d) => ({ name: d.name!, value: d.value ?? null }));
        } catch {
          return [];
        }
      })();
    }
    return globalVarsPromise;
  },
  _reset(): void {
    globalVarsPromise = null;
  }
};

export const triggerModuleFieldsStore = {
  /** Fields for `<module>`, fetched-and-cached. Returns [] on error
   *  / unknown module so callers can fall back to DEFAULT_RECORD_FIELDS. */
  async fieldsFor(module: string): Promise<string[]> {
    if (!module) return [];
    let p = fieldsCache.get(module);
    if (!p) {
      p = fetchFields(module);
      fieldsCache.set(module, p);
    }
    return p;
  },
  /** Test-only: clear the in-memory cache. */
  _reset(): void {
    fieldsCache.clear();
  }
};
