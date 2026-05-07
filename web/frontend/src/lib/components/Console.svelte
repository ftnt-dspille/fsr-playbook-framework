<script lang="ts">
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';

  let {
    text = '',
    lines = null,
    emptyTitle,
    emptyHint,
    emptyIcon,
    autoScroll = false,
    metaLeft,
    metaRight,
    /** Hide the built-in toolbar (line count + copy + scroll-to-bottom).
     *  Use when the caller already provides a section header so we don't
     *  end up with two stacked headers. */
    showToolbar = true
  }: {
    text?: string;
    lines?: string[] | null;
    emptyTitle: string;
    emptyHint?: string;
    emptyIcon?: Snippet;
    autoScroll?: boolean;
    metaLeft?: Snippet;
    metaRight?: Snippet;
    showToolbar?: boolean;
  } = $props();

  let scrollEl: HTMLDivElement | undefined;
  let copied = $state(false);

  const hasContent = $derived((lines?.length ?? 0) > 0 || (text || '').length > 0);
  const lineCount = $derived(
    lines ? lines.length : text ? text.split('\n').length : 0
  );

  // Render console output as HTML.
  //
  // Strict invariant: every span / anchor we emit is built directly
  // from a chunk of the raw input, escaped at emission time. We never
  // run a regex over already-rendered HTML — earlier versions did, and
  // a `\d+` highlighter merrily matched `300` inside class names like
  // `text-emerald-300`, which corrupted the whole frame.
  //
  // Pipeline:
  //   • per-line: if the line is JSON-shaped, parse it and render via
  //     the structured emitter (`jsonToHtml`) which walks the parsed
  //     value and emits colored spans directly.
  //   • otherwise: linkify URLs while escaping in a single pass.
  //
  // Both paths produce HTML that is never re-scanned.

  const URL_RE = /(https?:\/\/[^\s<>"'`]+)/g;
  const ANCHOR_CLS =
    'underline decoration-dotted underline-offset-2 text-[var(--brand)] hover:decoration-solid';

  function escapeHtml(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function linkifyEscape(raw: string): string {
    let html = '';
    let last = 0;
    for (const m of raw.matchAll(URL_RE)) {
      const idx = m.index ?? 0;
      html += escapeHtml(raw.slice(last, idx));
      let url = m[0];
      let trailing = '';
      while (url && /[.,;:)\]}>]$/.test(url)) {
        trailing = url.slice(-1) + trailing;
        url = url.slice(0, -1);
      }
      const safe = escapeHtml(url);
      html +=
        `<a href="${safe}" target="_blank" rel="noopener noreferrer" class="${ANCHOR_CLS}">${safe}</a>` +
        escapeHtml(trailing);
      last = idx + m[0].length;
    }
    html += escapeHtml(raw.slice(last));
    return html;
  }

  function jsonToHtml(value: unknown, indent: number): string {
    if (value === null) return '<span class="text-amber-300">null</span>';
    const t = typeof value;
    if (t === 'boolean') return `<span class="text-amber-300">${value}</span>`;
    if (t === 'number')
      return `<span class="text-violet-300">${escapeHtml(String(value))}</span>`;
    if (t === 'string') {
      const inner = linkifyEscape(value as string);
      return `<span class="text-emerald-300">&quot;${inner}&quot;</span>`;
    }
    const pad = '  '.repeat(indent);
    const childPad = '  '.repeat(indent + 1);
    if (Array.isArray(value)) {
      if (value.length === 0) return '[]';
      const items = value
        .map((v) => `${childPad}${jsonToHtml(v, indent + 1)}`)
        .join(',\n');
      return `[\n${items}\n${pad}]`;
    }
    if (t === 'object' && value) {
      const keys = Object.keys(value as Record<string, unknown>);
      if (keys.length === 0) return '{}';
      const entries = keys
        .map((k) => {
          const keyHtml = `<span class="text-sky-300">&quot;${escapeHtml(k)}&quot;</span>`;
          const valHtml = jsonToHtml((value as any)[k], indent + 1);
          return `${childPad}${keyHtml}: ${valHtml}`;
        })
        .join(',\n');
      return `{\n${entries}\n${pad}}`;
    }
    return escapeHtml(String(value));
  }

  // ── workflow-record pretty card ──────────────────────────────────
  // The fsrpb run-playbook command tail-ends with a JSON dump of the
  // FSR workflow record. Showing 30+ fields of raw JSON is noise; we
  // render a compact card with the fields a human actually wants:
  // name / status / timing / link. Other JSON objects fall through to
  // the generic structured emitter.

  function looksLikeWorkflowRecord(v: unknown): v is Record<string, unknown> {
    if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
    const o = v as Record<string, unknown>;
    if (o['@type'] === 'Workflow') return true;
    return (
      typeof o['@id'] === 'string' &&
      typeof o['name'] === 'string' &&
      typeof o['status'] === 'string'
    );
  }

  function statusClass(status: string): string {
    const s = status.toLowerCase();
    if (
      s === 'finished' || s === 'success' || s === 'completed' ||
      s === 'active' || s === 'done' || s === 'ok'
    ) return 'text-emerald-300';
    if (s === 'failed' || s === 'error' || s === 'cancelled' || s === 'canceled')
      return 'text-rose-300';
    if (s === 'awaiting' || s === 'pending' || s === 'queued' || s === 'running')
      return 'text-amber-300';
    return 'text-[var(--text-default)]';
  }

  function formatDuration(createdIso: unknown, modifiedIso: unknown): string | null {
    if (typeof createdIso !== 'string' || typeof modifiedIso !== 'string')
      return null;
    const a = Date.parse(createdIso);
    const b = Date.parse(modifiedIso);
    if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return null;
    const ms = b - a;
    if (ms < 1000) return `${ms}ms`;
    const s = Math.round(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rs = s % 60;
    return rs ? `${m}m ${rs}s` : `${m}m`;
  }

  function fmtIso(iso: unknown): string {
    if (typeof iso !== 'string') return '';
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return iso;
    const d = new Date(t);
    // Local time, short readable form: "May 7, 09:54:41".
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    });
  }

  function workflowRecordHtml(o: Record<string, unknown>, lead: string): string {
    const name = String(o['name'] ?? '');
    const status = String(o['status'] ?? '');
    const idIri = typeof o['@id'] === 'string' ? (o['@id'] as string) : '';
    const created = o['created'];
    const modified = o['modified'];
    const duration = formatDuration(created, modified);
    const node = o['node_name'];
    const debug = o['debug'];
    const tags = o['tags'];
    const errorVal = o['error'];

    const rows: Array<{ label: string; value: string }> = [];
    rows.push({
      label: 'Name',
      value: `<span class="text-emerald-300">${escapeHtml(name)}</span>`,
    });
    rows.push({
      label: 'Status',
      value: `<span class="${statusClass(status)}">${escapeHtml(status)}</span>`,
    });
    if (duration) {
      rows.push({
        label: 'Duration',
        value: `<span class="text-violet-300">${escapeHtml(duration)}</span>`,
      });
    }
    if (typeof modified === 'string') {
      rows.push({
        label: 'Finished',
        value: `<span class="text-[var(--text-muted)]">${escapeHtml(fmtIso(modified))}</span>`,
      });
    } else if (typeof created === 'string') {
      rows.push({
        label: 'Started',
        value: `<span class="text-[var(--text-muted)]">${escapeHtml(fmtIso(created))}</span>`,
      });
    }
    if (typeof node === 'string' && node) {
      rows.push({
        label: 'Node',
        value: `<span class="text-[var(--text-default)]">${escapeHtml(node)}</span>`,
      });
    }
    if (debug === true) {
      rows.push({
        label: 'Debug',
        value: `<span class="text-amber-300">on</span>`,
      });
    }
    if (typeof tags === 'string' && tags.trim()) {
      rows.push({
        label: 'Tags',
        value: `<span class="text-[var(--text-default)]">${escapeHtml(tags)}</span>`,
      });
    }
    if (errorVal && errorVal !== null && errorVal !== '') {
      const errStr = typeof errorVal === 'string' ? errorVal : JSON.stringify(errorVal);
      rows.push({
        label: 'Error',
        value: `<span class="text-rose-300">${escapeHtml(errStr)}</span>`,
      });
    }
    if (idIri) {
      // Build a clickable URL from the IRI by stitching it onto the
      // host the FSR web UI lives on. We don't know the host here, so
      // fall back to the relative IRI which still works as a link
      // when the user is browsing the FSR appliance directly.
      const safe = escapeHtml(idIri);
      rows.push({
        label: 'Link',
        value: `<a href="${safe}" target="_blank" rel="noopener noreferrer" class="${ANCHOR_CLS}">${safe}</a>`,
      });
    }

    const labelW =
      rows.reduce((w, r) => Math.max(w, r.label.length), 0) + 2;
    const indent = escapeHtml(lead);
    const rowLines = rows
      .map(
        (r) =>
          `${indent}  <span class="text-[var(--text-faint)]">${escapeHtml(r.label.padEnd(labelW))}</span>${r.value}`,
      )
      .join('\n');
    const title = `${indent}<span class="text-[var(--text-muted)]">─── Workflow run ───</span>`;
    return `${title}\n${rowLines}`;
  }

  function tryParseJsonLine(line: string): unknown | undefined {
    const t = line.trim();
    if (!t) return undefined;
    const head = t[0];
    if (head !== '{' && head !== '[') return undefined;
    if (t.length < 4) return undefined;
    try {
      return JSON.parse(t);
    } catch {
      return undefined;
    }
  }

  // Walk an input character offset to find a brace-balanced JSON
  // value (object or array). Strings (including escaped quotes) are
  // skipped so braces inside string values don't throw off the count.
  // Returns the index *after* the closing brace, or -1 if the value
  // doesn't terminate within the input.
  function findJsonEnd(s: string, start: number): number {
    const open = s[start];
    if (open !== '{' && open !== '[') return -1;
    const close = open === '{' ? '}' : ']';
    let depth = 0;
    let inStr = false;
    let escape = false;
    for (let i = start; i < s.length; i++) {
      const c = s[i];
      if (inStr) {
        if (escape) {
          escape = false;
        } else if (c === '\\') {
          escape = true;
        } else if (c === '"') {
          inStr = false;
        }
        continue;
      }
      if (c === '"') {
        inStr = true;
        continue;
      }
      if (c === open) depth++;
      else if (c === close) {
        depth--;
        if (depth === 0) return i + 1;
      }
    }
    return -1;
  }

  function renderConsoleHtml(raw: string): string {
    if (!raw) return '';
    // Walk the input. Outside JSON: emit per-line via linkifyEscape.
    // When we encounter a `{` or `[` at the start of trimmed line
    // content, scan forward for a balanced JSON value spanning one
    // or more lines, parse it, and route it through the structured
    // emitter (workflow card or generic jsonToHtml).
    const out: string[] = [];
    const lines = raw.split('\n');
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const trimmedStart = line.trimStart();
      const lead = line.slice(0, line.length - trimmedStart.length);
      if (trimmedStart.startsWith('{') || trimmedStart.startsWith('[')) {
        // Try to parse a JSON value starting here, possibly across
        // multiple lines. Build the candidate from `trimmedStart` of
        // line i and the full text of subsequent lines until brace
        // balance closes.
        // Use the original (un-stripped) bodies for index math, then
        // trim only at the front of the first line.
        const block = lines.slice(i).join('\n');
        // The opening brace is at offset = lead.length within `block`.
        const startInBlock = lead.length;
        const end = findJsonEnd(block, startInBlock);
        if (end > 0) {
          const candidate = block.slice(startInBlock, end);
          try {
            const parsed = JSON.parse(candidate);
            if (parsed && typeof parsed === 'object') {
              if (looksLikeWorkflowRecord(parsed)) {
                out.push(workflowRecordHtml(parsed, lead));
              } else {
                out.push(escapeHtml(lead) + jsonToHtml(parsed, 0));
              }
              // Advance past the consumed lines. Count newlines in
              // the slice we consumed; the +1 lands on the line after.
              const consumed = block.slice(0, end);
              i += (consumed.match(/\n/g)?.length ?? 0) + 1;
              continue;
            }
          } catch {
            // Fall through to plain rendering.
          }
        }
      }
      out.push(linkifyEscape(line));
      i++;
    }
    return out.join('\n');
  }

  const renderedHtml = $derived(
    renderConsoleHtml(lines ? lines.join('\n') : text || '')
  );

  $effect(() => {
    // Re-scroll to bottom when new content arrives in streaming mode.
    void (lines?.length ?? 0);
    void text;
    if (!autoScroll || !scrollEl) return;
    queueMicrotask(() => scrollEl?.scrollTo({ top: scrollEl.scrollHeight }));
  });

  async function copy() {
    const payload = lines ? lines.join('\n') : text;
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(payload);
      copied = true;
      setTimeout(() => (copied = false), 1200);
    } catch {
      /* ignore clipboard errors (sandbox / permissions) */
    }
  }

  function scrollToBottom() {
    scrollEl?.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
  }
