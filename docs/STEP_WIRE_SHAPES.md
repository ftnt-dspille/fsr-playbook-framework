# FortiSOAR Playbook Step Wire Shapes (editor-derived)

Authoritative per-step argument shapes extracted from the FortiSOAR 8.0 editor
bundle (`800_app.min.js`, beautified) — what the editor actually compiles before POST,
replacing values inferred from playbook JSON. Each row cites the step's editor
controller/constant. Generated 2026-06-25 via a 21-agent extraction workflow.

## Reverse-engineered Connector step type schema from FortiSOAR playbook editor bundle

editor: PLAYBOOK_STEP_TYPES.Connectors registered at line 33858. ConnectorStepCtrl controller at lines 37204-37476. Template: app/playbooks/designer/step-arguments/connector.html · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `connector` | string |  | True |  | Connector name/ID (e.g., 'Slack', 'ServiceNow'). Set at line 37276 via setActiveConnector() from e.name. Essential system key. |
| `name` | string |  | True |  | Connector display label. Set at line 37276 via e.label. Displayed in step name. Present in ~1255/1256 instances per inferred schema. |
| `version` | string |  | True |  | Connector version string. Set at line 37276 via e.version. Updated when agent changes (line 37441). System key. |
| `operation` | string |  | True |  | Operation identifier (technical name). Set at line 37450 via o.operation.operation. System key. |
| `operationTitle` | string | (derived from operation metadata) | False |  | Human-readable operation title. Set at line 37450 via o.operation.title. Present in ~1254/1256 instances per inferred schema. Not critical for playback. |
| `params` | object | {} | True |  | Operation-specific parameters. Initialized as empty object at line 37450. Values set from user input (line 37389). If received as array, converted to object (line 37389). System key. |
| `config` | string | null or first default configuration UUID | False |  | Configuration UUID or dynamically selected string. Set at lines 37398-37400, 37454. Deleted/set to null at line 37450 if operation has is_config_required=false. Present in ~1212/1256 instances. Compile-time default selection happens at v() function (line 37424-37429). |
| `pickFromTenant` | boolean | false | False |  | Flag for tenant-based agent selection. Set at line 37276 to false on connector change. Set to true at line 37439 when agent='Pick From Record Ownership'. Present in ~457/1256 instances per inferred schema. |
| `agent` | string | undefined | False |  | Remote agent name for distributed deployments. Set at line 37441 or 37439. Can be agent name or 'Pick From Record Ownership'. Deleted at line 37443 or 37454 when no agent selected. Compile-time rule (line 34487): if agent + for_each exists, delete for_each.break_loop. NOT in inferred schema but core |
| `dynamicallySelected` | boolean | false | False |  | Flag indicating config is dynamically selected via expression. Set to true at line 37454. Set to false at line 37454 when toggling back to static. Toggled via toggleConfig UI state (line 37311). UI state flag kept in arguments during persistence. |
| `annotation` | object | undefined | False |  | Connector annotation metadata (if connector has annotations). Set conditionally at line 37276. Used to filter operations by annotation.name (line 37385). UI-only field for editor state management. |
| `when` | string | undefined | False |  | Step condition. Deleted at compile-time if empty/undefined (line 34487). Standard playbook step field. |
| `for_each` | object | {} | False |  | Loop configuration. Structure: {item, condition, __bulk, parallel, break_loop}. Compile-time rule (line 34487): delete for_each if item empty; if agent + for_each.break_loop, delete break_loop. Standard playbook step field. |
| `ignore_errors` | boolean | undefined | False |  | Error handling flag. Present in ~40/1256 instances per inferred schema. Standard playbook step field. |
| `message` | object | undefined | False |  | Notification message. Compile-time rule (line 34487): delete if content empty. Standard playbook step field. |
| `step_variables` | object | undefined | False |  | Step-level variable declarations. Present in ~999/1256 instances per inferred schema. Standard playbook step field. |

**Compile transforms:** Step arguments cleanup during save (line 34487-34490): DELETE empty/undefined: when, mock_result, do_until (if condition empty), for_each (if item empty), message (if content empty). CONNECTOR-SPECIFIC: if arguments.agent AND for_each + break_loop both exist, DELETE for_each.break_loop. GENERAL: if apply_async=true, DELETE for_each.break_loop. LINE 34498: Update stepType.displayName to '{name} {version}'. LINE 37450: if operation.is_config_required=false, set config=null. LINE 37389: if params received as array, convert to {}. LINE 37454: Dynamic config selection: toggleConfig=true → set dynamicallySelected=true, DELETE agent; toggleConfig=false → set dynamicallySelected=false, RESTORE agent.

<details><summary>evidence</summary>

- 37276-37276: setActiveConnector writes connector, name, version, pickFromTenant, annotation to o.config.arguments
- 37450-37450: S() operationChanged writes params={}, operation, operationTitle; conditionally config=null
- 37439-37454: T() agentChanged and C() configurationChanged manage agent, pickFromTenant, dynamicallySelected mutations
- 34487-34490: Compile-time cleanup rules for all step arguments including Connector-specific logic
- 34498: Connector displayName mutation for playbook save
- 37311-37385: Controller lifecycle reads all argument keys including UI-only ones
- Diff vs inferred schema (fsr-schema.ts:241-293): Bundle reveals agent, dynamicallySelected, annotation which inferred schema missed or partially captured

</details>

