# Architecture Hardening Plan — DONE

All four items shipped. Final tallies: frontend 387 tests, backend 182,
E2E 19 (588 total) all green, svelte-check 0 errors / 0 warnings.

| Item | Status | Highlights |
|---|---|---|
| 1. Collapse YAML sources of truth | ✅ | 5 buffers → 1 (`playbookStore.currentYaml` / `replaceYaml`). `yamlStore` + `pageBindings.svelte.ts` deleted. `visualStore.renderToYaml` writes straight into the canonical buffer. Bonus: fixed 12 jsdom unhandled rejections from MonacoCode/MonacoYaml async-mount race. |
| 2. Save mutation primitive | ✅ | `saveState` machine (`idle`/`pending`/`saving`/`retrying`/`error`/`conflict`/`saved-just-now`). Exp backoff on transient (5xx + network). Single-flight w/ post-save edit pickup so no edit is ever lost. `online` listener auto-retries on reconnect. Live pill + Retry button in `PlaybookHeader`. |
| 3. Optimistic concurrency | ✅ | `drafts.head_revision_id` + online migration. PUT honors `If-Match`; 409 carries `{server_revision_id, server_updated_ts, server_yaml}`. Frontend surfaces a conflict modal with Overwrite / Reload-theirs. |
| 4. Revision pruning | ✅ | Tiered retention for auto-saves (1min/10min/1hr/1day buckets across hour/day/week/month; >30d dropped). Manual saves kept forever. Atomic with the insert. New `(draft_name, is_auto, created_ts)` index. |

See per-item details below for the implementation record.

---

## Item 1 — Collapse the YAML sources of truth

**Problem.** Five places claim to be "the current YAML":
`yamlStore.text` (legacy), `playbookStore.state.active.yaml`,
`visualStore.state.graph.source.yaml`, Monaco's internal buffer,
and the `yaml` $state inside `pageBindings`. Every cross-store
effect that exists is glue to keep these five in sync. Every bug
this session has lived in that glue.

**Target.** ONE canonical buffer:
`playbookStore.state.active.yaml`. Everything else either reads
from it or is a derived parse of it.

**Plan.**

1. **Stage 1 — Promote `playbookStore` to authority.**
   - Make `playbookStore.state.active.yaml` the only writable
     in-memory string.
   - Add a typed getter `playbookStore.currentYaml` (returns `''`
     when no active doc) so consumers stop guarding `state.active`
     themselves.
   - Add `playbookStore.replaceYaml(next, source)` that updates
     yaml + recomputes dirty + notifies. Replaces `setYaml` and
     centralizes the write side.

2. **Stage 2 — Delete `yamlStore`.**
   - `yamlStore.text` is just a mirror; remove it.
   - `Chat`, `DiagnosticsList`, `DeployPanel`, `Console`, any other
     reader → switch to `playbookStore.currentYaml`.
   - Drop the `yamlStore` localStorage key (one-shot migration
     reads it once if present, writes into `playbookStore`'s
     last-opened pointer, then deletes).

3. **Stage 3 — Make `visualStore.graph.source.yaml` derive, not
   shadow.**
   - The graph keeps its parsed nodes/edges; the source string is
     fetched on demand from `playbookStore.currentYaml`.
   - `visualStore.renderToYaml()` writes its emitted YAML into
     `playbookStore.replaceYaml(...)` directly — no more "render
     and then sync" two-step.

4. **Stage 4 — Make Monaco bind directly.**
   - `MonacoYaml` accepts `value: () => string` (reactive accessor)
     instead of a snapshot prop.
   - `onInput` writes straight into `playbookStore.replaceYaml`.
   - The `yaml` $state inside `pageBindings` goes away.

5. **Stage 5 — Retire `pageBindings.svelte.ts`.**
   - Once the local `yaml` $state is gone, the bindings module
     shrinks to just the active-sync + autosave effects. Move
     those into `playbookStore` itself as a `bindAutosave()` hook
     the page calls once.

**Multi-user prep.** None needed — single canonical buffer is the
right shape regardless of user count.

**Risk.** This touches every component that reads YAML. Mitigated
by the e2e suite + the page-wiring integration tests we just added —
both will scream if the wiring breaks.

**Estimate.** 1-2 days of focused work. Done in stages, each
landing green CI.

---

## Item 2 — Real save mutation primitive

**Problem.** `playbookStore.save()` is a one-shot `fetch` wrapped
in `try/catch`. No queue, no retry, no offline awareness, no
visible "saving…" / "save failed, retry?" state beyond a tiny
status pill. Network blips eat edits silently.

**Target.** A `saveMutation` primitive owned by `playbookStore`
that:
- Coalesces rapid edits (debounce + most-recent-wins).
- Retries with exponential backoff on transient failures (network
  errors, 5xx).
- Surfaces a `saveState`: `'idle' | 'pending' | 'saving' |
  'retrying' | 'error' | 'saved-just-now'`.
- Exposes `errorMessage` + `retryNow()` for the UI.
- Never loses an edit: if save is in flight and a new edit lands,
  queue the new buffer for after the current call returns.

