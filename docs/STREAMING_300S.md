# The 300s ceiling on `fsr-playbook-builder` build turns

> Briefing for an agent investigating why long build turns die ~5 min in.
> All `operations.py:NNN` refs are the **connector** copy
> (`ConnectorsV2/fsr-playbook-builder/fsr-playbook-builder/operations.py`);
> `_loop_helpers.py` / `anthropic_provider.py` are **canonical** fsr_core
> (`fsr-playbook-framework/fsr_core/llm/`). Edit fsr_core, never the vendored copy.

## Symptom
A long agentic **build** run (chat-driven playbook authoring) dies around the
5-minute mark. Even with the action-based streaming feed (contract 2.5.0)
working, a >5-min build is killed mid-flight: the widget's incremental poll
goes dark and the final transcript is lost.

## Architecture of a build turn
- Widget calls connector op **`chat_turn`** (`operations.py:1596`). It makes a
  **single blocking** call: `result = asyncio.run(run_agent_turn(...))` at
  `operations.py:1715`. One HTTP request spans the entire agent loop.
- In parallel the widget polls **`chat_poll`** (`operations.py:1766`) — a pure
  SQLite read by cursor. `chat_turn` writes a `turn_start` frame up front
  (`:1673`), one frame per event via
  `_on_event` → `_event_to_wire` → `storage.append_turn_progress`
  (`:1681-1689`), then a **terminal `stream_end` frame** carrying the
  authoritative transcript + stop_reason (`:1736-1741`).
- The agent loop: `run_agent_turn` (fsr_core) consumes
  `AnthropicProvider.stream()`, which runs up to **`MAX_TOOL_TURNS = 16`** LLM
  rounds (`_loop_helpers.py:166`), each round capped at
  **`STREAM_TIMEOUT_SECS = 300`** (`_loop_helpers.py:184`). fsr_core's own worst
  case is 16×300s — far beyond any gateway ceiling.

## Where the ceiling actually lives (key finding)
Connector ops run under the **gunicorn `fsr-integrations-agent`** process
(user `fsr-int…`, observed PID 111751), config at
`/etc/fsr-integrations-agent/fsr-integrations-agent.conf.py`. They do **not**
run in the `nginx` `cyops-workflow` celery worker. Therefore:

- The ceiling is **gunicorn's `timeout`** (default 30s; FortiSOAR sets it
  higher — likely ~300s). When a request exceeds it, the gunicorn master
  **SIGKILLs the worker** mid-request.
- Consequence: `chat_turn`'s blocking `asyncio.run` is interrupted → the
  terminal `stream_end` frame (`:1736`) is **never written** → `chat_poll`
  never reports `done`, never gets the transcript → run appears to hang/vanish.
- **Streaming does not fix this.** The feed gives incremental UI, but the
  *producer* is still one blocking request that the gateway reaps. (Also:
  per `anthropic_provider.py:247-262`, text is buffered per-LLM-round, not
  token-streamed — granularity is per-round regardless.)

## The durable fix (hypothesis to validate)
**Fix 3 — poll-to-completion:** decouple the producer from the HTTP request.

- `chat_turn` writes `turn_start`, spawns the agent run **detached**, returns
  immediately with `{accepted, turn}`.
- The detached run keeps appending frames + the terminal `stream_end` to SQLite
  independent of request lifetime. `chat_poll` drives the UI and renders the
  terminal transcript on `done`.
- Well-supported by the existing design: the authoritative transcript
  **already rides in the `stream_end` frame**, returned by `read_turn_progress`
  (`storage.py:408`). So `chat_poll` is already a complete substitute for
  `chat_turn`'s return value — the only missing piece is making `chat_turn`
  non-blocking.
- **Open risk:** a bare `threading.Thread` inside a gunicorn **sync** worker
  dies when that worker is recycled/killed. The right detach target depends on
  the gunicorn worker class. If sync workers, the durable answer may be to hand
  the build to the `cyops-workflow` celery queue rather than a thread. There is
  thread precedent in the connector (warmup/health hooks,
  `operations.py:3433`/`3809`) but those are fire-and-forget, not multi-minute.
- **Secondary — payload trim:** `_event_to_wire` does **not** truncate
  `tool_result.content` (`operations.py:614`), unlike the `[:300]` caps
  elsewhere. Large `get_record`/`search` results bloat both the feed rows and
  the final transcript.

