/**
 * Monaco hover provider — when the cursor is on `arguments:` (or any
 * key directly under it), look up the enclosing step's `type:` and
 * surface the curated step-args help as a markdown popup.
 *
 * Backend: GET /api/ref/step-args/<type>
 *
 * Why a custom provider (not yaml-language-server / JSON Schema)?
 * Friendly-form keys (`title`, `inputs`, `module`, `branches`) only
 * exist in our resolver, not in any schema. The agent needs *authoring*
 * docs keyed by friendly type, which is what this dict gives them.
 */

type HelpResponse = {
  type: string;
  markdown: string | null;
  spec: { summary: string };
};

const helpCache = new Map<string, Promise<HelpResponse | null>>();

async function fetchHelp(stepType: string): Promise<HelpResponse | null> {
  const cached = helpCache.get(stepType);
  if (cached) return cached;
  const p = (async () => {
    try {
      const r = await fetch(`/api/ref/step-args/${encodeURIComponent(stepType)}`);
      if (!r.ok) return null;
      return (await r.json()) as HelpResponse;
    } catch {
      return null;
    }
  })();
  helpCache.set(stepType, p);
  return p;
}

/** Indent (in spaces) of the first non-blank char on a line. -1 if blank. */
function indentOf(line: string): number {
  const m = line.match(/^(\s*)\S/);
  return m ? m[1].length : -1;
}

/**
 * Walk upward from `lineNumber` to find the nearest enclosing
 * `type: <name>` whose key indent is strictly less than `argsIndent`
 * (so it belongs to the same step that owns `arguments:`).
 *
 * YAML in this project uses 2-space indents and step blocks open with
 * `- id:`. The step's `type:` and `arguments:` sit at the same indent
 * level. We bound the walk by the first `- ` line we hit at <=
 * argsIndent (that's the step's own opener).
 */
function findEnclosingType(
  model: any,
  startLine: number,
  argsIndent: number
): string | null {
  for (let n = startLine; n >= 1; n--) {
    const text: string = model.getLineContent(n);
    const ind = indentOf(text);
    if (ind === -1) continue;
    const stripped = text.slice(ind);
    // Stop walking once we cross out of this step (a sibling step
    // opener `- id:` or a less-indented block).
    if (n !== startLine && stripped.startsWith('- ') && ind <= argsIndent) {
      // The step opener line itself may carry `type:` in flow form,
      // but we always emit it on its own line. Keep walking inside
      // the step block; the `- ` line is the lower bound.
      // Continue the walk one more iteration for sibling-step keys
      // that share its indent.
    }
    const m = stripped.match(/^type:\s*([A-Za-z_][\w-]*)/);
    if (m && (ind === argsIndent || ind === argsIndent)) {
      return m[1];
    }
    // Hard stop when we reach a previous step opener at or below
    // argsIndent — we've left this step's body.
    if (n !== startLine && stripped.startsWith('- ') && ind < argsIndent) {
      return null;
    }
  }
  return null;
}

export function registerYamlHover(monaco: any): { dispose: () => void } {
  return monaco.languages.registerHoverProvider('yaml', {
    async provideHover(model: any, position: any) {
      const lineNo = position.lineNumber;
      const line: string = model.getLineContent(lineNo);
      const ind = indentOf(line);
      if (ind === -1) return null;
      const stripped = line.slice(ind);

      // Fire on `arguments:` directly, OR any key beneath it. Walk up
      // until we find the `arguments:` line and capture its indent.
      let argsIndent: number | null = null;
      if (/^arguments\s*:/.test(stripped)) {
        argsIndent = ind;
      } else {
        for (let n = lineNo - 1; n >= 1; n--) {
          const t: string = model.getLineContent(n);
          const i = indentOf(t);
          if (i === -1) continue;
          const s = t.slice(i);
          if (/^arguments\s*:/.test(s) && i < ind) {
            argsIndent = i;
            break;
          }
          // Crossed out of this step's body.
          if (s.startsWith('- ') && i < ind) return null;
          // Hit a sibling top-level key at the args indent — not under args.
          if (i < ind && !/^arguments\s*:/.test(s)) return null;
        }
      }
      if (argsIndent === null) return null;

      // Find this step's `type:` (sibling of `arguments:`, same indent).
      const stepType = findEnclosingType(model, lineNo, argsIndent);
      if (!stepType) return null;
      const help = await fetchHelp(stepType);
      if (!help || !help.markdown) return null;
      return {
        contents: [{ value: help.markdown, isTrusted: true }]
      };
    }
  });
}
