# Chat streaming to the SOAR widget — implementation plan

**Started**: 2026-05-30. Owner: dcspille.
**Decision pending**: ship Option A (polling) for the demo; Option B
(nginx SSE listener, **no auth**) only if true token-by-token output is
the thing being demoed. This doc specs both so the call is reversible.

## Problem

`/api/integration/execute/` (the path behind the widget's
`executeConnectorAction`) is strictly synchronous: it blocks until the
connector op returns final JSON. There is no native streaming. To show
incremental agent activity (text tokens, tool-use cards, status) in the
widget we need either (A) poll an already-persisted event log, or (B) a
side channel that pushes events as they happen.

## What already exists (do not rebuild)

`fsr_playbooks/llm/run_turn.py::run_agent_turn` already separates two sinks
for every event it emits:

- `on_event: EventCallback` — fired per event *before* persistence. The
  web app wires this to an `asyncio.Queue` and yields SSE frames
  (`web/backend/routes/chat.py:300-360`). **This is the listener path's
  reuse point.**
- `history_sink: HistorySink` (`fsr_playbooks/protocols.py:45`) — persists
  each event as a `chat_message` row scoped by `session_id`, with a
  monotonic `seq`. Docstring confirms the connector pre-supplies
  `session_id`, so rows land **from the first round-trip**. **This is
  the polling path's reuse point.**

`HistorySink.record_chat_message(session_id, turn, seq, kind, content,
name)` is the row shape both options read back.

---

## Shared groundwork (both options need this)

1. **Run the turn in the background, return immediately.**
   Today a connector op that calls `run_agent_turn` would block the
   `execute` request for the whole turn. Change the chat-start op
   (`start_turn` / `send_message`) to:
   - generate/accept a `session_id`,
   - spawn the turn (asyncio task / thread) that runs `run_agent_turn`
     with the connector's `SqliteHistorySink`,
   - return `{session_id, status: "running"}` synchronously.
   The turn keeps writing `chat_message` rows as it progresses.

2. **Session/turn state table.** Add a `turn_status(session_id, turn,
   status, error, updated_at)` row set to `running` at spawn, flipped to
   `done`/`error` in a `finally`. Both options use this to know when to
   stop tailing.

3. **Approval gate interplay.** `resume_agent_turn` + the tier≥3
   `pending_approval` path ([[agent_mutating_op_approval_gate]]) must set
   `turn_status = awaiting_approval` so the client knows to render the
   action card and stop expecting more events until resume.

---

## Option A — Polling the persisted event log (recommended for demo)

### Connector side
- New read op **`get_chat_events`** with params `{session_id,
  after_seq=0, limit=200}`. Body:
  ```python
  rows = con.execute(
      "SELECT turn, seq, kind, content, name FROM chat_messages "
      "WHERE session_id=? AND seq>? ORDER BY seq ASC LIMIT ?",
      (session_id, after_seq, limit)).fetchall()
  status = con.execute(
      "SELECT status,error FROM turn_status WHERE session_id=? "
      "ORDER BY turn DESC LIMIT 1", (session_id,)).fetchone()
  return {"events": [...], "next_seq": rows[-1].seq if rows else after_seq,
          "status": status.status, "error": status.error}
  ```
  Read-only, idempotent, cheap. No new persistence — reads what the turn
  already wrote.

### Widget side
- On send: call `send_message` → get `session_id`.
- Poll `get_chat_events` every ~1.2s via the existing connector service
  (`executeConnectorAction`), passing `after_seq = next_seq` from the
  prior response. Append events; advance cursor.
- Stop when `status in ("done","error","awaiting_approval")`. On
  `awaiting_approval`, render the action card; on approve, call the
  resume op and resume polling.
- Backoff: widen interval to ~3s after N empty polls; reset on activity.

### Pros / cons
- ✓ Inherits SOAR auth + RBAC for free (every poll is an authed
  `execute`).
