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

function indent(line: string): string {
  const m = line.match(/^(\s*)/);
  return m ? m[1] : '';
}

/** Snippets keyed by short step type — inserted INSTEAD OF just the keyword
 *  when the user picks an item. `${N}` are tab-stops; ${0} is the final cursor. */
const STEP_SNIPPETS: Record<string, (pad: string) => string> = {
  connector: (pad) =>
    `connector\n${pad}arguments:\n${pad}  connector: \${1:connector_name}\n${pad}  operation: \${2:operation_name}\n${pad}  params:\n${pad}    \${0}`,
  set_variable: (pad) =>
    `set_variable\n${pad}arguments:\n${pad}  arg_list:\n${pad}    - name: \${1:my_var}\n${pad}      value: \${2:value}\${0}`,
  decision: (pad) =>
    `decision\n${pad}arguments:\n${pad}  conditions:\n${pad}    - option: \${1:yes}\n${pad}      condition: "{{ \${2:vars.x > 10} }}"\n${pad}branches:\n${pad}  \${1:yes}: \${3:next_step}\n${pad}# default fallthrough when no condition matches\n${pad}next: \${4:default_step}\${0}`,
  find_record: (pad) =>
    `find_record\n${pad}arguments:\n${pad}  module: \${1:alerts}\n${pad}  filter:\n${pad}    \${2:name}: \${3:value}\${0}`,
  create_record: (pad) =>
    `create_record\n${pad}arguments:\n${pad}  module: \${1:alerts}\n${pad}  data:\n${pad}    \${2:name}: \${3:value}\${0}`,
  update_record: (pad) =>
    `update_record\n${pad}arguments:\n${pad}  collection: \${1:/api/3/alerts/\${2:uuid}}\n${pad}  module: \${3:alerts}\n${pad}  data:\n${pad}    \${4:status}: \${5:Closed}\${0}`,
  delay: (pad) => `delay\n${pad}arguments:\n${pad}  delay_seconds: \${1:30}\${0}`,
  manual_input: (pad) =>
    `manual_input\n${pad}arguments:\n${pad}  record: "{{ \${1:vars.input.records[0]['@id']} }}"\n${pad}  type: \${2:single-select}\n${pad}  input:\n${pad}    title: \${3:Approve this action?}\n${pad}    options:\n${pad}      - \${4:Approve}\n${pad}      - \${5:Reject}\n${pad}  timeout: \${6:3600}\${0}`,
  code_snippet: (pad) =>
    `code_snippet\n${pad}arguments:\n${pad}  code: |\n${pad}    \${1:# python}\n${pad}    result = {\\"ok\\": True}\${0}`,
  workflow_reference: (pad) =>
    `workflow_reference\n${pad}arguments:\n${pad}  workflow: \${1:Other Collection:Other Playbook}\n${pad}  inputs:\n${pad}    \${0}`,
  start: (pad) => `start\n${pad}\${0}`,
  start_on_create: (pad) =>
    `start_on_create\n${pad}arguments:\n${pad}  module: \${1:alerts}\n${pad}\${0}`,
  start_on_update: (pad) =>
    `start_on_update\n${pad}arguments:\n${pad}  module: \${1:alerts}\n${pad}\${0}`,
  stop: (pad) => `stop\${0}`,
  end: (pad) => `end\${0}`
};

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
        const pad = indent(line);
        return {
          suggestions: types.map((t) => {
            const snippet: ((pad: string) => string) | undefined = STEP_SNIPPETS[t.name];
            const hasSnippet = typeof snippet === 'function';
            const insertText = hasSnippet ? snippet(pad) : t.name;
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
