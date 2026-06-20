/**
 * Stub for monaco-editor used in vitest. Tests that need to spy on
 * setValue / setMarkers can vi.mock this and override pieces.
 */
export const MarkerSeverity = { Error: 8, Warning: 4, Info: 2 };

export const languages = {
  register: () => {},
  setMonarchTokensProvider: () => {},
  setLanguageConfiguration: () => ({ dispose: () => {} }),
  registerCompletionItemProvider: () => ({ dispose: () => {} }),
  registerHoverProvider: () => ({ dispose: () => {} }),
  registerSignatureHelpProvider: () => ({ dispose: () => {} }),
  registerCodeActionProvider: () => ({ dispose: () => {} }),
  registerDocumentFormattingEditProvider: () => ({ dispose: () => {} }),
  onLanguage: () => ({ dispose: () => {} }),
  getLanguages: () => [],
  CompletionItemKind: {
    Snippet: 27,
    Module: 8,
    Function: 1,
    EnumMember: 16,
    Field: 4
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
      // Editor lifecycle / interaction listeners — enhanceJinjaEditor
      // wires onDidType + onKeyDown + onDidDispose. The mock just hands
      // back a disposable so the wrapper doesn't crash; tests that
      // exercise the actual typing behavior live in the browser project.
      onDidType: () => ({ dispose: () => {} }),
      onKeyDown: () => ({ dispose: () => {} }),
      onDidDispose: () => ({ dispose: () => {} }),
      onDidFocusEditorText: () => ({ dispose: () => {} }),
      onDidBlurEditorText: () => ({ dispose: () => {} }),
      getModel: () => ({ getLanguageId: () => 'yaml', getLineContent: () => '', getValueInRange: () => '' }),
      getPosition: () => ({ lineNumber: 1, column: 1 }),
      getSelection: () => ({ isEmpty: () => true }),
      getContribution: () => null,
      executeEdits: () => true,
      setPosition: () => {},
      focus: () => {},
      dispose: () => {}
    };
  },
  setModelMarkers: () => {},
  defineTheme: () => {},
  setTheme: () => {}
};

export const KeyCode = { Backspace: 1, Enter: 3, Tab: 2, Escape: 9 };
export class Range {
  constructor(public startLineNumber: number, public startColumn: number,
              public endLineNumber: number, public endColumn: number) {}
}

export default { editor, languages, MarkerSeverity, KeyCode, Range };
