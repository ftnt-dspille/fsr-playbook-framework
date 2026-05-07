/**
 * Stub for monaco-editor used in vitest. Tests that need to spy on
 * setValue / setMarkers can vi.mock this and override pieces.
 */
export const MarkerSeverity = { Error: 8, Warning: 4, Info: 2 };

export const languages = {
  registerCompletionItemProvider: () => ({ dispose: () => {} }),
  registerHoverProvider: () => ({ dispose: () => {} }),
  CompletionItemKind: {
    Snippet: 27,
    Module: 8,
    Function: 1,
    EnumMember: 16
  },
  CompletionItemInsertTextRule: { InsertAsSnippet: 4 }
};

export const editor = {
  create: (_host: HTMLElement, opts: { value?: string }) => {
    let cur = opts?.value ?? '';
    const handlers: ((e: unknown) => void)[] = [];
    return {
      getValue: () => cur,
      setValue: (v: string) => {
        cur = v;
        for (const h of handlers) h({});
      },
      onDidChangeModelContent: (cb: (e: unknown) => void) => {
        handlers.push(cb);
        return { dispose: () => {} };
      },
      getModel: () => ({}),
      dispose: () => {}
    };
  },
  setModelMarkers: () => {}
};

export default { editor, languages, MarkerSeverity };
