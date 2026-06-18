// Loads the jinja-editor widget's filter constants file (an IIFE that
// expects `window`) and prints its filterSignatures + categoryOrder as JSON.
// Used by probe_jinja.py via subprocess.
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const path = process.argv[2];
if (!path) { console.error("usage: node _jinja_extract.mjs <path>"); process.exit(2); }
const src = await readFile(path, "utf8");
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const ns = sandbox.window.JinjaEditorWidget || {};
process.stdout.write(JSON.stringify({
  filters: ns.filterSignatures || {},
  categories: ns.filterCategoryOrder || [],
}));
