# FortiSOAR Query API — full reference

Source-of-truth: `/opt/cyops-api/src/{Query,Constants,Filter}` (recon
2026-05-03) plus live probes against the dev appliance. Companion to
`FortiSOAR_Query_Aggregation_and_Filter_Options.md` (covers what's
publicly documented; this doc fills the gaps).

There are **three distinct query/search surfaces** in FSR. Pick by use case:

| Layer | Endpoint | When to use | OR semantics |
|---|---|---|---|
| URL-param filter | `GET /api/3/<resource>?field$op=value` | Quick, single-condition AND queries | **AND only** |
| Query payload | `POST /api/query/<resource>` | Anything non-trivial: nested AND/OR, aggregations, complex filters | **Full AND/OR tree** |
| Global search | `POST /api/search` | Cross-module text search, Elasticsearch-backed | `q` keyword string |

## 1. URL-param filters (`GET /api/3/<resource>?...`)

Grammar: `?[<assoc>__]<field>[$<operator>]=<value>` — multiple parts ANDed.

```
GET /api/3/workflows?steps.stepType.name=Connectors&isActive=true
GET /api/3/workflows?steps.arguments$like=%fortinet-fortisiem%
GET /api/3/alerts?severity.itemValue$in=high,critical
```

- Field path uses **dot** (`steps.stepType.name`) or **double-underscore** (`steps__stepType__name`); the parser converts `__` → `.` (`FilterArrayFactory:46`).
- Operator token is `$` (`AttributeLevelOperators::OPERATOR_TOKEN`). Default operator (no `$op` suffix) is `eq`.
- Multiple parts are ANDed with no way to introduce OR. Repeating a key (`?field=A&field=B`) or array form (`?field[]=A&field[]=B`) returns `400 Bad Request`. Use the payload endpoint for OR.
- Reserved `$`-prefixed parameters (model-level): `$limit`, `$page`, `$partial`, `$orderby`, `$relationships`, `$export`, `$search` (covered below).

## 2. Query payload (`POST /api/query/<resource>`)

Body grammar (per `App\Query\Query` + `App\Query\ExpressionBuilder`):

```jsonc
{
  "logic": "AND" | "OR",
  "filters": [
    // leaf
    { "field": "<path>", "operator": "<op>", "value": <val>, "type": "<type>"? },
    // group — recurse with arbitrary nesting
    { "logic": "AND" | "OR", "filters": [ … ] }
  ],
  "sort": [ { "field": "<path>", "direction": "asc" | "desc" } ],
  "aggregates": [ { "operator": "<op>", "field": "<path>", "alias": "<name>" } ]
}
```

Pagination/options come via query string: `$limit` (default 30, **max 5000** per `api_platform.yaml`), `$page`, `$partial`. They are **not** part of the body.

### 2.1 Attribute operators (per-leaf `operator`)

From `App\Constants\AttributeLevelOperators`:

| Operator | Behavior | Notes |
|---|---|---|
| `eq` | exact equality | Default if `operator` omitted. For association IRIs, the UUID is extracted before comparison. |
| `neq` | exact inequality | |
| `lt`, `lte`, `gt`, `gte` | numeric / date comparisons | Datetime `type` + numeric value → epoch is converted to timestamp. |
| `in` | match any of N values | Accepts an array `[…]` or a pipe-delimited string. **Lowercases string values.** Association IRIs → UUIDs. |
| `nin` | NOT IN — but generated SQL is `NOT IN (…) OR field IS NULL` | Includes NULL rows by design. |
| `like` | SQL LIKE; **lowercases the value** | Use `%` and `_` wildcards. Compares against `LOWER(field)` for non-JSON columns. |
| `notlike` | SQL NOT LIKE | Constant exists, but **excluded from the `ALL_OPERATORS` whitelist** in the enum — works in practice but may be deprecated. |
| `contains` | JSON containment (`jsonb_contains`) | For JSON/object fields. |
| `exists` | JSON path/key existence (`jsonExists`) | Undocumented in the public guide. |
| `isnull` | boolean: `true` → IS NULL, `false` → IS NOT NULL | |
| `search` | per-field full-text search | **Source-only operator** — declared, parsed, used by `FieldExpressionBuilder->search()` internally, but every wire form returns 500. Treat as not-callable from HTTP; use `$search` (§3) instead. |

### 2.2 Logic groups (`logic` field)

`logic: "AND"` or `logic: "OR"` at every nesting level. Nest by setting a child's `logic` field — there is no `or[…]` URL-param shorthand, **only the body form**.

