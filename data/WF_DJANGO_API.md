# `/api/wf/*` Django service — full reference

Source-of-truth: runtime introspection (`inspect.getmembers` + `manage.py
show_urls`) of `/opt/cyops-workflow/sealab/`. The Django views are
shipped as compiled Cython (`.so`) so source isn't readable, but the
public surface — class names, method signatures, docstrings, attributes
— is fully recoverable. Captured 2026-05-03 from the dev appliance.

Companion files:
- `store/incoming/wf_django_urls.txt` — full `manage.py show_urls` table (239 routes).
- `store/incoming/wf_introspect.json` — class/method dump for every workflow module (433 KB JSON).

## 1. Run control — `WorkflowViewSet`

URL prefix: `/api/wf/api/workflows/`.

| Action | URL | Sig | Notes |
|---|---|---|---|
| `start` | `POST /<pk>/start/` | `(request, pk)` | "Puts a workflow into the queue" — manual fire alternative to `/api/triggers/1/notrigger/<wf_uuid>` |
| `resume` | `POST /<pk>/resume/` | `(request, pk)` | "Resumes a paused workflow" — for runs in `paused` status (≠ `awaiting`; that one uses manual-wf-input PUT) |
| `retry` | `POST /<pk>/retry/` | `(request, pk)` | "Retry a failed workflow from failed step onwards" — restart from last failed step |
| `approval` | `POST /<pk>/approval/` | `(request, pk)` | Approval-step shortcut. Likely takes `{decision: approve\|reject, comment}` — needs probe |
| `proxy` | `POST /<pk>/proxy/` | `(request, pk)` | Forwarding for cross-tenant playbook calls — verify shape on a multi-tenant box |
| `wfinput_resume` | `POST /<pk>/wfinput_resume/` | (cython) | Decoy — appears canonical but the real path is `PUT /api/wf/api/manual-wf-input/<pk>/`. See `QUERY_API.md`. |
| `refresh_settings` | `POST /<pk>/refresh_settings/` | (cython) | Reload appliance-wide settings; rare |

## 2. Aggregate / dashboard — same ViewSet

| Action | URL | Returns |
|---|---|---|
| `count` | `GET /count/` | `{count: N}` (verified) |
| `metrics` | `GET /metrics/` | `{actionCount: N, ...}` (dashboard tile data) |
| `statuslist` | `GET /statuslist/` | per-status counts (dashboard pie) |
| `delete` | `POST /delete/` | bulk delete by id list — body shape unverified |
| `auto_vacuum` | `POST /auto_vacuum/` | DB cleanup trigger |
| `log_list` | `GET /log_list/` | run-list filtered for log view |
| `vocab` | `GET /vocab/` | enum/picklist values (DRF metadata) |
| `context` | `GET /context/` | JSON-LD `@context` doc |

## 3. Historical (audit) — `HistoricalWorkflowViewSet` + `HistoricalStepViewSet`

URL prefix: `/api/wf/api/historical-workflows/`, `/api/wf/api/historical-steps/`.

Listing form **works**; per-`<pk>` form 500s (PHP-side bug). Use `?workflow=<pk>` to fetch a run's history.

`HistoricalWorkflowViewSet` extra actions: `config`, `count`, `metrics`, `vocab`, `context`, `log_list`.
`HistoricalStepViewSet` extra actions: `vocab`, `context`.

Schema reference: `workflow/migrations/0052_historical_workflow.py` defines all JSONField columns (`args`, `result`, `input`, `data`, `env`).

## 4. Manual input — `WorkflowInputView`

URL prefix: `/api/wf/api/manual-wf-input/`.

| Action | URL | Notes |
|---|---|---|
| `list_wfinput` | `POST /list_wfinput/` | Hydra collection of pending inputs (GET → 405) |
| `retrieve_wfinput` | `POST /<pk>/retrieve_wfinput/` | Adds `input.schema` + `response_mapping` |
| (PUT detail) | `PUT /<pk>/` | Submit response — **canonical resume**. Body: `{workflow:<int_pk>, input:<dict>, type, step_id}` |

Open task #24: enumerate all input-variable + response-option shapes (text, dropdown, checkbox, file, approval, agent-routed, unauthenticated link, email channel, timeout).

## 5. Query — `WorkflowQueryViewSet` / `HistoricalWorkflowQueryViewSet`

Custom payload-style query endpoints (sibling of `/api/query/<resource>` on the PHP side, but Django-resourced).

| URL | Method | Notes |
|---|---|---|
| `/api/wf/api/query/` | POST | Ad-hoc query body (logic+filters+aggregates) over current runs |
| `/api/wf/api/query/workflow_logs/` | GET | Stream of workflow_logs records (audit feed) |
| `/api/wf/api/query/vocab/` | GET | enum vocab |
| `/api/wf/api/query/context/` | GET | JSON-LD context |
| `/api/wf/api/historical-query/...` | (same actions) | Same shape over historical_step / historical_workflow tables |

Body grammar identical to `/api/query/<resource>` (PHP side) — see `store/QUERY_API.md`.

## 6. Schedules — `Periodic*ViewSet`

| URL | View | Notes |
|---|---|---|
| `/api/wf/api/scheduled/` | `PeriodicWorkflowViewSet` | List/CRUD scheduled playbooks |
| `/api/wf/api/scheduled/trigger-now/` | `.trigger` action `(request)` | Fire a scheduled run on demand |
| `/api/wf/api/crontab-schedule/` | `PeriodicCrontabScheduleViewSet` | Cron schedule definitions |
| `/api/wf/api/interval-schedule/` | `PeriodicIntervalScheduleViewSet` | Interval schedule definitions |

## 7. Misc

| URL | View | Notes |
|---|---|---|
| `/api/wf/api/dynamic-variable/` | `DynamicVariableView` | globalVars CRUD |
| `/api/wf/api/jinja-editor/` | `JinjaEditorView` | live Jinja eval (the `_try_render` path probes use) |
| `/api/wf/api/expressions/` | `ExpressionsView` (separate `expression_builder` app) | Expression library |
| `/api/wf/api/expressions/bulk` | `ExpressionsBulkView` | Bulk save/delete |
| `/api/wf/api/manual-wf-input/` | `WorkflowInputView` | Above |

Plus three module-level `View`s without `<pk>`:
- `StartView` (`.view`) — likely "start a workflow by name/uuid" composite endpoint.
- `TasksView` / `TaskDetailView` (`.view`) — celery task introspection.
- `JobHealthcheckView`, `HealthcheckView` — service health checks.
- `ActionCountView` — counts of running actions per playbook (dashboard).
- `CreateAndStartView` — POST a new workflow + start it in one call.
- `OutputView` — download a run's full output as a blob.
- `SMTPConfigView` — SMTP settings CRUD.

These return `(?)` for signatures because they're 100% Cython; only the URL→class mapping is known. Probe live for body shapes when you need them.

## 8. What we still don't know

The view *implementations* are Cython-compiled and don't yield to `inspect.getsource` or `dis.dis`. To learn body validation, error responses, side-effects, etc., you must:

1. Probe live with realistic payloads and capture the response shape.
2. Read serializer attributes (often plain-Python `serializer_class` references).
3. Look at request/response patterns in the FSR UI bundle (`fsr_src/app.unmin.js`) — many of the URL conventions there match these endpoints.

Do **not** attempt to decompile the `.so` files — see the discussion in the project's earlier notes; introspection + live probes have given us full coverage of the public surface without ToS issues.
