/**
 * Monaco YAML completion provider — context-sensitive suggestions for
 * `type:`, `connector:`, `operation:`, plus step-type snippets that
 * scaffold the next required fields.
 */
import { getStepTypes, listOperations, searchConnectors } from './api';

let stepTypeCache: { name: string; detail: string }[] | null = null;
let connectorCache: { name: string; label: string | null }[] | null = null;
const opsCache = new Map<string, { op_name: string; title: string | null }[]>();

async function getStepTypesCached() {
  if (!stepTypeCache) stepTypeCache = await getStepTypes();
  return stepTypeCache;
}
async function getConnectorsCached() {
  if (!connectorCache) connectorCache = await searchConnectors('', 800);
  return connectorCache;
}
async function getOpsCached(connector: string) {
  if (!opsCache.has(connector)) {
    opsCache.set(connector, await listOperations(connector, '', 500));
  }
  return opsCache.get(connector)!;
}

function findConnectorAbove(model: any, lineNumber: number): string | null {
  for (let i = lineNumber - 1; i > 0 && i > lineNumber - 30; i--) {
    const ln = model.getLineContent(i);
    const m = ln.match(/^\s*connector:\s*(.+?)\s*$/);
    if (m) return m[1].replace(/^["']|["']$/g, '');
    if (/^\S/.test(ln)) break;
  }
  return null;
}

/**
 * Snippets keyed by short step type — inserted INSTEAD OF just the keyword
 * when the user picks an item. `${N}` are tab-stops; ${0} is the final cursor.
 *
 * Monaco's autoIndent:'full' (default) re-indents each newline to match the
 * surrounding context, so snippets must NOT include an explicit base-indent
 * prefix.  Each continuation line carries only its *relative* child indent.
 * The `pad` parameter is accepted for API compatibility but intentionally
 * unused — Monaco provides the base indentation automatically.
 */
const STEP_SNIPPETS: Record<string, (pad: string) => string> = {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  connector: (_pad) =>
    `connector\narguments:\n  connector: \${1:connector_name}\n  operation: \${2:operation_name}\n  params:\n    \${0}`,
  set_variable: (_pad) =>
    `set_variable\narguments:\n  arg_list:\n    - name: \${1:my_var}\n      value: \${2:value}\${0}`,
  decision: (_pad) =>
    `decision\narguments:\n  conditions:\n    - option: \${1:"yes"}\n      condition: "{{ \${2:vars.x > 10} }}"\nbranches:\n  \${1:"yes"}: \${3:next_step}\n# default fallthrough when no condition matches\nnext: \${4:default_step}\${0}`,
  find_record: (_pad) =>
    `find_record\narguments:\n  module: \${1:alerts}\n  filter:\n    \${2:name}: \${3:value}\${0}`,
  create_record: (_pad) =>
    `create_record\narguments:\n  module: \${1:alerts}\n  data:\n    \${2:name}: \${3:value}\${0}`,
  update_record: (_pad) =>
    `update_record\narguments:\n  collection: \${1:/api/3/alerts/\${2:uuid}}\n  module: \${3:alerts}\n  data:\n    \${4:status}: \${5:Closed}\${0}`,
  delay: (_pad) => `delay\narguments:\n  delay_seconds: \${1:30}\${0}`,
  manual_input: (_pad) =>
    `manual_input\narguments:\n  record: "{{ \${1:vars.input.records[0]['@id']} }}"\n  type: \${2:single-select}\n  input:\n    title: \${3:Approve this action?}\n    options:\n      - \${4:Approve}\n      - \${5:Reject}\n  timeout: \${6:3600}\${0}`,
  code_snippet: (_pad) =>
    `code_snippet\narguments:\n  code: |\n    \${1:# python}\n    result = {\\"ok\\": True}\${0}`,
  workflow_reference: (_pad) =>
    `workflow_reference\narguments:\n  workflow: \${1:Other Collection:Other Playbook}\n  inputs:\n    \${0}`,
  start: (_pad) => `start\n\${0}`,
  start_on_create: (_pad) =>
    `start_on_create\narguments:\n  module: \${1:alerts}\n\${0}`,
  start_on_update: (_pad) =>
    `start_on_update\narguments:\n  module: \${1:alerts}\n\${0}`,
  stop: (_pad) => `stop\${0}`,
  end: (_pad) => `end\${0}`
};

/** Names of all step types that have snippet templates. */
export const SNIPPET_NAMES = Object.keys(STEP_SNIPPETS);

/** Build a snippet for the given step type. `pad` is accepted for API
 *  compatibility; Monaco provides base indentation automatically. */
export function buildSnippet(name: string, pad: string): string {
  const fn = STEP_SNIPPETS[name];
  return fn ? fn(pad) : name;
}

export function registerYamlCompletions(monaco: any): { dispose: () => void } {
  return monaco.languages.registerCompletionItemProvider('yaml', {
    triggerCharacters: [':', ' '],
    async provideCompletionItems(model: any, position: any) {
      const line = model.getLineContent(position.lineNumber);
      const before = line.slice(0, position.column - 1);
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn
      };

      // type: …  →  step-type snippets
      if (/^\s*type:\s*[A-Za-z_]*$/.test(before)) {
        const types = await getStepTypesCached();
        return {
          suggestions: types.map((t) => {
            const hasSnippet = t.name in STEP_SNIPPETS;
            // Pass '' — Monaco autoIndent:'full' provides the base indentation.
            const insertText = hasSnippet ? buildSnippet(t.name, '') : t.name;
            return {
              label: t.name,
              kind: monaco.languages.CompletionItemKind.Snippet,
              insertText,
              insertTextRules:
                monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
              detail: t.detail,
              documentation: hasSnippet
                ? {
                    value:
                      '```yaml\n' +
                      insertText.replace(/\$\{?\d+:?([^}]*)\}?/g, '$1') +
                      '\n```'
                  }
                : undefined,
              range
            };
          })
        };
      }

      // connector: …
      if (/^\s*connector:\s*[A-Za-z0-9_-]*$/.test(before)) {
        const conns = await getConnectorsCached();
        return {
          suggestions: conns.slice(0, 200).map((c) => ({
            label: c.name,
            kind: monaco.languages.CompletionItemKind.Module,
            insertText: c.name,
            detail: c.label || '',
            range
          }))
        };
      }

      // operation: …  (look up the connector: line above)
      if (/^\s*operation:\s*[A-Za-z0-9_]*$/.test(before)) {
        const conn = findConnectorAbove(model, position.lineNumber);
        if (!conn) return { suggestions: [] };
        const ops = await getOpsCached(conn);
        return {
          suggestions: ops.map((o) => ({
            label: o.op_name,
            kind: monaco.languages.CompletionItemKind.Function,
            insertText: o.op_name,
            detail: o.title || '',
            range
          }))
        };
      }

      return { suggestions: [] };
    }
  });
}