</script>

<div class="flex h-full min-h-0 flex-col">
  {#if showToolbar}
    <div class="flex items-center gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-panel)] px-3 py-1.5 text-[11px] text-[var(--text-muted)]">
      {#if metaLeft}
        {@render metaLeft()}
      {/if}
      {#if hasContent}
        <span class="rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
          {lineCount} line{lineCount === 1 ? '' : 's'}
        </span>
      {/if}
      <div class="ml-auto flex items-center gap-1.5">
        {#if metaRight}
          {@render metaRight()}
        {/if}
        {#if hasContent}
          <button
            type="button"
            class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
            onclick={copy}
            aria-label="Copy console contents"
          >
            {copied ? '✓ copied' : 'copy'}
          </button>
          {#if autoScroll}
            <button
              type="button"
              class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
              onclick={scrollToBottom}
              aria-label="Scroll to latest"
            >
              ↓ latest
            </button>
          {/if}
        {/if}
      </div>
    </div>
  {/if}
  <div bind:this={scrollEl} class="min-h-0 flex-1 overflow-auto bg-[var(--bg-canvas)]">
    {#if hasContent}
      <pre class="m-0 px-3 py-2 font-mono text-[12.5px] leading-[1.55] text-[var(--text-default)] whitespace-pre-wrap">{@html renderedHtml}</pre>
    {:else}
      <div class="flex h-full items-center justify-center px-6 py-10">
        <div class="max-w-md text-center">
          <div class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--brand)]">
            {#if emptyIcon}
              {@render emptyIcon()}
            {:else}
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.6">
                <rect x="3.5" y="4.5" width="17" height="13" rx="2" />
                <path d="M7 10l3 2.5L7 15" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M12 15h5" stroke-linecap="round" />
              </svg>
            {/if}
          </div>
          <div class="text-sm font-medium text-[var(--text-default)]">{emptyTitle}</div>
          {#if emptyHint}
            <p class="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-[var(--text-muted)]">{emptyHint}</p>
          {/if}
        </div>
      </div>
    {/if}
  </div>
</div>