## Document FASTrigger (TRIGGER_PARENT_STEP_TYPE) authoritative argument shape from editor bundle

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `__triggerLimit` | boolean | undefined (conditional initialization) | False |  | When undefined, editor initializes to true (if triggerOnSource is undefined); used to enable/disable record replication triggering. Compile transform: affects triggerOnSource and triggerOnReplicate initialization at line 23726. |
| `triggerOnSource` | boolean | true | False |  | Editor initializes at line 23726; set to true/false based on __triggerLimit and user selection. Controls whether trigger fires on source record creation. |
| `triggerOnReplicate` | boolean | false or computed | False |  | Editor initializes at line 23726; inverse of triggerOnSource when __triggerLimit is true. Controls whether trigger fires on replicated records. |
| `step_variables` | object | {} | True |  | System key at line 23725. Contains 'input' property which is deleted for all triggers at init, then reconstructed at compile-time. Input structure varies by trigger type (lines 34553-34572): API_TRIGGER={params: {api_body, api_params}}, ACTION_TRIGGER={params: {...}, records}, POST_*_TRIGGER={record |
| `resources` | array<string> | [] | False |  | Array of module/resource IRIs. Initialized from arguments.resource (legacy field) at line 23754 if present. Validated at line 23744-23750; invalid resources are filtered out. Watched at line 23823-23824 to trigger field reloading. Present in all trigger types (line 23803). |
| `resource` | string | undefined | False |  | Legacy field, converted to resources array at line 23754. Editor checks both arguments.resource and arguments.resources (line 23848). |
| `inputVariables` | array<{name: string, _expanded?: boolean, ...}> | [] | False |  | ACTION_TRIGGER specific (line 23784). Array of input parameter definitions. Each variable maps to request.data[name]. Editor sets _expanded flag at line 23830 for UI state. Compile transform creates params object from inputVariables at lines 34562-34564. |
| `route` | string | UUID.generate() | False |  | API_TRIGGER specific (line 23780, UUID generated at line 23780). ACTION_TRIGGER generates UUID at line 23787. Format: 'deferred/...' for Basic auth or 'deferred/' prefix patterns. Modified via apiSuffix watch at line 23827-23828. |
| `authentication_methods` | array<string> | [] | False |  | API_TRIGGER specific (line 23778-23780). Array containing single auth method: '' (token), 'Basic' (basic auth), or 'anonymous'. Editor watches authSelection at line 23825-23826 and updates route accordingly. |
| `executeButtonText` | string | 'COMPONENTS.GRID.EXECUTE' (translated) | False |  | ACTION_TRIGGER specific (line 23784). User-visible button text. Translated via translationService.instantTranslate() |
| `showToasterMessage` | object: {visible: boolean, messageVisible: boolean, message?: string} | {visible: false, messageVisible: true} | False |  | ACTION_TRIGGER specific (line 23784-23786). Controls if toast message is shown after execution. messageVisible defaults to true; message text optional. Editor validates at line 23732. |
| `singleRecordExecution` | boolean | false | False |  | ACTION_TRIGGER specific (line 23787). Editor computes from input.runInnerSelection at line 23797. When true with records, executes once per record sequentially instead of all at once. |
| `noRecordExecution` | boolean | false | False |  | ACTION_TRIGGER specific (line 23787). Editor computes from input.runSelection at line 23797. When true, playbook executes without record context. Compile transform at line 34562 checks this. |
| `displayConditions` | object: {[moduleName]: {visibility: string, conditions?: unknown, filters?: ...}} | {} | False |  | ACTION_TRIGGER specific (line 23787). Maps module names to conditional visibility rules. Accessed at line 23787 to compute displayConditionsExpanded for UI. Set via prepareResourceField at line 23834. Used for field-level visibility rules (line 12727). |
| `_promptexpanded` | boolean | false | False |  | ACTION_TRIGGER specific (line 23830). Set to true when input focus is on input-variable fields. Transient UI state, stored on arguments. |
| `fieldbasedtrigger` | object: {filters: array, logic: 'AND' \| 'OR'} | {filters: [], logic: 'AND'} | False |  | Initialized on trigger step's arguments via prepareResourceField (line 23834-23836). Stores filter/condition logic for the trigger. Also set via 'START_ACTION' logic at line 48761. |

**Compile transforms:** Compile-time mutations before POST (lines 34486-34607):  1. **For all triggers**:     - i.description = null (if undefined)    - i.status = null (if undefined)    - i.group = null (if undefined)    - i.arguments.for_each/do_until/when/ignore_errors are preserved as-is (generic step properties, line 34600)  2. **API_TRIGGER specific** (line 34553-34558):    - step_variables.input is set to: {params: {api_body: "{{vars.request.data}}", api_params: "{{vars.request.params}}"}}  3. **ACTION_TRIGGER specific** (line 34560-34564):    - step_variables.input is constructed as:      - If inputVariables.length > 0: params[varName] = '{{vars.request.data["varName"]}}'      - Always adds: records: "{{vars.input.records}}"  4. **POST_CREATE_TRIGGER, POST_DELETE_TRIGGER, POST_UPDATE_TRIGGER** (line 34566-34572):    - step_variables.input is set to: {records: ["{{vars.input.records[0]}}"]}

<details><summary>evidence</summary>

- 800_app.beautified.js:638 — TRIGGER_PARENT_STEP_TYPE constant definition
- 800_app.beautified.js:23703-23842 — csTrigger directive full implementation (trigger editor UI controller)
- 800_app.beautified.js:23714-23726 — Common trigger argument initialization
- 800_app.beautified.js:23776-23781 — API_TRIGGER specific initialization
- 800_app.beautified.js:23782-23794 — ACTION_TRIGGER specific initialization
- 800_app.beautified.js:23797 — singleRecordExecution/noRecordExecution computation
- 800_app.beautified.js:23825-23826 — authentication_methods watch handler
- 800_app.beautified.js:23827-23828 — route watch handler
- 800_app.beautified.js:23830-23831 — _promptexpanded and inputVariables[n]._expanded UI state
- 800_app.beautified.js:23834-23836 — displayConditions and fieldbasedtrigger initialization
- 800_app.beautified.js:34552-34572 — Compile-time step_variables.input transforms by trigger type
- 800_app.beautified.js:34600 — Generic step properties (for_each, do_until, when, ignore_errors) validation

</details>

## SetVariables Step Type - Authoritative Argument Schema

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `for_each` | object |  | False |  | Optional control-flow loop. Structure: {condition: string, item: string, __bulk?: boolean, parallel?: boolean}. Removed at compile time if empty. Present in ~4/1386 instances. Excluded from step variable generation. |
| `do_until` | object |  | False |  | Optional retry loop. Structure: {condition: string, delay: number\|string, retries: number\|string}. Removed at compile time if empty. Excluded from step variable generation. |
| `when` | string |  | False |  | Optional conditional execution (Jinja expression). Removed at compile time if empty. Becomes step variable. |
| `message` | object |  | False |  | Optional message/logging. Structure: {content: string, records: string, tags?: unknown[], thread?: boolean, type?: string, parentstepid?: string, tenant?: string}. Removed at compile time if empty. Present in ~7/1386 instances. Becomes step variable. |
| `_tmp` | string |  | False |  | [system key] Internal/temporary. Present in 1/1386 instances. Becomes step variable. |
| `name` | string |  | False |  | [system key] Step name metadata. Present in 3/1386 instances. Becomes step variable. |
| `params` | string |  | False |  | [system key] Parameters. Present in 20/1386 instances. Becomes step variable. |
| `result` | string |  | False |  | [system key] Result reference. Present in 2/1386 instances. Becomes step variable. |
| `task_id` | string |  | False |  | [system key] Task identifier. Present in 3/1386 instances. Becomes step variable. |
| `[key: string]` | unknown |  | False |  | User-defined variables (arbitrary dynamic keys). ~1203/1386 instances have additional keys. Each becomes a step variable available to subsequent steps as {{vars.step_name.variable_name}}. Cannot use reserved words: input, step_variables, do_until, ignore_errors, when, for_each, items, result, reques |

**Compile transforms:** SetVariable compile-time cleanup (line 34487): removes empty/undefined when, do_until, for_each, message fields. Validation (lines 34499-34502): rejects if arguments has 'input' key. Step variable generation (lines 25491-25493): excludes for_each and do_until from step variables. UI controller excludes these from editing: condition, mock_result, ignore_errors, variables, timeout (line 38189)."

<details><summary>evidence</summary>

- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:33868-33871 (widget registration)
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:38184-38191 (SetVariableCtrl definition)
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:34499-34502 (input validation)
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:34487 (general cleanup transform)
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:25491-25493 (step variable generation)
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:1708-1710 (RESERVED_KEYWORDS constant)
- /Users/dylanspille/PycharmProjects/FSRPlaybookConversion/fsr-schema.ts:314-337 (inferred schema - cross-check)
- Editor differential: 'timeout' added to excludes in newer build (line 38189 vs 36607 in older app.beautified.js)

</details>

## FindRecords Step Type Schema Extraction

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `module` | string |  | True |  | Module path with optional query parameters. Format: <path>?$limit=<N>[&$relationships=true][&$fsr_max_relation_count=<N>]. Controller reconstructs this from params at line 36773. |
| `query` | object | {} | True |  | Query object containing filters, logic, sort, limit, and optionally __selectFields. Structure follows Query class definition. Initialized empty at line 36763, populated by UI. |
| `query.filters` | array | [] | True |  | Array of filter objects with field, operator, value. Matches inferred schema at fsr-schema.ts:348-366 |
| `query.limit` | number | 30 | True |  | Result limit. Controller extracts from module URL param at line 36810, defaults to 30 at line 36761 |
| `query.logic` | string | AND | True |  | Filter logic operator. Values: AND, OR. Inferred from schema line 368 |
| `query.sort` | array | [] | True |  | Array of sort objects with field and direction. Matches inferred schema line 369-374 |
| `query.__selectFields` | array |  | False |  | Array of field names to select. CONDITIONALLY PRESENT. Deleted by compile-time transform at line 34498 if checkboxFields is falsy. Set by controller at lines 36768-36769 when checkboxFields is true |
| `checkboxFields` | boolean | false | False |  | Controls whether __selectFields is persisted. When false, __selectFields is deleted at line 34498 before POST. Default false at line 36760 |

**Compile transforms:** Compile-time transform at line 34498: If stepType is 'FindRecords' and checkboxFields is falsy (false/undefined/0/''), then delete arguments.query.__selectFields. This mutation occurs before POST to the backend. Logic: \"FindRecords\" !== i.stepType.name \|\| i.arguments.checkboxFields \|\| delete i.arguments.query.__selectFields

<details><summary>evidence</summary>

- 800_app.beautified.js:36754-36818 (FindRecordsCtrl controller definition)
- 800_app.beautified.js:33848 (stepTypeWidget registration)
- 800_app.beautified.js:34498 (compile-time transform)
- 800_app.beautified.js:36758-36766 (params initialization with defaults)
- 800_app.beautified.js:36768-36769 (__selectFields assignment)
- 800_app.beautified.js:36773-36776 (module string reconstruction)
- 800_app.beautified.js:36806-36810 (module URL parameter parsing)
- fsr-schema.ts:345-395 (inferred FindRecordArgs for cross-check)

</details>

## ReferencePlaybook Step Type Schema Reverse Engineering

uuid `74932bdc-b8b6-4d24-88c4-1a4dfbc524f3` · editor: REFERENCE_STEP / WorkflowReference · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `workflowReference` | string |  | True |  | IRI of the referenced playbook (e.g., /api/3/workflows/{uuid}), or jinja expression string. Set by WorkflowReferenceCtrl at line 37197 from selected playbook @id. |
| `pass_parent_env` | boolean | false | False |  | Pass parent environment to referenced playbook. Initialized at line 37195; mutually exclusive with pass_input_record. Default injected when undefined. |
| `pass_input_record` | boolean | false | False |  | Pass input record to referenced playbook. Initialized at line 37195; mutually exclusive with pass_parent_env. Default injected when undefined. |
| `arguments` | object | {} | False |  | Map of parameter name → value to pass to the referenced playbook. Filtered by playbook.parameters list at line 37197-37199. Supports jinja expressions. |
| `apply_async` | boolean | false | False |  | Execute referenced playbook asynchronously. Present in 536/539 instances per inferred schema. When true, deletes for_each.break_loop at line 34489. Default false initialized at line 11607. |
| `for_each` | object |  | False |  | [system key] Loop structure with: condition (jinja), item (loop variable), __bulk (boolean), break_loop (string), parallel (boolean). Present in 153/539 instances. Deleted if item is empty at line 34487. |
| `do_until` | object |  | False |  | [system key] Retry loop: condition, delay (int, milliseconds), retries (int). Deleted if condition is empty at line 34487. |
| `ignore_errors` | boolean |  | False |  | [system key] Continue execution even if step fails. Deleted if false. Present in 21/539 instances. |
| `when` | string |  | False |  | [system key] Jinja condition to execute step. Deleted if empty at line 34487. Present in 47/539 instances. |
| `message` | object |  | False |  | [system key] Collaboration message with content, records, tags, tenant, thread, type, parentstepid. Deleted if content is empty at line 34487. Present in 7/539 instances. |
| `mock_result` | string |  | False |  | [system key] Mock result for testing. Deleted if empty at line 34487. Present in 2/539 instances. |
| `step_variables` | object |  | False |  | [system key] Not directly set by WorkflowReferenceCtrl; inherited from base step system. |

**Compile transforms:** Step compilation logic at line 34480-34608 (submitSelectedStep function): 1. At line 34487: Empty arguments are deleted before save:    - when: delete if empty string    - mock_result: delete if empty string    - do_until: delete if .condition is empty    - for_each: delete if .item is empty    - message: delete if .content is empty    - delay: set to 0 if undefined 2. At line 34489: If apply_async=true AND for_each exists, delete for_each.break_loop 3. At line 34498-34608: No special compile step for WorkflowReference/RemotePlaybookReference (case statement at line 34577-34584 just handles reference blocks, not workflow reference steps) 4. No argument deletion or transformation specific to WorkflowReference steps found; inherits system key cleanup patterns from base step handling.

<details><summary>evidence</summary>

- Line 646: PLAYBOOK_STEPS_UUID.REFERENCE_STEP = '74932bdc-b8b6-4d24-88c4-1a4dfbc524f3'
- Line 33862-33864: .stepTypeWidget('WorkflowReference', { templateUrl: 'playbookReference.html', controller: 'WorkflowReferenceCtrl' })
- Lines 37192-37202: WorkflowReferenceCtrl definition shows workflowReference, pass_parent_env, pass_input_record, arguments initialization
- Lines 37193-37200: $watch on playbook parameter handling; arguments filtered by playbook.parameters
- Line 34487-34489: Compile-time argument cleanup: delete empty when/mock_result/do_until/for_each/message; cleanup for_each.break_loop when apply_async=true
- Line 11607: apply_async default false initialization when showAsync is true
- Line 1709: cyops_playbook_iri, cyops_playbook_name listed as RESERVED_KEYWORDS.PLAYBOOKS (available as step variables, not arguments)
- Lines 33457, 33564: workflow_iri and workflowReference both recognized as playbook reference arguments in export/import
- Inferred schema (FSR-schema.ts lines 403-434): ReferencePlaybookArgs shows pass_parent_env in 469/539, pass_input_record in 497/539, apply_async in 536/539

</details>

## Extract and document the authoritative Wait step (Delay) argument schema from the FortiSOAR editor bundle

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `delay` | object | { days: 0, hours: 0, minutes: 0, seconds: 0 } | True |  | Time-based delay configuration. All time components support jinja expressions (string) or numeric values. Lines 36687-36730 show structure initialization. |
| `type` | string | TimeBased | False | TimeBased | Step delay mode. Defaults to 'TimeBased' at line 36721. Determines if delay is time-based (vs event-based via rule). Only 'TimeBased' observed in DelayCtrl. |
| `timeout` | object | null | False |  | Optional timeout configuration for approval/manual-input steps connected after this delay. Lines 36557-36565 show structure. Deleted if isTimeout is false (line 36561). |
| `for_each` | object | null | False |  | Optional loop configuration. System key visible in compile-time cleanup (line 34487). Structure: { item: string, condition: string, break_loop?: string } |
| `rule` | object | null | False |  | Optional event-based wait rule. Used for event-triggered resume instead of time-based delay. Structure visible in PauseUntilConditionCtrl (line 36553+). |
| `step_variables` | array | [] | False |  | System key for step-level variables. Not managed by DelayCtrl but present in compiled steps. |

**Compile transforms:** DelayCtrl initialization (lines 36716-36744): (1) delay defaults to { days:0, hours:0, minutes:0, seconds:0 } if missing. (2) type defaults to 'TimeBased'. (3) If type='TimeBased' AND (delay.weeks > 0 OR delay.days >= 7), delay normalized to { days:7, hours:0, minutes:0, seconds:0 } with 7-day max. (4) Jinja expressions detected via isJinjaConvertibleToTag for each time component (lines 36700-36709). Compile-time cleanup (lines 34487-34488): (5) Each delay property (days,hours,minutes,seconds) set to 0 if undefined. (6) for_each deleted if empty. (7) do_until deleted if condition empty. (8) timeout deleted if isTimeout=false (line 36561). (9) Timeout values capped: days<=7, hours<=168, minutes<=10080 (line 36633).

<details><summary>evidence</summary>

- 800_app.beautified.js:33908-33910 stepTypeWidget Delay with DelayCtrl
- 800_app.beautified.js:36684-36752 DelayCtrl full implementation
- 800_app.beautified.js:36716-36730 delay default structure initialization
- 800_app.beautified.js:36721 type defaults to TimeBased; delay.days capped at 7
- 800_app.beautified.js:36700-36709 jinja expression detection for time components
- 800_app.beautified.js:34487-34488 compile-time cleanup for delay properties
- 800_app.beautified.js:36557-36565 timeout argument structure
- 800_app.beautified.js:36582-36584 for_each default in PauseUntilConditionCtrl
- fsr-schema.ts:442-481 WaitArgs inferred interface
- fsr-schema.ts:82-89 Wait step registration uuid 6832e556-b9c7-497a-babe-feda3bd27dbf

</details>

## OnUpdate (post_update/pre_update) Step Type Arguments Schema

editor: POST_UPDATE_TRIGGER = 'cybersponse.post_update', PRE_UPDATE_TRIGGER = 'cybersponse.pre_update' (line 634-635) · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `resources` | array | [] | True |  | Array of module IRI/type strings that trigger the playbook. When any record of these modules is updated, the playbook is triggered. Line 23744, 23803, 23823. |
| `resource` | string | none | False |  | Deprecated single module type. Converted to resources array on init. Line 23754. |
| `displayConditions` | object | {} | False |  | Object keyed by module type, storing display conditions for fields per module. Structure: { [moduleType]: { visibility: string, conditions: object, filters: array } }. Auto-initialized by prepareResourceField. Line 23834, 38918. |
| `fieldbasedtrigger` | object | { filters: [], logic: 'AND' } | False |  | Filter-based trigger definition. Contains: filters (array of filter conditions), logic (string: 'AND' or 'OR'). Initialized in prepareResourceField. Line 23834-23836. |
| `__triggerLimit` | boolean | true for new triggers | False |  | Flag indicating whether trigger limit options (created vs replicated) are enabled. When undefined, defaults to true if triggerOnSource/triggerOnReplicate are undefined. Line 23726. |
| `triggerOnSource` | boolean | true | False |  | For post_update/pre_update only: trigger when record is created (source). Maps to 'created' option in UI. Line 23726, 23734. |
| `triggerOnReplicate` | boolean | false | False |  | For post_update/pre_update only: trigger when record is replicated. Maps to 'replicated' option in UI. Line 23726, 23734. |
| `step_variables` | object | undefined (set by compiler) | False |  | Auto-generated by editor during compilation. Input field is deleted on init (line 23725) and rebuilt by compiler to: { input: { records: ["{{vars.input.records[0]}}"] } }. Lines 23725, 34569-34571. |

**Compile transforms:** For POST_UPDATE_TRIGGER steps during save/compilation (line 34569-34571): 1. step_variables.input is SET TO: { records: ["{{vars.input.records[0]}}"] } 2. If step_variables object does not exist, it is created with the input field above 3. step_variables.input.params field is NOT added (unlike ACTION_TRIGGER which adds params from inputVariables) 4. Empty when/mock_result/do_until/for_each/message fields are deleted if falsy (line 34487)

<details><summary>evidence</summary>

- Line 634-635: PLAYBOOK_STEP_TYPES.POST_UPDATE_TRIGGER and PRE_UPDATE_TRIGGER constants
- Line 23703-23840: csTrigger directive definition with scope bindings and initialization logic
- Line 23711: arguments scope binding via ngModel
- Line 23725: step_variables.input deletion on init
- Line 23726-23734: __triggerLimit, triggerOnSource, triggerOnReplicate initialization and update logic
- Line 23728: allowIsChangedOperator check for post_update
- Line 23806: POST_UPDATE_TRIGGER special handling for relationship fields in resourceFields
- Line 23811-23821: POST_UPDATE_TRIGGER arrayOperators definition (multiselectpicklist, tags with in_all, in, addedvalueis)
- Line 23834-23837: prepareResourceField initialization of displayConditions and fieldbasedtrigger
- Line 34486-34571: Step save validation - POST_UPDATE_TRIGGER compile-time transformations
- Line 34569-34571: Compiler auto-generates step_variables.input with records array
- Line 1709: displayConditions listed in PLAYBOOKS constant as valid step argument
- Line 38918: displayConditions evaluated at runtime for visibility conditions

</details>

## Decision Step Type Schema Reverse-Engineering

editor: DECISION: "Decision" (line 621); stepTypeWidget("Decision", {...}) at line 33903; controller: "DecisionCtrl" at line 33905; templateUrl: "app/playbooks/designer/step-arguments/decision.html" at line 33904; size: "large" at line 33907 · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `conditions` | array | [] | True |  | Array of condition objects that define routing paths. Initialized as empty array if not present. Each element is an object with optional step_iri, condition, default, option, and step_name properties. Line 36545: i.config.arguments.conditions initialized as []; Line 36539-36541: addCondition pushes  |
| `conditions[n].step_iri` | string |  | False |  | IRI string pointing to target step. Before compile: local UUID format (e.g., 'workflow_steps/uuid-xyz'). After compile: full API URL (API_3_BASE + WORKFLOW_STEPS + uuid). Line 33442: step_iri transformed in loop to full URL; Line 34490: step_name added based on step_iri lookup during save |
| `conditions[n].condition` | string |  | False |  | Jinja expression that evaluates routing condition. Optional field. Lines 48770-48771, 48779-48780 show condition field being set with {{ }} Jinja expressions. Supports Jinja2 template syntax for dynamic decision logic |
| `conditions[n].default` | boolean | false | False |  | Marks this condition as the default path when no other conditions match. When set to true during addCondition. Line 36539-36540: push({default: true}); Line 36546: filter checks for true === e.default to determine if defaultStep flag set |
| `conditions[n].option` | string |  | False |  | Optional field, likely legacy or alternative naming. Present in inferred schema DecisionArgs but not explicitly set in DecisionCtrl. May be used for display or alternative routing logic |
| `conditions[n].step_name` | string | null | False |  | COMPILE-TIME GENERATED - Added during save/compile phase. Derived from step_iri lookup. Line 34490: step_name populated from playbook.steps lookup using getEndPathName filter on step_iri. Not user-editable in UI |
| `step_variables` | array |  | False |  | Optional array for step-scoped variables. Present in 154/311 Decision instances per inferred schema. Not explicitly managed by DecisionCtrl but available via step_variables mechanism used across steps. Type is unknown[] per schema |

**Compile transforms:** addCondition() pushes empty object {} or {default: true} to conditions array (lines 36539-36541). During save (line 34489-34490): for each condition, if step_iri exists and contains 'workflow_steps', populate step_name from playbook.steps[getEndPathName(step_iri)].name. During reference block compilation (line 33442): transform step_iri from local UUID format to full API URL: API_3_BASE + WORKFLOW_STEPS + s[getEndPathName(step_iri)]. Line 34545: excludes list shows excluded fields: ['condition', 'mock_result', 'ignore_errors', 'loops', 'variables', 'timeout'] - these are NOT part of arguments, they are step-level or meta-level controls

<details><summary>evidence</summary>

- Line 621: DECISION: 'Decision' constant
- Lines 33903-33907: stepTypeWidget configuration
- Lines 36530-36551: DecisionCtrl controller code
- Lines 36538-36549: addCondition, removeCondition, and initialization logic
- Lines 34489-34490: Compile-time step_name injection from step_iri
- Lines 33441-33442: Reference block step_iri transformation to API URL format
- Lines 48770-48771, 48779-48780: condition field usage with Jinja expressions
- /Users/dylanspille/PycharmProjects/FSRPlaybookConversion/fsr-schema.ts lines 506-515: DecisionArgs interface with inferred schema

</details>

## Reverse-engineer UtilityNoOp (utility step) argument schema from FortiSOAR editor bundle

editor: CyopsUtilites (step type widget name) → maps to ConnectorStepCtrl controller and connector.html template (line 33893-33896) · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `connector` | string |  | True |  | System key. Connector name/identifier. Set by ConnectorStepCtrl at line 37276. |
| `operation` | string |  | True |  | System key. Operation ID within connector. Set by ConnectorStepCtrl at line 37450. |
| `operationTitle` | string |  | True |  | Human-readable operation title. Set by ConnectorStepCtrl at line 37450 from operation.title. |
| `params` | object | {} | True |  | System key. Operation parameters. Initialized to {} and populated from operation metadata. Line 37450. |
| `version` | string |  | True |  | System key. Connector version. Set by ConnectorStepCtrl at line 37276. |
| `step_variables` | unknown |  | True |  | System key. Connector output schema mapping. Referenced at line 25501. |
| `config` | string |  | False |  | System key. Configuration ID (UUID). May be null if is_config_required=false. Line 37450. Empty string means null/undefined. |
| `name` | string |  | False |  | Step display name. Set by ConnectorStepCtrl at line 37276. Empty means not set. |
| `pickFromTenant` | boolean | false | False |  | Flag for dynamic tenant selection. Set by ConnectorStepCtrl at line 37276. |
| `agent` | string |  | False |  | Optional agent assignment for remote execution. Set by ConnectorStepCtrl at lines 37441-37443. |
| `annotation` | unknown |  | False |  | Connector annotation filter. Set by ConnectorStepCtrl at line 37276. |
| `dynamicallySelected` | boolean | false | False |  | Flag indicating dynamic agent/config selection. Set by ConnectorStepCtrl at line 37454. |
| `when` | string |  | False |  | Conditional execution Jinja expression. Present in ~40/442 instances (9%). Deleted if empty. Line 34487. |
| `for_each` | object |  | False |  | Loop execution config. Present in ~27/442 instances (6%). Shape: {condition?: string, item: string, __bulk?: boolean, parallel?: boolean, batch_size?: number}. Deleted if item is empty. Lines 11542, 11581, 34487. |
| `do_until` | object |  | False |  | Retry loop config. Present in ~2/442 instances (<1%). Shape: {condition: string, delay: number\|string, retries: number\|string}. Deleted if condition is empty. Line 34487. |
| `ignore_errors` | boolean | false | False |  | Suppress step failure errors. Present in ~17/442 instances (4%). Line 34487. |
| `message` | object |  | False |  | Logging/audit message. Present in ~5/442 instances (1%). Shape: {content: string, records: string, parentstepid?: string, tags?: string[], tenant?: string, thread?: boolean, type?: string}. Deleted if content is empty. Line 34487. |

**Compile transforms:** When step is saved (line 34487): - Empty when/do_until/for_each/message objects are deleted entirely - When string must be non-empty or key is deleted - do_until.condition must be non-empty or key is deleted   - for_each.item must be non-empty or key is deleted - message.content must be non-empty or key is deleted  For loop execution modes (line 11581): - __bulk mode: sets __bulk=true, deletes parallel, sets batch_size=(undefined ? 100 : existing) - sequential mode: sets parallel=false, __bulk=false, deletes batch_size - parallel mode: sets parallel=true, __bulk=false, deletes batch_size  Agent-based deletion (line 34487): - If agent is set AND for_each exists AND for_each.break_loop exists, break_loop is deleted  Bulk mode auto-defaults (line 11542): - If loopExecutionModes.bulk=true AND parallel is undefined AND __bulk is undefined → sets __bulk=true, batch_size=100 - Otherwise if parallel is undefined → sets parallel=false

<details><summary>evidence</summary>

- Lines 37273-37451: ConnectorStepCtrl full definition and argument handling
- Lines 33893-33896: stepTypeWidget registration of CyopsUtilites using ConnectorStepCtrl
- Lines 25496-25505: Dynamic value service treating CyopsUtilites same as Connectors
- Lines 37276: connector, name, version, pickFromTenant assignment
- Lines 37450: operation, operationTitle, params assignment
- Lines 11542, 11581: __bulk, batch_size compile-time defaults
- Lines 34487-34489: Empty argument cleanup and break_loop deletion on save
- Lines 1709: Reserved system argument keys including when, for_each, do_until, ignore_errors, message
- fsr-schema.ts lines 517-556: Inferred UtilityNoOpArgs cross-check (442 instances, 241 playbookCount)

</details>

## reverse-engineer-updaterecord-step

editor: UPDATE_DATA constant at line 627; stepType UUID: b593663d-7d13-40ce-a3a3-96dece928722 · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `collection` | string |  | True |  | Workflow collection IRI path; read from l.config.arguments at line 37015 |
| `collectionType` | string |  | True |  | Target module type IRI; used for schema lookup at line 25517; e.g. /api/3/modules/incidents |
| `resource` | object |  | True |  | Field update payload; accessed at line 37100 via l.config.arguments.resource; keys are field names, values are field values; supports __link for relationships |
| `operation` | enum | Append | False | Append,Overwrite | Field merge strategy; defaulted at line 37038; present in 328/334 instances; supports Jinja expressions |
| `fieldOperation` | object | {} | False |  | Per-field operation override; defaulted at line 37038; maps field names to Append/Overwrite; present in 319/334 instances; for_each removes entries for unsupported field types at line 37143 |
| `__recommend` | array |  | False |  | Recommended field names for UI highlighting; populated at lines 37047, 37056, 37145; present in 234/334 instances; array of field name strings |
| `_showJson` | boolean |  | False |  | UI state for JSON view toggle; set at line 37031; present in 222/334 instances; no compile-time effect |
| `for_each` | object |  | False |  | Bulk/loop execution; present in 47/334 instances; structure: { __bulk: boolean, condition: string, item: string, batch_size?: number, parallel?: boolean }; deleted if item is empty string at line 34487; batch_size enables bulk mode in for_each compilation |
| `ignore_errors` | boolean |  | False |  | Skip step error handling; present in 4/334 instances; standard system key |
| `when` | string |  | False |  | Jinja conditional for step execution; present in 59/334 instances; deleted if empty string at line 34487; supports full Jinja expressions |
| `message` | object |  | False |  | Step message config; present in 105/334 instances; deleted if content is empty string at line 34487; structure: { content: string, records: string, parentstepid?: string, tags?: array, tenant?: string, thread?: boolean, type?: string } |
| `tagsOperation` | string |  | False |  | Special operation mode for recordTags field; present in 33/334 instances; similar to operation but scoped to tags |
| `step_variables` | unknown |  | False |  | System key for step output definitions; accessed at line 37121; read-only to schema; schema varies per playbook context |

**Compile transforms:** Line 37038: operation defaults to 'Append'; fieldOperation defaults to {}. Line 34487-34489: for_each is deleted if undefined or if for_each.item is empty string. Line 34572-34573: If collection is COMMENTS type, resource.content is scanned for mentioned people and added as resource.peopleUpdated (boolean) and resource.people (array). Line 25517-25520: collectionType is split and resolved to fetch module schema; step outputs are formatted as array if for_each is present, otherwise single object.

<details><summary>evidence</summary>

- line 627: UPDATE_DATA constant
- lines 33840-33843: stepTypeWidget config
- lines 37015-37147: UpdateRecordCtrl function body
- line 37148: controller registration with $inject array
- lines 25515-25521: compile-time case handler
- lines 34572-34573: step save handler for UPDATE_DATA
- lines 34487-34489: cleanup logic for for_each
- lines 37038-37047: default injection and module change handler
- fsr-schema.ts lines 564-616: inferred schema for cross-check

</details>

## Reverse-engineer CreateRecord (InsertData) step type

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `collection` | string |  | True |  | Primary resource identifier. Line 36822: derived from selectedModule. Conditionally prepends 'upsert/' based on __replace state. Can contain 'ingest-feeds' path. No jinja in editor. |
| `resource` | object | {} | True |  | Form field values + meta keys __replace (string), __fieldsToUpdate (array, optional), __link (relationship mapping). Line 36906: __replace recalculated on save. Supports jinja in field values. |
| `operation` | string | Overwrite | False | Overwrite,Append | Relationship operation mode. Line 36841: Defaults to 'Overwrite'. Line 36904: Determines __link merge strategy. |
| `fieldOperation` | object | {} | False |  | Maps field names to 'Overwrite'\|'Append'. Line 36841: Defaults to {}. Line 36992: Per-field defaults to 'Overwrite'. Specific to multiselectpicklist/recordTags. |
| `__recommend` | array | [] | False |  | Recommended field names. Lines 36945, 36954: Populated from module schema. Line 36994: Managed via changeRecommendation(). |
| `_showJson` | boolean | false | False |  | UI state: JSON view (true) vs form (false). Line 36838: Set by showJsonView(). Line 36988: Persisted via p variable. |
| `collectionType` | string |  | False |  | Module type IRI for comparison logic. Line 36945: Read for change detection, NOT set by controller. |
| `for_each` | object |  | False |  | Bulk config: {item, condition, __bulk?, batch_size?, parallel?}. Line 25512: Checked in output generation. Line 37006: Shown in IngestBulkFeedCtrl default. |

**Compile transforms:** Line 36841: Sets operation='Overwrite' and fieldOperation={} if undefined. Line 36822: Prepends 'upsert/' to collection if dataConfig.__replace !== 0. Line 36877-36879: Conditionally deletes/sets resource.__fieldsToUpdate based on __replace value. Line 36906: Recalculates resource.__replace via m() function mapping (0/1/2/3 -> '', 'false', 'true'). Line 25512: Output generation checks for_each to return array or single object.

<details><summary>evidence</summary>

- Line 33876-33880: stepTypeWidget registration for InsertData
- Line 36820-36997: InsertDataCtrl definition and registration
- Line 36841: Default initialization block
- Line 36822: Collection path modification
- Line 36877-36879: __fieldsToUpdate conditional logic
- Line 36906: resource.__replace recalculation
- Line 25507-25514: InsertData compile case statement
- Line 36929-36934: Relationship __link handling functions

</details>

## ManualStart (ACTION_TRIGGER) Step Type Schema

uuid `f414d039-bb0d-4e59-9c39-a8f1e880b18a` · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `inputVariables` | array | [] | True |  | Array of input variable definitions. Each variable can have name, type, formType, label, defaultValue, required, and many other UI/validation properties. Stored in the step arguments; compiled into step_variables.input at save time. |
| `resources` | array | [] | True |  | Array of module/collection IRIs that define which entities this manual start action can be triggered on. Empty array means 'no record execution' mode. |
| `step_variables` | object | {} | True |  | Object containing step output variables. Compiler auto-populates step_variables.input with params (mapped from inputVariables) and records='{{vars.input.records}}' |
| `route` | string | UUID.generate() if not present | False |  | Unique route identifier for this action trigger. Generated at init if not set. Format: UUID or API path string. |
| `executeButtonText` | string | instantTranslate('COMPONENTS.GRID.EXECUTE') | False |  | Button label shown to users executing this action. Gets translated at UI init; stored as key, not translated value. |
| `displayConditions` | object | {} | False |  | Maps module/collection names to visibility conditions. Each collection can have filters, logic, limit, sort arrays defining when the action is shown. Keys are collection/module names. |
| `showToasterMessage` | object | { visible: false, messageVisible: true } | False |  | Configuration for optional success message shown after execution. Keys: visible (boolean), message (string), messageVisible (boolean). |
| `__triggerLimit` | boolean | true | False |  | Controls trigger replication behavior. When true, uses triggerOnSource/triggerOnReplicate. When false, triggers on both. |
| `triggerOnSource` | boolean | true | False |  | Whether to trigger when record created on source. Only applies if __triggerLimit=true. |
| `triggerOnReplicate` | boolean | false | False |  | Whether to trigger when record replicated. Only applies if __triggerLimit=true. |
| `singleRecordExecution` | boolean | false (derived from UI) | False |  | If true, playbook runs once per record. If false, runs once on all records. Derived from runInnerSelection UI field ('single' vs 'all'). |
| `noRecordExecution` | boolean | false | False |  | If true, playbook can run without records. Overrides singleRecordExecution. Set when runSelection value is 'none'. |
| `title` | string | step.name (fallback) | False |  | Display title for this action trigger. Used in execution logs and action menus. Falls back to step name if not set. |
| `_promptexpanded` | boolean | false | False |  | UI-only state flag. Tracks whether the input variables prompt section is expanded in the editor. Not sent to server. |

**Compile transforms:** ACTION_TRIGGER compile-time transforms (lines 34487-34607): 1. Delete empty optional fields: when, mock_result, do_until.condition, for_each.item, message.content 2. Pre-compile cleanup (line 23725): Delete step_variables.input (compiler rebuilds it) 3. ACTION_TRIGGER specific (lines 34560-34564):    - For each inputVariable with name, add params[name]='{{vars.request.data["name"]}}'    - Set records='{{vars.input.records}}'    - Assign to step_variables.input 4. Trigger limit init (line 23726): If __triggerLimit undefined, set true; if true, default triggerOnSource=true, triggerOnReplicate=false

<details><summary>evidence</summary>

- 800_app.beautified.js:23703-23842 - csTrigger directive
- 800_app.beautified.js:23782-23794 - ACTION_TRIGGER init
- 800_app.beautified.js:34560-34564 - compile transform
- 800_app.beautified.js:23725-23787 - defaults/validation
- fsr-schema.ts:136-143 - ManualStart classification
- fsr-schema.ts:674-948 - ManualStartArgs inferred schema

</details>

## Reverse-engineer FortiSOAR OnCreate step type schema from editor bundle

editor: ea155646-3821-4542-9702-b246da430a8d (OnCreate/POST_CREATE_TRIGGER at lines 632, 48761) · confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `fieldbasedtrigger` | object |  | True |  | System key. Query object with filter criteria for record creation trigger. Structure: {filters: [], logic: 'AND'\|'OR'}. Each filter has: field (string), operator (string), value (unknown), _value (unknown). Initialized at line 23834-23836 as {filters: [], logic: 'AND'}. Set directly from r.query at |
| `resource` | string |  | True |  | System key. The module/resource type this trigger applies to. Set at line 48768. Example: 'incidents', 'alerts', etc. |
| `step_variables` | object |  | True |  | System key. Contains runtime variables for the step. Compile transform at lines 34569-34571 sets input property: {records: ['{{vars.input.records[0]}}'] }. Can be empty object initially, populated at compile time. |
| `__triggerLimit` | boolean | true | False |  | System key. Controls trigger behavior on replicated records. If undefined or missing, editor initializes to true (line 23726). When true: triggerOnSource=true, triggerOnReplicate=false. When false: triggerOnSource=true, triggerOnReplicate=true. |
| `resources` | array |  | False |  | System key. Array of resource types. Present in 34/36 instances per inferred schema. Gets populated/filtered at lines 23743-23750. Replaces singular 'resource' key in modern usage. |
| `triggerOnSource` | boolean | true | False |  | System key. When true, trigger fires on source (original) record creation. Set based on __triggerLimit at line 23726. Updated at line 23734 based on triggerLimitOptions selection. |
| `triggerOnReplicate` | boolean | false | False |  | System key. When true, trigger fires on replicated record creation. Set based on __triggerLimit at line 23726. Updated at line 23734 based on triggerLimitOptions selection. |

**Compile transforms:** At compile time (lines 34566-34572): For POST_CREATE_TRIGGER, editor injects step_variables.input = {records: ['{{vars.input.records[0]}}'] } before POST. This wraps the input record in an array. No other compile-time mutations found for OnCreate arguments beyond this input variable injection.

<details><summary>evidence</summary>

- Line 48761: OnCreate step type UUID assignment and fieldbasedtrigger initialization: t.stepType = '/api/3/workflow_step_types/ea155646-3821-4542-9702-b246da430a8d', t.arguments.fieldbasedtrigger = r.query
- Line 48768: resource assignment: t.arguments.resource = n
- Lines 23726-23734: __triggerLimit, triggerOnSource, triggerOnReplicate initialization in csTrigger directive
- Lines 23834-23836: fieldbasedtrigger default structure initialization with filters and logic
- Lines 34569-34571: step_variables.input compile transform for POST_CREATE_TRIGGER
- Lines 23744-23750: resources array filtering and validation
- Line 23754: resource to resources conversion: o.arguments.resources = [o.arguments.resource]
- Lines 33947-33948: stepTypeWidget registration for 'cybersponse.post_create' using trigger.html template
- Line 1709: displayConditions listed as reserved keyword (present in ACTION_TRIGGER but not confirmed in OnCreate arguments)
- Schema file /Users/dylanspille/PycharmProjects/FSRPlaybookConversion/fsr-schema.ts lines 145-152, 957-965: Inferred OnCreateArgs type confirming fieldbasedtrigger, resource, step_variables as system keys

</details>

## Reverse-engineer IngestBulkFeed step schema from FortiSOAR playbook editor

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `step_type` | string | IngestBulkFeed | True |  |  |
| `uuid` | string | 7b221880-716b-4726-a2ca-5e568d330b3e | True |  |  |
| `collection` | string | /api/ingest-feeds/{moduleName} | True |  | Auto-calculated via $watch at line 37009-37010. Format enforced by editor, cannot be manually set by user. |
| `resource` | object | {} | True |  | Field mappings (Record<string, unknown>). Inherited from InsertDataCtrl (line 37000). Contains field values and __replace key. |
| `step_variables` | array | [] | True |  | System key. Tracks variable state during execution. Inherited from parent controller. |
| `for_each` | object | {item:"",condition:""} | False |  | Loop configuration initialized at line 37006-37008. Compile-time: deleted if for_each.item is empty (line 34487). |
| `for_each.item` | string |  | True |  | Jinja-expression or array reference. If empty string at save, entire for_each deleted. Supports jinja (line 11536). |
| `for_each.condition` | string |  | False |  | Optional loop condition. Supports jinja expressions (line 11536 converts empty to literal, non-empty to jinja). |
| `for_each.__bulk` | boolean | true | False |  | Compile-time: set to true by line 11542 if bulk mode and no parallel/__bulk defined. IngestBulkFeed.loopExecutionModes.bulk=true (line 37003). |
| `for_each.batch_size` | number | 100 | False |  | Compile-time: set to 100 by line 11542 when __bulk=true. Deleted for sequential/parallel modes (line 11581). |
| `for_each.parallel` | boolean | false | False |  | Deleted when __bulk=true (line 11581). False for sequential, true for parallel mode. Mutually exclusive with __bulk. |
| `for_each.break_loop` | string |  | False |  | Optional loop break condition. Deleted: (1) if agent mode on (line 34487), (2) if apply_async=false (line 34489). Supports jinja. |
| `__recommend` | array | [] | False |  | Optional field recommendation list. Auto-deleted on collection watcher (line 37010). Present in 9/10 inferred instances. |
| `_showJson` | boolean | false | False |  | UI state: tracks if JSON view is shown (line 36838: 'l.config.arguments._showJson = l.showJson'). Present in 4/10 inferred instances. |
| `when` | string |  | False |  | Optional step condition. Deleted if empty at save (line 34487). System key. Present in 2/10 inferred instances. |
| `fieldOperation` | deleted |  | False |  | REMOVED: Explicitly deleted at line 37011. Unlike CreateRecord, IngestBulkFeed does not support field-level operations. |
| `operation` | deleted |  | False |  | REMOVED: Explicitly deleted at line 37011. CreateRecord defaults to 'Overwrite', but IngestBulkFeed removes it entirely. |

**Compile transforms:** For-each deletion validation (line 34487): DELETE for_each if for_each.item === ''. Ensures loop only exists with a defined iteration variable.\n\nBulk mode initialization (line 11542): IF loopExecutionModes.bulk=true AND for_each.parallel=undefined AND for_each.__bulk=undefined, THEN set __bulk=true and batch_size=100. IngestBulkFeed has bulk=true, so this always applies on first-time for_each creation.\n\nExecution mode transforms (line 11581): Mutually exclusive mode logic:\n- '__bulk' mode: __bulk=true, delete parallel, batch_size=100 (or keep if set)\n- 'sequential' mode: parallel=false, __bulk=false, delete batch_size\n- 'parallel' mode: parallel=true, __bulk=false, delete batch_size\n\nBatch size enforcement (line 11599): If __bulk=true and batch_size undefined, set to 100.\n\nBreak-loop conditional deletion (lines 34487, 34489):\n- IF agent mode ON: delete for_each.break_loop\n- IF apply_async=false: delete for_each.break_loop\n\nEmpty field cleanup (line 34487): DELETE when if empty string."

<details><summary>evidence</summary>

- Bundle: /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js
- Widget registration line 33881: stepTypeWidget('IngestBulkFeed', {templateUrl:'insertData.html', controller:'IngestBulkFeedCtrl'})
- Controller line 37013: angular.module('cybersponse').controller('IngestBulkFeedCtrl', e), e.$inject=['$scope','$controller','$filter']
- Implementation lines 36999-37012: IngestBulkFeedCtrl inherits InsertDataCtrl, sets loopExecutionModes, initializes for_each, sets collection, deletes operation/fieldOperation
- Collection watcher lines 37009-37010: enforces /api/ingest-feeds/ + module name format
- For-each init lines 37006-37008: {item:'', condition:''}
- Loop modes lines 37002-37005: bulk=true, parallel=false, sequential=false
- Field deletion line 37011: delete fieldOperation and operation
- For-each validation line 34487: deletes for_each if item is empty
- Bulk defaults line 11542: sets __bulk=true, batch_size=100 for bulk mode
- Batch enforcement line 11599: ensures batch_size=100 if __bulk=true
- Mode transforms line 11581: __bulk/__parallel/sequential logic
- Break-loop deletion line 34487 (agent) and 34489 (apply_async)
- Schema cross-check: /Users/dylanspille/PycharmProjects/FSRPlaybookConversion/fsr-schema.ts lines 154-161, 973-987

</details>

## SendEmail Step Arguments

confidence **medium**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `to` | array(string) | [] | False |  | Email recipient addresses. Converted from/to jinja tags format via convertVarsToTag/convertTagsToVar filters. In editor, joined with commas for display (line 38148). |
| `from_str` | string | SMTP defaultFrom or DEFAULT_FROM_EMAIL | True |  | Sender email address. Defaults to SMTP settings defaultFrom or DEFAULT_FROM_EMAIL injection (line 38148). System key per inferred schema. |
| `content` | string | "" | False |  | Email body content. Handled via richtext editor with Field({name: 'content', formType: 'richtext', title: 'Content'}). Set via getMarkDown callback (line 38166). |
| `cc` | array(string) | null | False |  | Carbon copy recipients. Not directly exposed in SendEmailCtrl in bundle; present in inferred params schema at line 1030 as optional cc_recipients field. Possible implementation gap or hidden in template. |
| `bcc` | array(string) | null | False |  | Blind carbon copy recipients. Not directly exposed in SendEmailCtrl; present in inferred params schema line 1026 as optional bcc_recipients field. Possible implementation gap. |
| `subject` | string | null | False |  | Email subject line. Not exposed in SendEmailCtrl controller; present in inferred schema params (line 1025) as required iri_list+subject. Possible implementation gap or stored differently. |
| `attachments` | array | null | False |  | Email attachments. Not exposed in SendEmailCtrl; could be in params per inferred schema. Form handling not visible in bundle. |
| `timeout` | object | null | False |  | Excluded from arguments via excludes=['timeout'] (line 38148). Not permitted for SendEmail steps. |
| `config` | string | null | True |  | System key (inferred schema line 996). Likely SMTP configuration ID. |
| `connector` | string | null | True |  | System key (inferred schema line 997). Likely 'SMTP' or similar. |
| `version` | string | null | True |  | System key (inferred schema line 1004). Connector version identifier. |
| `step_variables` | unknown | [] | True |  | System key (inferred schema line 999-1003). Output/step variables. Can be array or object with various keys like my_var1, connector_name. |
| `operation` | string | null | False |  | Optional system key. Present in 19/20 instances per inferred schema. Likely SMTP operation identifier. |
| `operationTitle` | string | null | False |  | Optional. Present in 19/20 instances (inferred schema line 1022). Display title for the operation. |
| `params` | object | null | False |  | Optional system key. Present in 19/20 instances (inferred schema line 1023-1039). Contains iri_list, subject, bcc, bcc_recipients, body, body_type, cc, cc_recipients, content, file_name, file_path, from, to, to_recipients, type. MISMATCH: Not accessed in SendEmailCtrl bundle code; unclear how editor |
| `when` | string | null | False |  | Execution condition. Optional (inferred schema line 1040). Present in 5/20 instances. Deleted at compile-time if empty (line 34487). |
| `for_each` | object | null | False |  | Loop iteration. Optional system key. If set with __bulk=true, batch_size defaults to 100 (line 11542). Deleted if item is empty at compile-time (line 34487). |
| `ignore_errors` | boolean | null | False |  | Optional system key (inferred schema line 1011). Error handling flag. |
| `message` | object | null | False |  | Optional system key (inferred schema line 1012-1019). Deleted if content is empty at compile-time (line 34487). |
| `mock_result` | string | null | False |  | Optional (inferred schema line 1020). Deleted if empty at compile-time (line 34487). |

**Compile transforms:** 1. **Empty field deletion** (line 34487): Delete `when`, `mock_result`, `do_until`, `for_each`, `message` if undefined or empty. 2. **Tag conversion** (line 38148): Convert `to` field from/to jinja tags format using convertVarsToTag/convertTagsToVar filters. 3. **Default from address** (line 38148): If `to` is undefined/empty, set `from_str` to SMTP defaultFrom or DEFAULT_FROM_EMAIL constant. 4. **Bulk loop defaults** (line 11542): If for_each is set to bulk mode and __bulk/__parallel undefined, set `__bulk=true` and `batch_size=100`. 5. **Break-loop cleanup** (line 34487): Delete `for_each.break_loop` if agent is set and break_loop exists. 6. **Delay normalization** (line 34488): Zero undefined/empty values in delay array. 7. **Format conversion** (line 36567-36582): RichText content via Field object with formType='richtext'. ContentTypes enum: [{name: 'Plain Text', type: 'text/plain'}, {name: 'HTML', type: 'text/html'}].

<details><summary>evidence</summary>

- Line 33885: Step widget registration
- Line 38147-38169: SendEmailCtrl complete definition
- Line 34480-34608: Step save/compile logic and argument transformation
- Line 11542: Bulk loop default setting
- Line 34487-34492: Compile-time field deletion conditions
- fsr-schema.ts lines 163-170: SendEmail classification
- fsr-schema.ts lines 995-1041: Inferred SendEmailArgs schema
- Line 36567-36582: RichText field and content type definitions
- Line 17232-17251: convertTagsToVar and convertVarsToTag filter definitions

</details>

## reverse-engineer-manualinput-step

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `type` | enum |  | True | InputBased | Always 'InputBased' for ManualInput steps (set at line 37898 in editor). ManualInput and ApprovalManualInput both use this step type with different is_approval flags. |
| `input` | object | {"schema":{"title":null,"description":null,"inputVariables":[]}} | True |  | Schema object containing the input form definition. Initialized at line 37898-37903. |
| `response_mapping` | object | {"options":[],"connecteStepsLength":0,"customSuccessMessage":"Awaiting Playbook resumed successfully."} | True |  | Maps response options to next steps. Initialized at line 37925-37927. connecteStepsLength is DELETED before POST (line 34525). |
| `owner_detail` | object | {"isAssigned":false,"assignedToField":null,"assignedToPerson":[]} | True |  | Specifies who receives the manual input request. Initialized at line 37920-37923. |
| `record` | string | {{ vars.input.records[0]["@id"] }} | True |  | IRI/reference to the record being worked on. Set at line 38012 with jinja expression support. |
| `resources` | string |  | False |  | Module/resource type for record context (line 38012, 38014-38015) |
| `step_variables` | object\|array |  | True |  | System key for storing output variables. Initialized per step but NOT modified for ManualInput during compile (unlike triggers at line 34553-34571). |
| `is_approval` | boolean | false | False |  | Set to true for ApprovalManualInput variant (line 38012). Controls approval-style options (Approve/Reject). |
| `unauthenticated_input` | boolean | false | False |  | Allows external/unauthenticated users to respond. Initialized at line 37898. When true, triggers agent mode logic at line 37915. |
| `external_channel_list` | array | [] | False |  | List of external communication channel IRIs (e.g., Email, Slack). Initialized at line 37898. Validated at line 34534 when unauthenticated_input=true. |
| `inline_channel_list` | array | [] | False |  | List of internal communication channel IRIs. Initialized at line 37898. Validated at line 34534 when unauthenticated_input=true. |
| `inputExternalUser` | boolean |  | False |  | Allow external users to respond. Validated/cleaned at line 34540. |
| `inputInternalUsers` | boolean |  | False |  | Allow internal users to respond. Validated/cleaned at line 34540. |
| `agent_id` | string\|null | null | False |  | Agent for external communication (line 37898). Set to null at line 34540 if Slack channel + agent_id conflict. Logic at line 37784-37788. |
| `email_notification` | object | {"enabled":false,"smtpParameters":{}} | False |  | Email notification settings. Initialized at line 37920-37921. |
| `external_email_subject` | string\|null | A FortiSOAR playbook is requesting your input | False |  | Subject for external user emails. Set at line 37790 or line 37807-37808. |
| `internal_email_subject` | string\|null | A FortiSOAR playbook is requesting your input | False |  | Subject for internal user emails. Set at line 37790 or line 37806. |
| `custom_email_body_external` | string\|null | null | False |  | Custom HTML body for external emails. Initialized/managed at line 37790, 37807-37808. |
| `custom_email_body_internal` | string\|null | null | False |  | Custom HTML body for internal emails. Initialized/managed at line 37790, 37806. |
| `external_email_attachments` | array\|null | null | False |  | Attachments for external emails. Managed at line 37790, 37807-37808. |
| `internal_email_attachments` | array\|null | null | False |  | Attachments for internal emails. Managed at line 37790, 37806. |
| `customEmailExternal` | boolean | false | False |  | Enable custom email body for external users. Logic at line 37789-37791, 37807-37808. |
| `customEmailInternal` | boolean | false | False |  | Enable custom email body for internal users. Logic at line 37805-37806. |
| `isRecordLinked` | boolean | true | False |  | Track whether step is linked to a record context. Logic at line 38012. When false, disables unauthenticated mode. |
| `timeout` | object |  | False |  | Timeout configuration for awaiting response. Validated at line 37947-37951 (max 7 days, 168 hours, 10080 minutes). |
| `message` | object |  | False |  | Message/logging metadata (system key). Not usually set for ManualInput. |

**Compile transforms:** Line 34525: delete i.arguments.response_mapping.connecteStepsLength — connecteStepsLength is an editor-only tracking key for counting connected downstream steps; removed during compile before POST. Line 34514: Similar pattern for ManualDecision, but different structure. Line 34540-34544: Cleanup transforms — if inputExternalUser=false, clear external_channel_list and emailRecipients; if inputInternalUsers=false, clear inline_channel_list and externalRecipients; if agent_id is set and Slack channel exists, remove Slack channel. Line 34533-34535: When unauthenticated_input=true, force owner_detail fields to null/empty/false. Line 37898-37927: Default initialization sets type='InputBased', empty input.schema, empty response_mapping options, null/empty owner_detail, and hardcoded success message.

<details><summary>evidence</summary>

- 800_app.beautified.js:34516-34546 (MANUAL_INPUT validation case)
- 800_app.beautified.js:34525 (connecteStepsLength deletion)
- 800_app.beautified.js:34534-34544 (unauthenticated_input and channel cleanup)
- 800_app.beautified.js:37750-38024 (ManualInputCtrl initialization and event handlers)
- 800_app.beautified.js:37898-37927 (argument defaults)
- 800_app.beautified.js:37947-37951 (timeout validation)
- 800_app.beautified.js:38012-38022 (record and ownership logic)
- fsr-schema.ts:1049-1123 (inferred ManualInputArgs cross-reference)

</details>

## reverse-engineer-approval-step-type

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `step_type_name` | string | Approval |  |  | Editor registers widget 'Approval' at line 33911 of bundle |
| `step_type_uuid` | iri | /api/3/workflow_step_types/a19333c2-c822-11ed-afa1-0242ac120002 |  |  | APPROVAL_STEP_TYPE constant defined at line 618; appears in compile transforms at line 33447 |
| `arguments.collection` | enum | approvals | False | approvals | Set by ApprovalStepCtrl at line 37501; hardcoded enum value 'approvals' |
| `arguments.resource` | object | {} | True |  | Initialized at line 37507; contains approvals entity fields. ApprovalStepCtrl populates: playbookiri, playbookuuid, playbookname (lines 37513), assignedTo, owners, userOwners (line 37497), approvaldescription (line 37517), status (line 37561). Validation at line 34548 requires assignedTo non-empty O |
| `arguments.resource.playbookiri` | string | api/3/workflows/{playbook.id} | False |  | Set at line 37513 with pattern 'api/3/workflows/{id}' |
| `arguments.resource.playbookuuid` | string |  | False |  | Set at line 37513 to playbook UUID |
| `arguments.resource.playbookname` | string |  | False |  | Set at line 37513 from getEditingPlaybook().name |
| `arguments.resource.assignedTo` | string |  | False |  | IRI to person/@id. Either this or owners.length >= 1 required (validation at line 34548). Set by addPeople() at line 37497; line 37519-37523 loads person details via Modules.get API |
| `arguments.resource.owners` | array | [] | False |  | Array of team/@id IRIs. Either assignedTo OR owners.length >= 1 required. Set at line 37497; line 37527-37531 loads team details via Modules.get API |
| `arguments.resource.userOwners` | array |  | False |  | Array of user/@id IRIs; set at line 37497 when User type selected; omitted if Team type selected |
| `arguments.resource.approvaldescription` | string |  | False |  | Set from arguments.message at line 37517 (backward compat); supports jinja expressions per line 37480 isJinjaConvertibleToTag check |
| `arguments.resource.status` | object | Pending picklist object | False |  | Set at line 37561-37563 to the 'Pending' status picklist option from approvals entity; contains itemValue='Pending' |
| `arguments.approvers` | array |  | False |  | LEGACY/BACKWARD-COMPAT - old format; array at line 37513; parsed and deleted after converting to resource.assignedTo/resource.owners; contains {type:'User'\|'Team', '@id':..., ...} |
| `arguments.message` | string |  | False |  | LEGACY/BACKWARD-COMPAT - old format at line 37517; moved to arguments.resource.approvaldescription, then deleted |
| `arguments.response_mapping` | object |  | False |  | Optional; used in compile transforms at line 33448. If present contains 'options' array with step_iri values transformed to full API paths |
| `arguments.response_mapping.options` | array |  | False |  | Each object has: option (string), step_iri (relative path, transformed), primary (boolean) |
| `arguments.response_mapping.options[].step_iri` | string |  | False |  | Relative workflow step path like 'workflow_steps/uuid'; transformed at compile time to '/api/3/workflow_steps/{uuid}' |
| `arguments.timeout` | object |  | False |  | Optional timeout config; if present has: days, hours, minutes, step_iri |
| `arguments.timeout.step_iri` | string |  | False |  | Relative workflow step path for timeout target |

**Compile transforms:** RESPONSE_MAPPING (line 33448): Each option's step_iri transformed from relative to full API path: 'workflow_steps/abc123' becomes '/api/3/workflow_steps/abc123' \| TIMEOUT (line 33449): If timeout.step_iri exists, transforms to full API path \| BACKWARD_COMPAT_APPROVERS (line 37513): Legacy approvers array parsed (filtering by type User/Team) and deleted after migration to resource.assignedTo/resource.owners \| BACKWARD_COMPAT_MESSAGE (line 37517): Legacy message field moved to resource.approvaldescription, then deleted

<details><summary>evidence</summary>

- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:618
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:33911-33914
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:33447-33449
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:34547-34551
- /private/tmp/claude-501/-Users-dylanspille-PycharmProjects-pyfsr/3cd13171-5e17-4044-b46c-18bf50474813/scratchpad/800_app.beautified.js:37478-37565

</details>

## CreateTask Step Type (UUID: dc6ac63d-c5a5-472f-9eb4-6b18473a98b8)

confidence **medium**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `collection` | string | tasks | True |  | Hardcoded by editor at line 37569 (ManualTaskCtrl). Always 'tasks' collection. |
| `resource` | object |  | True |  | Task record fields. Editor loads fields dynamically from Entity('tasks') at line 37577. Structure determined by tasks module schema at runtime. |
| `resource.name` | string |  | True |  | Task name. Present in all 6 observed instances (line 37569-37576 shows field iteration). |
| `resource.status` | string \| object |  | True |  | Task status. Can be IRI string or picklist object. Present in all examples. E.g., '/api/3/picklists/959021fc-c19d-4aee-8e51-5395c5029719' or {id, @id, @type, color, display, ...} |
| `resource.priority` | string \| object |  | True |  | Task priority. Can be IRI string or picklist object. Present in all examples. E.g., '/api/3/picklists/90088ebe-0a7d-4aa6-9c9c-93b937a4e4f8' or {id, @id, @type, color, display, ...} |
| `resource.incidents` | string \| null |  | False |  | Incident reference (IRI or jinja). Optional. E.g., '{{vars.input.params['incident_iri']}}' or '/api/3/incidents/...' or null |
| `resource.assignedToPerson` | string \| object \| null |  | False |  | Person to assign task to. Can be IRI string, person object with {id, @id, @type, email, firstname, lastname, ...}, or null. Optional in observed instances. |
| `resource.description` | string |  | False |  | Task description. Optional HTML content. Present in 2/6 observed instances. E.g., '<p>Following are asset details</p>...' |
| `resource.[task_field_name]` | unknown |  | False |  | Other optional task module fields (taskdata, tasktype, owners, persons, recordTags, startDate, dueBy, notes, etc.). Envelope passes through any field present in tasks module schema. See fsr-schema.ts lines 1243-1288 for full list. |
| `step_variables` | array | [] | False |  | System key. Empty array in all observed instances. Line 37569 (excludes list) shows system-level fields are managed by framework, not user-editable. |
| `message` | object |  | False |  | Optional system key. Present in 3/6 instances per schema. Contains {content: string, records: string, tenant: string, parentstepid?: string}. Managed by framework for task notifications. |

**Compile transforms:** Line 37569 (ManualTaskCtrl init): Editor sets `a.config.arguments.collection = "tasks"` unconditionally.   Lines 37570-37576 (_updateResource function): Editor builds resource object by iterating task module form fields. For each field: - Skip undefined or empty values - For lookup/picklist types: extract @id, store as IRI string - For multiselectpicklist: extract @id array   - For other types: store as-is - Result stored in `a.config.arguments.resource`  No post-compile transforms detected for CreateTask (unlike ManualDecision which stringifies taskdata at line 34514, or ManualInput which validates response_mapping). Resource object is passed as-is to API POST.

<details><summary>evidence</summary>

- Bundle line 37569: ManualTaskCtrl controller (handles 'tasks' collection)
- Bundle line 37577: Entity('tasks') load triggers dynamic field discovery
- Playbook examples: 6 CreateTask instances with consistent {collection, resource, step_variables} envelope
- fsr-schema.ts lines 1187-1298: CreateTaskArgs interface (inferred from playbooks)
- Bundle line 33919: ManualTask stepTypeWidget registration (but CreateTask doesn't have explicit registration, suggesting it may use generic/fallback handler or encoder maps it at load time)
- Bundle line 36520: Default widget fallback for unregistered step types (empty template)

</details>

## APIEndpoint Step Type Arguments (UUID: df26c7a2-4166-4ca5-91e5-548e24c01b5f)

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `authentication_methods` | array | [] | True | ,Basic,anonymous | Array of authentication method values. Editor reads from authSelection and constructs this array. Line 23778-23779: editor finds matching authOption based on this value. |
| `route` | string | UUID (generated) | True |  | API endpoint route. For APIEndpoint (this UUID), route is PRESERVED during export (not regenerated). For other step types with route, it IS regenerated. Line 33438: route regeneration conditional on UUID. Line 23780: route may be prefixed with 'deferred/' based on authentication method. |
| `resources` | array | [] | False |  | Array of module IRIs (entity types). Line 23754: if arguments.resource exists, converted to resources array. Line 23784, 23787: initialization in ACTION_TRIGGER case (applies to all triggers). Line 23744-23750: intersection/difference checking for valid modules. |
| `displayConditions` | object | {} | False |  | Field-based display conditions object. Line 23787: displayConditionsExpanded calculated from this. Line 23834: initialized as empty object on parent scope. |
| `inputVariables` | array | [] | False |  | Array of input variable definitions. Line 23784: initialized with default empty array. Line 23830: used for input focus handling with _expanded property on items. |
| `noRecordExecution` | boolean | false | False |  | Whether trigger can run without record input. Line 23787: derived from runSelection value. Line 23797: set when runSelection is 'none'. For API_TRIGGER, prevents record requirement. |
| `singleRecordExecution` | boolean | false | False |  | Whether trigger runs once per record vs. all records at once. Line 23787: derived from runInnerSelection value. Line 23797: set when runInnerSelection is 'single' and runSelection is not 'none'. |
| `executeButtonText` | string | COMPONENTS.GRID.EXECUTE | False |  | Button text for manual action triggers. Line 23784: instantTranslate applied with default value. |
| `showToasterMessage` | object | {visible:false,messageVisible:true} | False |  | Toast notification settings. Line 23784-23786: default object structure. Line 23732: toggleCustomMessageOption modifies visible and messageVisible properties. |
| `step_variables` | object | undefined | True |  | COMPILE-TIME TRANSFORM: During step save for API_TRIGGER, set to {params:{api_body:'{{vars.request.data}}',api_params:'{{vars.request.params}}'}}. Line 34553-34558. Line 23725: deleted during initialization. Line 34495: validation error if input property exists before save. |
| `__triggerLimit` | boolean | true | False |  | Enable trigger limiting. Line 23726: if undefined, set to true. Line 23734: updateTriggerLimit modifies triggerOnSource and triggerOnReplicate based on this flag. |
| `triggerOnSource` | boolean | true | False |  | Trigger when records are created/modified on source. Line 23726: defaults to true, modified by param.triggerLimit. Line 23734: set by updateTriggerLimit. |
| `triggerOnReplicate` | boolean | false | False |  | Trigger when records are replicated. Line 23726: defaults to false if __triggerLimit true. Line 23734: set by updateTriggerLimit. |

**Compile transforms:** Route UUID Preservation (line 33438): For APIEndpoint UUID df26c7a2-4166-4ca5-91e5-548e24c01b5f, route argument is PRESERVED during export. For other step types with route argument, route UUID is regenerated. Condition: stepTypeUUID.indexOf(APIEndpoint_UUID) < 0 triggers regeneration. \| step_variables.input Injection (lines 34553-34558): During API_TRIGGER step save, step_variables.input is SET to {params: {api_body: "{{vars.request.data}}", api_params: "{{vars.request.params}}"}}. This overwrites any user input. \| Empty Arguments Cleanup (lines 34487-34488): Undefined/empty values for when, mock_result, do_until.condition, for_each.item, message.content are deleted during save. \| step_variables.input Validation (line 34495): Pre-save error if step_variables.input exists in arguments - prevents invalid step_variables structure.

<details><summary>evidence</summary>

- Line 33951: stepTypeWidget('cybersponse.api_call') registration with trigger.html template
- Lines 23776-23781: API_TRIGGER initialization in csTrigger directive
- Lines 23782-23793: Shared trigger argument handling (resources, inputVariables, displayConditions)
- Line 25487: API_TRIGGER argument initialization (api_body, api_params)
- Line 33438: Route UUID preservation transform by UUID check
- Lines 34495-34559: Step save switch case with API_TRIGGER step_variables injection
- Line 617: API_TRIGGER constant definition as 'cybersponse.api_call'
- fsr-schema.ts lines 1301-1314: APIEndpointArgs inferred schema shows subset of editor-used arguments

</details>

## CodeSnippet step type argument schema extraction

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `connector` | string |  | True |  | CodeSnippet connector name; set by ConnectorStepCtrl.setActiveConnector() at line 37276 |
| `version` | string |  | True |  | Connector version; set at lines 37276, 37402, 37441; updated on agent change |
| `operation` | string |  | True |  | Operation name (e.g., execute_code); set by operationChanged() at line 37450 |
| `operationTitle` | string |  | True |  | Human-readable title; set at line 37450 from operation.title |
| `params` | object | {} | True |  | Parameters object, populated from operation.parameters (line 37389); for CodeSnippet includes python_function key |
| `config` | string | null | False |  | Configuration UUID; set conditionally at lines 37398-37400, 37450; null if operation has is_config_required=false |
| `step_variables` | unknown | {} | True |  | Step output schema; [system key] - contains step result structure |
| `name` | string |  | False |  | Display name from connector label; set at line 37276 |
| `agent` | string | null | False |  | Agent UUID for remote execution; set at lines 37441, 37454; deleted if not applicable (line 37442) |
| `pickFromTenant` | string | false | False |  | Use record ownership for agent selection; set at lines 37276, 37312, 37439, 37454 |
| `dynamicallySelected` | string | false | False |  | Dynamic agent config flag; set at lines 37312, 37315, 37454 |
| `annotation` | string | null | False |  | Annotation filter for operations; set at line 37276 if provided to setActiveConnector() |
| `for_each` | string | null | False |  | Loop config: {condition, item, __bulk?, parallel?, break_loop?}; line 37312 clears break_loop on agent mode toggle |
| `when` | string | null | False |  | Jinja conditional expression for step execution; standard connector-step key |
| `ignore_errors` | string | false | False |  | Suppress errors; standard connector-step key |
| `message` | string | null | False |  | Notification: {content, records, tags?, tenant?, thread?, type?, parentstepid?}; standard connector-step key |

**Compile transforms:** The bundle processes arguments only on load: the ie() function (line 34207) converts empty arrays to {} for step_variables, resource, arguments, params. No deletions or mutations occur at POST-save time — all controller-set arguments persist unchanged in the playbook JSON.

<details><summary>evidence</summary>

- 800_app.beautified.js:33897 (stepTypeWidget registration for CodeSnippet)
- 800_app.beautified.js:37273-37475 (ConnectorStepCtrl function definition)
- 800_app.beautified.js:37274-37291 (setActiveConnector sets connector, version, name, pickFromTenant)
- 800_app.beautified.js:37312-37316 (toggleAgentMode sets agent, pickFromTenant, dynamicallySelected, for_each.break_loop)
- 800_app.beautified.js:37389 (params population from operation.parameters)
- 800_app.beautified.js:37398-37400 (config selection logic)
- 800_app.beautified.js:37449-37451 (operationChanged function S sets operation, operationTitle, params, config)
- 800_app.beautified.js:37437-37447 (agentChanged function T sets agent, pickFromTenant, version)
- 800_app.beautified.js:34207-34211 (ie() function load-time transform)
- fsr-schema.ts:1317-1337 (CodeSnippet inferred schema for cross-check)

</details>

## reverse-engineer-setapikeys-step-type

confidence **high**

| key | type | default | required | enum | notes |
|---|---|---|---|---|---|
| `public_key` | string |  | True |  | Supports Jinja expressions/tags. Controller validates via dynamicValueService.isJinjaConvertibleToTag() |
| `private_key` | string |  | True |  | Supports Jinja expressions/tags. Controller validates via dynamicValueService.isJinjaConvertibleToTag() |

**Compile transforms:** No compile-time transforms detected. Controller only evaluates jinjaConfig state for UI; does not mutate arguments object.

<details><summary>evidence</summary>

- 800_app.beautified.js:33934-33936 (stepTypeWidget registration)
- 800_app.beautified.js:38171-38182 (SetAPIKeysCtrl definition)
- app.beautified.js:32352-32354, 36589-36600 (prior build — identical)
- fsr-schema.ts:1345-1349 (inferred schema match)

</details>

---

## Completeness audit

# Completeness Analysis: 21-Step FortiSOAR Extraction

## Prioritized Punch-List of Gaps

### **TIER 1: Low Confidence / Thin Coverage (Reliability Risk)**

1. **SendEmail (Medium Confidence)**
   - Only 20 instances observed; `cc`, `bcc`, `subject`, `attachments` fields marked "not exposed in SendEmailCtrl" but present in inferred `params` schema
   - Implementation gap: params structure vs arguments structure mismatch; unclear how editor args map to params object (lines 1025-1039 in params schema)
   - **Action:** Cross-verify against a captured SendEmail playbook step JSON; map controller fields to params keys

2. **CreateTask (Medium Confidence)**
   - Only 6 instances; no explicit stepTypeWidget registration found
   - Argument structure inferred from "Entity('tasks') dynamic field discovery" at line 37577, not extracted from bundle
   - Full field list at fsr-schema.ts:1243-1288 is inferred, not evidenced
   - **Action:** Extract exact field list from FortiSOAR demo appliance tasks module schema; verify all 40+ fields

3. **SetAPIKeys (Very Thin Coverage)**
   - Only 2 arguments documented; no validation rules, no compile-time transforms
   - No evidence of Jinja vs "tag" difference in public_key/private_key handling
   - **Action:** Clarify semantics of "isJinjaConvertibleToTag" vs full Jinja expressions; test with demo appliance

---

### **TIER 2: Cross-Step Inconsistencies (Normalization Risk)**

4. **`for_each` Structure Variance**
   - Documented as:
     - `{item, condition, __bulk?, parallel?, break_loop?}` (Connector, Delay, ReferencePlaybook)
     - `{condition, item, __bulk?, batch_size?, parallel?}` (UpdateRecord, IngestBulkFeed)
     - Inconsistent about `batch_size` presence, default, and compile-time behavior
   - Lines 11542, 11581, 11599 show complex __bulk/parallel/batch_size logic with unclear interaction
   - **Action:** Extract exact schema for `for_each` from lines 11536-11605; test all three modes (sequential, parallel, bulk) against demo appliance

5. **`operation` Key Overloading**
   - Connector steps: `operation` = operation UUID (system key)
   - UpdateRecord/CreateRecord: `operation` = enum ['Append', 'Overwrite'] (field merge strategy)
   - Triggers/Decision: no `operation` key at all
   - **Action:** Rename for clarity in typing; separate ConnectorOperation from FieldOperation

6. **`config` Type Variance**
   - Connector steps: UUID string or null (line 37450: "config=null if is_config_required=false")
   - Some steps show `config` deleted on save
   - No validation of config UUID existence or permissions
   - **Action:** Document config lifecycle (init → validation → compile → persist)

7. **`step_variables` Input vs Output Confusion**
   - Triggers: compiler INJECTS step_variables.input (lines 34553-34572)
   - Other steps: step_variables treated as user-defined output schema
   - Inconsistent documentation: sometimes "array", sometimes "object", sometimes "system key"
   - **Action:** Clarify: is step_variables.input always compiler-injected for triggers? Is it mutable by users?

8. **`message` Structure Variance**
   - Documented as object with {content, records, tags?, tenant?, thread?, type?, parentstepid?}
   - But some steps show only subset: {content, records, parentstepid?, tags?, tenant?, thread?, type?}
   - Ordering inconsistent
   - **Action:** Extract canonical message schema from line 34487 cleanup logic; verify all fields

---

### **TIER 3: Common Envelope Keys Omitted / Inconsistently Documented**

9. **Universal Keys Missing From Per-Step Docs**
   - `name` (step display name) — present in SetVariables, Connector, but not documented universally
   - `group` (step grouping) — mentioned in Trigger but not others
   - `left`, `top`, `width`, `height` (layout positioning) — never documented
   - `ignore_errors` — present in ALL steps but documented inconsistently:
     - Some: "boolean, default: false"
     - Some: "boolean, default: '', deleted if false"
     - Decision step excludes it at line 34545 ("excluded from arguments")
   - **Action:** Extract envelope schema once globally; reference per-step; flag exceptions

10. **Uncertain Jinja Expression Support Scope**
    - "Supports Jinja expressions" vs "Supports Jinja tags" distinction never clarified
    - dynamicValueService.isJinjaConvertibleToTag() called in many places; semantics unknown
    - Which fields accept {{vars.xyz}}? Which only accept literals?
    - **Action:** Define Jinja support levels (none, literals-only, full-Jinja, Jinja+tags) and apply consistently

---

### **TIER 4: Still Effectively Inferred, Not Evidenced**

11. **SendEmail Parameter Mapping**
    - `to`, `from_str`, `content` exposed in controller
    - But `cc`, `bcc`, `subject`, `attachments`, `config`, `connector`, `version`, `params` inferred from schema, not extracted from SendEmailCtrl
    - Line 38148-38169: SendEmailCtrl code doesn't show how these params are set
    - **Action:** Check if SendEmail uses hidden fields or delegates to generic connector handler; cross-verify with captured playbook JSON

12. **CreateTask Field Discovery**
    - Controller does "for_each field in Entity('tasks')" at line 37577
    - Actual field list never extracted; relying on inferred schema
    - No evidence of field validation, type coercion, or relationship handling
    - **Action:** Capture tasks module schema from appliance; verify field list and required fields

13. **ManualInput Email Notification Structure**
    - email_notification, external_email_subject, internal_email_subject, custom_email_body_external, custom_email_body_internal, external_email_attachments, internal_email_attachments documented but not extracted from bundle
    - Only initialized at line 37920-37921; implementation details unclear
    - **Action:** Trace through ManualInputCtrl initialization and event handlers to extract exact structure

14. **Decision conditions[n] Field Semantics**
    - `step_iri`, `condition`, `default`, `option`, `step_name` — unclear which are mutually exclusive
    - `condition` Jinja evaluation order vs `default` fallback logic not documented
    - **Action:** Extract decision routing algorithm from compiler (line 34489-34490); test with multi-condition decision step

15. **FindRecords Query Filter Syntax**
    - Documented as "follows Query class definition" but exact filter syntax not extracted
    - Does it use FTS5? Lucene? Postgres JSON operators?
    - Operator precedence for `logic: 'AND'|'OR'` unclear
    - **Action:** Extract Query class definition from codebase; document filter operators and precedence

16. **Loop Execution Mode Semantics**
    - `__bulk=true, batch_size=100` — what's the API behavior? Batch insert? Transaction?
    - Line 11542: bulk defaults to batch_size=100 if not set; where does 100 come from?
    - parallel=true vs sequential=false — async vs sync?
    - **Action:** Test loop modes against demo appliance; document performance implications

---

### **TIER 5: Schema Mismatches (Bundle vs Inferred)**

17. **Connector operationTitle Presence Variance**
    - `operationTitle` documented as "present in ~1254/1256 instances" but also "not critical for playback"
    - Some compile transforms ignore it; others seem to rely on it
    - **Action:** Verify if operationTitle is compile-time-generated from operation UUID or user-provided

18. **Trigger displayConditions Exclusion Inconsistency**
    - Decision step excludes displayConditions at line 34545 ("excluded from arguments")
    - But OnUpdate, OnCreate, ManualStart show displayConditions as valid argument
    - **Action:** Test displayConditions on all trigger types; clarify where it's valid/invalid

19. **agent/pickFromTenant/dynamicallySelected Scope**
    - Only documented for Connector-based steps (Connector, UtilityNoOp, CodeSnippet)
    - But ReferencePlaybook mentions agent at lines 37195-37202
    - Is agent a universal key or connector-specific?
    - **Action:** Search bundle for all agent-related mutations; determine if universal or scoped

---

### **TIER 6: Undocumented Semantics**

20. **Append vs Overwrite Field Merge Logic**
    - UpdateRecord, CreateRecord document operation enum ['Append', 'Overwrite']
    - Exact semantics never documented:
      - Does Append concatenate arrays? Merge objects?
      - Does Overwrite replace entire field value or merge?
      - Are semantics field-type-dependent (multiselectpicklist vs text vs lookup)?
    - **Action:** Test with demo appliance; document per field type

21. **Config Required=False Behavior**
    - Line 37450: "if operation.is_config_required=false, set config=null"
    - Unclear what happens at runtime; does null config use default?
    - **Action:** Trace API call behavior when config is null

---

## Overall Reliability Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Coverage** | 95% | 21/21 step types documented; 2-3 have gaps |
| **Evidence** | 85% | SendEmail (cc/bcc/subject), CreateTask (field list), ManualInput (email structure) inferred not extracted |
| **Consistency** | 70% | Cross-step inconsistencies in for_each, operation, config, step_variables, ignore_errors |
| **Completeness** | 80% | Common envelope keys (name, group, left/top, layout) not systematized; Jinja support scope unclear |
| **Compilation Logic** | 75% | Compile-time transforms documented but __bulk/parallel/batch_size interaction complex; reference block transforms may have edge cases |

**Recommendation:** 
- **Production Use:** Safe for steps with high confidence + full evidence (Connector, Triggers, SetVariables, FindRecords, ReferencePlaybook, Wait, Decision, UpdateRecord, CreateRecord, ManualStart, OnCreate, IngestBulkFeed, ManualInput, Approval, APIEndpoint, CodeSnippet). Use as source-of-truth for SDK schema generation.
- **Beta/Validation Needed:** SendEmail, CreateTask, SetAPIKeys. Require cross-verification with demo appliance before SDK commit.
- **Next Actions:** (1) Extract common envelope schema; (2) resolve for_each/config/operation/step_variables inconsistencies; (3) verify SendEmail/CreateTask against appliance; (4) document Jinja support scope; (5) extract compile-time transform edge cases from lines 11542-11605, 33438-33449.