- ✓ Zero appliance mutation; survives box reinstall; travels in the SP.
- ✓ ~90% of perceived liveness (cards/status appear within ~1s).
- ✗ Not token-by-token; coarser than SSE.
- ✗ Poll overhead (negligible at single-user demo scale).

---

## Option B — nginx-proxied SSE listener (no auth)

**Assumption: auth waived (single-user demo box).** This removes JWT
verification / shared-secret plumbing but NOT the appliance-level costs.

### Listener
- Add an aiohttp app (mirror `microsoft-teams/listener/teams_listener.py`
  structure, **drop `is_valid_secret`**) bound to `127.0.0.1:3978` with:
  - `POST /fsrpb/chat/turn` → spawns `run_agent_turn`, returns
    `{session_id}`.
  - `GET /fsrpb/chat/stream?session_id=…` → SSE. Reuse the web route's
    queue pattern: `on_event=queue.put`, yield `text/event-stream`
    frames; sentinel `_DONE` closes the stream. Lifted almost verbatim
    from `web/backend/routes/chat.py:300-360`.
- Still wire `history_sink` so reloads/late-joiners can fall back to
  Option A's `get_chat_events` (defense in depth + demo resilience).

### nginx prereq (root)
- `run_listener_prerequisite.sh` (model on the teams connector,
  `run_listener_prerequisite.sh:58`) inserts before `/websocket`:
  ```
  location /fsrpb/ {
      proxy_pass https://localhost:3978/;
      proxy_http_version 1.1;
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-Proto https;
      proxy_buffering off;          # REQUIRED for SSE
      proxy_read_timeout 3600s;     # keep stream alive
      proxy_redirect off;
  }
  ```
  Then `nginx -s reload`. Re-apply on upgrade/reinstall.

### Lifecycle
- Supervise the listener process (systemd unit or connector
  `run_listener` hook) so it stays up on `:3978` across reboots.

### Widget side
- `EventSource("/fsrpb/chat/stream?session_id=…")` (same-origin); append
  on each `message`. Fall back to Option A polling if `EventSource`
  errors (covers CSP/proxy hiccups).

### Watch-outs (non-auth)
- **CSP** ([[soar_csp_bug]]): box CSP is malformed; verify `connect-src`
  allows the EventSource before committing — may need a CSP tweak.
- `proxy_buffering off` is mandatory or events arrive batched.
- Appliance mutation does **not** travel in the solutionpack.

### Pros / cons
- ✓ True token-by-token streaming, sub-second.
- ✗ Root prereq + nginx reload + listener supervision.
- ✗ Stateful appliance change; breaks clean "install SP and go".
- ✗ CSP risk on this specific box.

---

## Recommendation & sequencing

Build **shared groundwork + Option A first** — it's the safe demo path
and it's the fallback for Option B anyway. Only add Option B if the demo
narrative is specifically "watch it think token-by-token." Because
Option B reuses the same `history_sink`, Option A is never wasted work.

1. Shared groundwork (bg turn + `turn_status` + approval status).
2. Option A `get_chat_events` op + widget poller. **Demo-ready here.**
3. (Optional) Option B listener + prereq + `EventSource` with A as
   fallback.

## Tests (per repo policy — no test-naked widget changes)

- **fsr_playbooks / connector (pytest):** `get_chat_events` cursor paging
  (after_seq, empty, limit); `turn_status` transitions incl.
  `awaiting_approval`/`error`; background turn writes rows incrementally
  (assert rows appear before turn `done`).
- **Listener (pytest, if B):** SSE frames match `on_event` order;
  `_DONE` closes; history_sink still populated for fallback.
- **Widget (jest):** poller advances cursor, dedupes, stops on terminal
  status, backs off on empty, resumes after approval.
- **Widget e2e (playwright, via Makefile targets only):** send →
  incremental render → action card → approve → completion, against a
  seeded session fixture.
