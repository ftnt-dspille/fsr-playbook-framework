/**
 * Theme store. Three options today — `forest` (zinc + teal, default),
 * `cobalt` (navy + electric blue), `light` (bone + teal). Persisted via
 * localStorage; re-applied to <html data-theme="..."> on mount.
 *
 * Light mode covers the chrome (header, drawer, primitives) cleanly.
 * Pages with hardcoded zinc-* Tailwind classes still feel dark in light
 * mode — migrating them is a separate pass.
 */
export type ThemeId = 'forest' | 'cobalt' | 'aurora' | 'light';

export const THEMES: { id: ThemeId; label: string; mode: 'dark' | 'light' }[] = [
  { id: 'forest', label: 'Forest', mode: 'dark' },
  { id: 'cobalt', label: 'Cobalt', mode: 'dark' },
  { id: 'aurora', label: 'Aurora', mode: 'dark' },
  { id: 'light', label: 'Light', mode: 'light' }
];

const STORAGE_KEY = 'fsrpb.theme';

function loadInitial(): ThemeId {
  if (typeof window === 'undefined') return 'forest';
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === 'forest' || saved === 'cobalt' || saved === 'aurora' || saved === 'light')
    return saved;
  return 'forest';
}

function applyToDocument(id: ThemeId) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', id);
}

class ThemeStore {
  current = $state<ThemeId>(loadInitial());

  init() {
    applyToDocument(this.current);
  }

  set(id: ThemeId) {
    this.current = id;
    applyToDocument(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* private browsing / quota — non-fatal */
    }
  }
}

export const theme = new ThemeStore();
