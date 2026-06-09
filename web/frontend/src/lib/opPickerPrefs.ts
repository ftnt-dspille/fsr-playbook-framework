/**
 * Recently-picked connector ops per connector, persisted to
 * localStorage. The OperationPicker uses this to float frequently/recently
 * chosen ops to the top — a tiny user-preference store, no backend.
 *
 * Score model: each pick adds 1 to a frequency counter, capped at 10.
 * On lookup, the score is `freq * decay(ageDays)` where decay halves
 * every 14 days. Keeps the list responsive to *recent* habits without
 * needing a "forget" UI.
 */
const STORAGE_KEY = 'fsrpb.op-picker-prefs.v1';
const FREQ_CAP = 10;
const HALF_LIFE_DAYS = 14;
const MS_PER_DAY = 86_400_000;

type OpRecord = { freq: number; lastTs: number };
type Store = Record<string /* connector */, Record<string /* op */, OpRecord>>;

function read(): Store {
  if (typeof localStorage === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function write(s: Store): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* quota — drop silently */
  }
}

export function recordPick(connector: string, op: string): void {
  if (!connector || !op) return;
  const s = read();
  const c = s[connector] ?? (s[connector] = {});
  const rec = c[op] ?? { freq: 0, lastTs: 0 };
  rec.freq = Math.min(FREQ_CAP, rec.freq + 1);
  rec.lastTs = Date.now();
  c[op] = rec;
  write(s);
}

function decay(ageMs: number): number {
  const d = ageMs / MS_PER_DAY;
  return Math.pow(0.5, d / HALF_LIFE_DAYS);
}

/** Score a list of (connector, op) candidates. Higher is better.
 * Returns 0 for unknown ops so the caller can fall back to server order. */
export function scoreFor(connector: string): (op: string) => number {
  const s = read();
  const c = s[connector] ?? {};
  const now = Date.now();
  return (op: string) => {
    const rec = c[op];
    if (!rec) return 0;
    return rec.freq * decay(now - rec.lastTs);
  };
}