**Plan.**

1. Add `playbookStore.saveState` ($state) and `lastSaveError`.

2. Replace the autosave $effect's inline save call with a state
   machine:
   ```
   idle → (dirty) → pending [debounce] → saving → saved/error
                                            ↑          ↓
                                            └── retrying (backoff)
   ```

3. New state surfaces in `PlaybookHeader`:
   - Replace the static "unsaved" pill with a live state pill
     (`Saving…`, `Saved 3s ago`, `Save failed — Retry`).
   - "Retry" button → `playbookStore.retrySave()`.

4. Backend already returns clean errors; just plumb them through.

5. Surface offline explicitly: a `navigator.onLine` listener
   short-circuits to `'error'` with message "offline — will retry
   when reconnected" + auto-retries on `online`.

**Multi-user prep.** Save state is per-document, not per-user;
already correctly scoped.

**Estimate.** 1 day. Doable independently of #1 — if #1 lands
first, this is even smaller because the saveState lives on the
already-clean playbookStore.

---

## Item 3 — Optimistic concurrency (single-tab race protection)

**Problem.** Open the same draft in two tabs, edit in both, save
in both: last-write-wins, silently. Not multi-user yet — but the
single-user multi-tab case bites today.

**Target.** Backend rejects saves that would overwrite a newer
revision; frontend surfaces a recoverable conflict UI.

**Plan.**

1. **Backend.**
   - `drafts` table already has `updated_ts`. Add `revision_id`
     (auto-increment per draft) — cheaper to compare than
     timestamps.
   - `PUT /api/playbooks/draft/{name}` accepts optional header
     `If-Match: <revision_id>`. When present, return 409 if the
     stored `revision_id` doesn't match.
   - Response: `{ ok: false, code: 'conflict', server_revision_id,
     server_updated_ts, server_yaml }`.

2. **Frontend.**
   - `playbookStore.state.active` gains `revisionId: number`.
   - `playbookStore.save()` sends `If-Match`.
   - On 409: pop a small recoverable modal: "This draft was
     modified in another tab. Show diff? Overwrite anyway? Reload
     theirs?" Don't auto-merge — show the user the choice.

3. **Migration.** Existing draft rows get `revision_id = 1`
   backfilled. Old clients (no `If-Match`) keep working — backend
   only enforces when the header is present.

**Multi-user prep.** This is the exact protocol you'd want for
multi-user too. `If-Match` + revision IDs is how every modern
cloud-backed editor handles concurrency (Notion, Linear, Figma).
Doing it now means later multi-user work is just "tell users who
edited what."

**Estimate.** Half a day backend + half a day frontend.

---

## Item 4 — Revision pruning

**Problem.** `revisions` table inserts on every autosave. ~1
revision per second of active edit. A single afternoon of work
on a chatty playbook creates thousands of rows. Will eventually
bloat `drafts.db` and slow the Revisions list query.

**Target.** Sensible retention policy with no user-visible loss
of safety.

**Plan.**

1. **Retention policy.**
   - Keep all **manual** saves forever (the user explicitly hit
     Save — that's a checkpoint they care about).
   - For **auto** saves: keep last hour at 1-minute granularity,
     last day at 10-minute granularity, last week at 1-hour
     granularity, last month at 1-day granularity, then drop.
   - Same shape Google Docs uses ("aggregate older changes").

2. **Pruning trigger.** Run on every save (cheap — index lookups,
   no full table scan). One DELETE statement per granularity
   tier, scoped to this draft. Keep it inside the transaction
   that inserted the new revision so prune+insert are atomic.

3. **Schema-side: add `auto BOOLEAN` index** (already a column,
   add the index) so the prune predicate is fast.

4. **Surface in UI.** Revisions list already shows `auto` flag;
   no UI change needed. Manual saves visually stand out.

**Multi-user prep.** None needed — retention is per-draft, not
per-user.

**Estimate.** ~3 hours. Independent of everything else.

---

## Sequencing

Recommended order:

1. **Item 1** first. Highest payoff (kills the bug class), and
   makes #2 + #3 cleaner because state lives in one place.
2. **Item 4** opportunistic — drop it in as a small PR when bored.
3. **Item 2** — save state machine + retry. Builds on cleaner #1.
4. **Item 3** — optimistic concurrency. Last because the conflict
   modal UX wants to read live `saveState` from #2.

Total: ~4 days of focused work, landing in 4 PRs, each
independently shippable.

## What's NOT in this plan (deliberate)

- **Multi-user authentication / per-user data scoping.** You said
  not now. None of items 1-4 lock you out of adding it later.
  The cleanest hook is to namespace the `drafts` table with a
  `user_id` column when you're ready — every other change above
  is per-document, which is the right scope.
- **Offline support (Service Worker + IndexedDB).** Defer until
  network reliability is actually a felt pain.
- **CRDT / real-time collab.** Deep rabbit hole, no current need.
- **Generated API client from OpenAPI.** Nice-to-have, not on the
  critical path.