Verified live: `OR(stepType.name eq UpdateRecord, eq InsertData, eq ApprovalManualInput)` → 307 hits (set-uniq union of 222+163+4 baselines). `AND(stepType.name eq A, eq B)` → 0 (sanity: a single column can't equal two values).

### 2.3 Sort

`sort: [{"field": "<path>", "direction": "asc"|"desc"}]`. Field aliases assigned by aggregates can be sorted on. Sorting through associations may be skipped in some aggregate paths.

### 2.4 Aggregations

From `App\Constants\AggregateOperators`:

| Operator | DQL | Notes |
|---|---|---|
| `fields`, `select` | `SELECT field AS alias` | Selecting raw fields; **does not flip query into aggregate mode**. |
| `count` | `COUNT(field)` | `field: "*"` → root alias. |
| `countdistinct` | `COUNT(DISTINCT field)` | Constant exists; **omitted from `ALL_OPERATORS` whitelist** but works at the builder layer. |
| `groupby` | adds `GROUP BY field` | Pair with a metric (count/avg/sum/…). |
| `distinct` | `DISTINCT field` | Documented in the public table only as "advanced"; works in practice. |
| `sum`, `max`, `min`, `avg`, `median` | corresponding SQL aggregates | `avg`/`median` exist as constants but are **omitted from the whitelist** (still emitted). |

A query is treated as aggregate iff `aggregates[]` contains anything other than `fields` / `select` (`AdvancedQueryController::isAggregateQuery`). That changes the response shape (`hydra:member` becomes aggregate rows instead of records).

### 2.5 Field paths

- Root field: `name`, `description`, `isActive`.
- Association traversal: `collection.name`, `steps.stepType.name`, `steps.arguments`. Arbitrary depth.
- Underscore form: `collection__name` ≡ `collection.name`.
- JSON column traversal: stored JSON columns (`Workflow.parameters`, `WorkflowStep.arguments`) accept `like` / `contains` / `exists` against the serialized text or path. **Per-key equality (`arguments.connector = 'foo'`) is NOT supported** — the filter resolves the field path through Doctrine ORM relations, not through JSON keys.

### 2.6 Persisted queries (`/api/3/query_objects`)

Save a body as a `Query` entity, then invoke via `POST /api/query/<resource>/<queryId>`. Body becomes reusable + permission-grantable. Not yet probed end-to-end — schema lives at `/api/3/query_objects` (CRUD).

## 3. `$search` query-string parameter

A top-level URL parameter on **both** `GET /api/3/<resource>` and `POST /api/query/<resource>`:

```
GET  /api/3/workflows?$search=fortinet
POST /api/query/workflows?$search=fortinet  + body filters
```

Probe-confirmed semantics (2026-05-03, against dev appliance, 1667 total workflows):

| Probe | Total | Inference |
|---|---:|---|
| `$search=phish` | 4 | substring match |
| `$search=fortinet` | 430 | |
| `$search=FORTINET` | 430 | **case-insensitive** |
| `$search=fortinet fortisiem` | 43 | tokenized (multi-token, likely AND of tokens) |
| `$search=a` | 1621 | **no minimum length enforced at query layer** |
| `$search=xx_no_match_xx` | 0 | clean miss path |
| `$search=fortinet` ∧ body `isActive=true` | 10 | combines with body filters as AND |
| `name like %phish%` (body) | 2 | for comparison: $search=phish hit 4, so $search covers more fields than `name` alone |

So `$search`:
- Case-insensitive substring across an entity's "searchable fields" (per-entity set, defined elsewhere; covers at least `name` and `description` for workflows).
- Tokenized when multi-word.
- AND-combinable with body filters.
- No min-length gate.
- Top-level parameter — does NOT belong inside the body's `filters[]` array (silently ignored if placed there: `{"$search": "x"}` in body → returned all 1667 records).

The constant `AttributeLevelOperators::SEARCH_TERM = '$search'` is what wires this token. Distinct from the per-field `search` operator (which is internal-only — see §2.1).

## 4. `/api/search` — Elasticsearch-backed global search

`POST /api/search` (controller `App\Controller\SearchController::search`).

Body shape (per the controller source; the live endpoint currently 500s on dev with `TypeError` — likely the same PHP 8 stdClass-vs-array issue we saw on `bulkupsert`, so wire this from a known-working appliance before relying on it):

```jsonc
{
  "q": "fortinet phishing",         // search term, **min 3 chars** enforced
  "index": ["alerts", "incidents"], // which modules — required, non-empty
  "size": 30,                       // page size
  "offset": 0,                      // skip
  "searchType": "_default",         // optional; alternate search profiles per entity
  "modifyDateGte": 0,               // epoch lower bound, optional
  "modifyDateLte": 0                // epoch upper bound, optional
}
```

Differences from `$search`:
- **Multi-index** — search across many entities in one call.
- **Elasticsearch-backed** — `AppConstants::ELASTIC_SEARCH_OPERATION_KEY = 'esoperation'` ties this path to ES.
- **3-character minimum** — enforced server-side.
- **Team / RBAC scoped** — joins `accessibleTeamIris` automatically; results respect record-level permissions.
- **searchType selector** — entity-specific search profiles (e.g., `_default` vs. `phonetic`); enumerate per entity if needed.

Use this for "global search bar" UX. For programmatic per-entity filtering use the query payload (§2) — it's deterministic, AND/OR-composable, and doesn't depend on the ES side-channel.

## 5. Pagination, partial, format

| Param | Default | Notes |
|---|---|---|
| `$limit` | 30 | Max **5000** per `api_platform.yaml#maximum_items_per_page`. |
| `$page` | 1 | 1-indexed. |
| `$partial` | false | When true, `hydra:totalItems` is omitted (faster). Useful when paging blindly. |
| `$orderby` | — | Model-level operator (`ModelLevelOperators::ORDER_BY = 'orderby'`); equivalent to body `sort[]`. |
| `$relationships` | false | Expand nested entities (`stepType` becomes a dict instead of an IRI string). |
| `$export` | false | Strip identity fields so the result re-imports cleanly. Used by `pull` and the export UI. |

## 6. Operator-by-layer summary

```
URL-param  filter:    eq, neq, lt, lte, gt, gte, in, nin, like, notlike,
                      contains, exists, isnull           — ANDed
URL-param  reserved:  $limit, $page, $partial, $orderby, $relationships,
                      $export, $search
Payload    filter:    same 13 attribute ops, PLUS arbitrary AND/OR nesting
Payload    aggregate: fields, select, count, countdistinct, groupby,
                      distinct, sum, max, min, avg, median
Global     search:    POST /api/search  {q, index[], size, offset, …}
```

## 7. Gaps & quirks worth flagging

- **Whitelist mismatch**: `AggregateOperators::ALL_OPERATORS` omits `countdistinct`, `avg`, `median`; `AttributeLevelOperators::ALL_OPERATORS` omits `notlike`. The constants are used by some validator path but not the DQL builder, so omitted operators **still execute** — they may be UI-hidden or pending deprecation.
- **`search` (per-field operator)**: declared but unwired for HTTP; every form returns 500.
- **Body `$search`**: silently ignored if placed inside the body. Always use the query string.
- **Per-key JSON equality**: `arguments.connector=foo` returns 0 even when matches exist; use `arguments$like=%foo%` (URL form) or `{field: "arguments", operator: "like", value: "%foo%"}` (payload).
- **`/api/search` PHP 8 bug**: live endpoint 500s on dev — same family as the `bulkupsert` `array_key_exists` on stdClass issue. Body shape above is from source; verify on your appliance.
- **No persisted-query probe yet**: shape of `/api/3/query_objects` POST body and `/api/query/<r>/<id>` invocation is unverified.

## 8. Source anchors (recon `fsrpb_recon_20260503-140810.tgz`)

- `E_filters/Query/Query.php` — `Query` class, `logic` constructor arg.
- `E_filters/Query/ExpressionBuilder.php` — `logicAnd`, `logicOr` factories.
- `E_filters/Query/FieldExpressionBuilder.php:131` — internal `search($value)` method.
- `E_filters/Constants/AttributeLevelOperators.php` — full leaf-operator enum + `OPERATOR_TOKEN`.
- `E_filters/Constants/AggregateOperators.php` — aggregate enum.
- `E_filters/Constants/ModelLevelOperators.php` — `orderby` only.
- `E_filters/Filter/FilterArrayFactory.php:40-75` — URL-param parser, double-underscore → dot, single-triple per part.
- `recon_20260503-122258/Controller/AdvancedQueryController.php` — `POST /api/query/<r>` dispatch + aggregate-mode detection.
- `recon_20260503-122258/Controller/SearchController.php` — `POST /api/search` Elasticsearch path.