## Storage / feed facts
- Feed DB: `~/.fsr_playbook_builder.db` for the `fsr-int…` user
  (`storage.py:42`), overridable by `FSR_PLAYBOOK_BUILDER_DB`. Cross-process
  handoff between `chat_turn` (writer) and `chat_poll` (reader) works because
  it's file-backed SQLite.
- Tables: `turn_progress(session_id, turn, frame_json, is_terminal,
  stop_reason, created_at, cursor)`. `read_turn_progress` scopes to `MAX(turn)`
  and reports `done` if any `is_terminal=1` row exists for that turn
  (`storage.py:370-414`).

## Repos / versions
- **Canonical source:** `fsr-playbook-framework/fsr_core` (edit here) + connector
  `ConnectorsV2/fsr-playbook-builder/`. The connector vendors a *copy* of
  fsr_core (rebuilt by `scripts/build.sh`) — do not edit the copy.
- **Installed on box:** `/opt/cyops/configs/integrations/connectors/fsr-playbook-builder_0_3_81/`
  (v0.3.81). **Verify this copy contains the poll feed** before trusting any
  on-box test.

## What still needs confirming on the VM
1. gunicorn `timeout` + worker class in
   `/etc/fsr-integrations-agent/fsr-integrations-agent.conf.py`.
2. A `[CRITICAL] WORKER TIMEOUT … SIGKILL` line in
   `/var/log/cyops/cyops-integrations/*.log` whose timestamp matches a session
   whose `turn_progress` has frames but **no `is_terminal=1` row** — this
   triangulates the kill exactly.
3. Whether the upstream FortiSOAR API hop (nginx/uwsgi → integrations agent)
   imposes a *lower* ceiling than gunicorn's own `timeout`.

## On-VM commands

```bash
# A. Home dir of the connector-executor user → where the feed DB lives
getent passwd $(ps -o user= -p 111751)           # resolve truncated "fsr-int+"
U=$(ps -o user= -p 111751); H=$(getent passwd "$U" | cut -d: -f6); echo "$U -> $H"
sudo ls -la "$H/.fsr_playbook_builder.db"
sudo -u "$U" printenv FSR_PLAYBOOK_BUILDER_DB     # in case it's overridden

# B. THE CEILING — gunicorn request timeout for connector execution
sudo grep -nE "timeout|workers|worker_class|graceful|keepalive" \
  /etc/fsr-integrations-agent/fsr-integrations-agent.conf.py

# C. Does the INSTALLED 0.3.81 copy even have the poll feed?
grep -c "chat_poll\|append_turn_progress\|turn_progress" \
  /opt/cyops/configs/integrations/connectors/fsr-playbook-builder_0_3_81/operations.py
grep -n "CONTRACT_VERSION" \
  /opt/cyops/configs/integrations/connectors/fsr-playbook-builder_0_3_81/operations.py

# D. Smoking gun — worker-timeout kills in the integrations agent log
sudo ls -t /var/log/cyops/cyops-integrations/ 2>/dev/null
sudo grep -niE "WORKER TIMEOUT|timeout|SIGKILL|killed|booting worker" \
  /var/log/cyops/cyops-integrations/*.log 2>/dev/null | tail -40

# 1. Frame-type histogram for a session's latest turn (proves build emits frames)
DB=$H/.fsr_playbook_builder.db   # from A
sqlite3 "$DB" "SELECT turn, json_extract(frame_json,'\$.type') t, count(*)
  FROM turn_progress WHERE session_id='<SID>' GROUP BY turn, t ORDER BY turn;"

# 2. Did the terminal frame ever get written? (the 300s-kill tell)
sqlite3 "$DB" "SELECT turn, is_terminal, stop_reason, datetime(created_at,'unixepoch')
  FROM turn_progress WHERE session_id='<SID>' AND is_terminal=1;"

# 3. Untruncated tool_result payloads bloating the feed
sqlite3 "$DB" "SELECT turn, length(frame_json) FROM turn_progress
  WHERE session_id='<SID>' AND json_extract(frame_json,'\$.type')='tool_result'
  ORDER BY 2 DESC LIMIT 5;"
```

**Decisive pairing: B + D.** Read the gunicorn `timeout`, then find a
`WORKER TIMEOUT`/SIGKILL log line whose timestamp matches a session whose
`turn_progress` has frames but no `is_terminal=1` row. That confirms no amount
of feed streaming saves the run — the producer request itself is reaped — which
is the case for Fix 3.
