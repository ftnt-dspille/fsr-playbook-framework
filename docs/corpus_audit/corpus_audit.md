# Corpus shape audit

## Step argument keys vs resolver whitelists

### `ApprovalManualInput` — 3 rows, 19 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `customEmailExternal`×3, `internal_email_subject`×3, `email_notification`×3, `isRecordLinked`×3, `custom_email_body_external`×3, `record`×3, `resources`×3, `unauthenticated_input`×3, `external_channel_list`×3, `agent_id`×3, `input`×3, `owner_detail`×3, `inline_channel_list`×3, `is_approval`×3, `external_email_subject`×3

### `CodeSnippet` — 28 rows, 8 distinct keys
✓ no unexpected keys
Never observed in corpus: `pickFromTenant`

### `Connectors` — 1332 rows, 35 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `operation`×1332, `version`×1332, `connector`×1332, `params`×1331, `name`×1330, `operationTitle`×1328, `config`×1273, `step_variables`×1073, `pickFromTenant`×498, `mock_result`×115, `operationOutput`×53, `ignore_errors`×46, `when`×38, `for_each`×30, `message`×18

### `CyopsUtilites` — 525 rows, 14 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `operation`×525, `version`×525, `step_variables`×525, `params`×525, `connector`×525, `operationTitle`×525, `when`×50, `for_each`×30, `ignore_errors`×22, `message`×10, `config`×7, `do_until`×2, `mock_result`×2, `name`×1

### `Decision` — 380 rows, 2 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `conditions`×380, `step_variables`×190

### `Delay` — 32 rows, 6 distinct keys
✓ no unexpected keys

### `FindRecords` — 305 rows, 8 distinct keys
✓ no unexpected keys
Never observed in corpus: `condition`, `mock_result`, `partial`

### `IngestBulkFeed` — 18 rows, 8 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `collection`×18, `resource`×18, `step_variables`×18, `for_each`×16, `__recommend`×14, `_showJson`×8, `when`×5, `mock_result`×2

### `InsertData` — 300 rows, 14 distinct keys
✓ no unexpected keys
Never observed in corpus: `__bulk`, `collectionType`

### `ManualInput` — 190 rows, 27 distinct keys
✓ no unexpected keys

### `ManualTask` — 6 rows, 4 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `collection`×6, `resource`×6, `step_variables`×6, `message`×3

### `RunScript` — 4 rows, 3 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `arguments`×4, `script`×4, `step_variables`×3

### `SendMail` — 23 rows, 16 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `version`×23, `config`×23, `connector`×23, `operation`×22, `step_variables`×22, `params`×22, `from_str`×22, `operationTitle`×21, `when`×6, `ignore_errors`×1, `mock_result`×1, `for_each`×1, `message`×1, `pickFromTenant`×1, `name`×1

### `SetAPIKeys` — 2 rows, 2 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `public_key`×2, `private_key`×2

### `SetVariable` — 1564 rows, 1331 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `output`×143, `data`×44, `payload`×35, `useMockOutput`×32, `indicatorValue`×29, `indicatorIRI`×29, `target_record_id`×27, `loggedInUserName`×26, `actionReason`×26, `context`×24, `indicator_value`×21, `enrichment_summary`×20, `params`×20, `source_data`×19, `cti_name`×17

### `UpdateRecord` — 385 rows, 13 distinct keys
✓ no unexpected keys
Never observed in corpus: `__bulk`, `config`, `is_upsert`, `version`

### `WorkflowReference` — 624 rows, 13 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `arguments`×624, `step_variables`×624, `workflowReference`×624, `apply_async`×618, `pass_input_record`×570, `pass_parent_env`×532, `for_each`×164, `when`×52, `ignore_errors`×28, `message`×9, `do_until`×8, `mock_result`×2, `params`×1

### `cybersponse.abstract_trigger` — 766 rows, 32 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `step_variables`×762, `triggerOnSource`×194, `__triggerLimit`×194, `triggerOnReplicate`×194, `message`×1, `modifyUser_id`×1, `connector_action_inputs`×1, `connector_label`×1, `connector_version`×1, `poll`×1, `tag`×1, `connector_icon`×1, `name`×1, `createUser_id`×1, `uuid`×1

### `cybersponse.action` — 840 rows, 21 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `resources`×840, `inputVariables`×840, `route`×839, `step_variables`×838, `singleRecordExecution`×823, `noRecordExecution`×819, `title`×783, `executeButtonText`×706, `displayConditions`×353, `_promptexpanded`×135, `showToasterMessage`×133, `triggerOnReplicate`×130, `triggerOnSource`×129, `__triggerLimit`×129, `operation`×1

### `cybersponse.api_call` — 18 rows, 6 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `route`×18, `authentication_methods`×18, `step_variables`×17, `triggerOnSource`×9, `triggerOnReplicate`×9, `__triggerLimit`×8

### `cybersponse.post_create` — 37 rows, 7 distinct keys
✓ no unexpected keys
Never observed in corpus: `useMockOutput`, `version`

### `cybersponse.post_delete` — 1 rows, 7 distinct keys
_no resolver normalizer; observed keys only_

Top keys: `triggerOnSource`×1, `resources`×1, `step_variables`×1, `__triggerLimit`×1, `resource`×1, `fieldbasedtrigger`×1, `triggerOnReplicate`×1

### `cybersponse.post_update` — 59 rows, 8 distinct keys
✓ no unexpected keys
Never observed in corpus: `useMockOutput`

## ManualInput inputVariables tuple drift

Distinct tuples: 20
✓ every observed tuple is covered by some `kind:`

Kinds never observed in corpus: `date`, `datetime`, `decimal`, `email`, `filehash`, `image`, `integer`, `multiselect`, `multiselectpicklist`, `phone`, `url`
