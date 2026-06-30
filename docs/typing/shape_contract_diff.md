# Shape-contract diff (Pass 2)

Stages analyzed: 9 (3 producer, 6 consumer)

## PHANTOM READS — read by a consumer, written by no stage
_The F3 signature: the reader is looking at a key nothing produces._

- `apply_async` — read by: emitter.py, typed_walker.py
- `connector_name` — read by: typed_walker.py
- `inputs` — read by: typed_walker.py
- `mock_result` — read by: emitter.py
- `module` — read by: typed_walker.py
- `modules` — read by: typed_walker.py
- `op` — read by: typed_walker.py
- `op_name` — read by: typed_walker.py
- `target` — read by: emitter.py, typed_walker.py
- `vars` — read by: typed_walker.py
- `when` — read by: emitter.py

## DEAD WRITES — written by a producer, read by no other stage
_Authored data that may never reach a consumer (silent-drop candidate)._

- `__triggerLimit` — written by: resolver/normalizers.py
- `authentication_methods` — written by: resolver/normalizers.py
- `collection` — written by: resolver/normalizers.py
- `config` — written by: resolver/connector_args.py, resolver/normalizers.py
- `content` — written by: resolver/normalizers.py
- `displayConditions` — written by: resolver/normalizers.py
- `email_notification` — written by: resolver/normalizers.py
- `executeButtonText` — written by: resolver/normalizers.py
- `from_str` — written by: resolver/normalizers.py
- `is_approval` — written by: resolver/normalizers.py
- `noRecordExecution` — written by: resolver/normalizers.py
- `operationTitle` — written by: resolver/connector_args.py
- `pickFromTenant` — written by: parser.py, resolver/connector_args.py
- `showToasterMessage` — written by: resolver/normalizers.py
- `singleRecordExecution` — written by: resolver/normalizers.py
- `step_variables` — written by: parser.py, resolver/connector_args.py, resolver/normalizers.py
- `triggerOnReplicate` — written by: resolver/normalizers.py
- `triggerOnSource` — written by: resolver/normalizers.py
- `version` — written by: resolver/connector_args.py

## Key x stage matrix (R=read, W=write)

| key | parser | normalizers | connector_args | emitter | typed_walker | validator | render_analyzer | arg_validator | decompiler |
|---|---|---|---|---|---|---|---|---|---|
| __triggerLimit |  | W |  |  |  |  |  |  |  |
| agent | W |  |  | R |  |  |  |  |  |
| apply_async |  |  |  | R | R |  |  |  |  |
| arg_list | W |  |  |  | R | R |  |  |  |
| arguments |  |  | R |  |  |  |  |  |  |
| authentication_methods |  | W |  |  |  |  |  |  |  |
| body |  | R |  |  |  |  |  |  |  |
| button_label |  | R |  |  |  |  |  |  |  |
| checkboxFields |  | R |  |  |  |  |  |  |  |
| collection |  | W |  |  |  |  |  |  |  |
| conditions | RW |  |  | RW |  | R | R |  | R |
| config |  | W | W |  |  |  |  |  |  |
| connector |  | RW | R |  | R | R |  |  |  |
| connector_name |  |  |  |  | R |  |  |  |  |
| content |  | W |  |  |  |  |  |  |  |
| description |  | R |  |  |  |  |  |  |  |
| displayConditions |  | W |  |  |  |  |  |  |  |
| do_until | W |  |  | R |  |  |  |  |  |
| email_notification |  | W |  |  |  |  |  |  |  |
| executeButtonText |  | W |  |  |  |  |  |  |  |
| external_channel_list |  | RW |  |  |  |  |  |  |  |
| fieldbasedtrigger |  | RW |  |  |  |  |  |  |  |
| for_each |  |  |  | RW |  |  |  |  |  |
| from |  | R |  |  |  |  |  |  |  |
| from_str |  | W |  |  |  |  |  |  |  |
| inline_channel_list |  | RW |  |  |  |  |  |  |  |
| input |  | RW |  |  | R |  |  |  |  |
| inputExternalUser |  | R |  |  |  |  |  |  |  |
| inputVariables |  | RW |  |  | R |  |  |  |  |
| inputs |  | R |  |  | R |  |  |  |  |
| isRecordLinked |  | RW |  |  |  |  |  |  |  |
| is_approval |  | W |  |  |  |  |  |  |  |
| message | W | RW |  | R |  |  |  |  | R |
| mock_result |  |  |  | R |  |  |  |  |  |
| module |  | R |  |  | R |  |  |  |  |
| modules |  | R |  |  | R |  |  |  |  |
| noRecordExecution |  | W |  |  |  |  |  |  |  |
| op |  |  |  |  | R |  |  |  |  |
| op_name |  |  |  |  | R |  |  |  |  |
| operation |  | RW | R |  | R | R |  |  |  |
| operationTitle |  |  | W |  |  |  |  |  |  |
| options | RW | R |  |  | R |  |  |  |  |
| owner_detail |  | RW |  |  |  |  |  |  |  |
| params |  | RW | RW |  | R |  |  |  |  |
| pickFromTenant | W |  | W |  |  |  |  |  |  |
| python_function |  | R |  |  |  |  |  |  |  |
| query |  | R |  |  |  |  |  |  |  |
| record |  | RW |  |  |  |  |  |  |  |
| requires_record |  | R |  |  |  |  |  |  |  |
| resource |  | RW |  |  | R |  |  |  |  |
| resources |  | RW |  |  | R |  |  |  |  |
| response_mapping |  | RW |  | R |  | R |  |  | R |
| route |  | RW |  |  |  |  |  |  |  |
| run_mode |  | R |  |  |  |  |  |  |  |
| showToasterMessage |  | W |  |  |  |  |  |  |  |
| singleRecordExecution |  | W |  |  |  |  |  |  |  |
| step_variables | W | W | W |  |  |  |  |  |  |
| target |  |  | R | R | R |  |  |  |  |
| title |  | RW |  |  |  |  |  |  |  |
| triggerOnReplicate |  | W |  |  |  |  |  |  |  |
| triggerOnSource |  | W |  |  |  |  |  |  |  |
| unauthenticated_input |  | RW |  |  |  |  |  |  |  |
| vars |  |  |  |  | R |  |  |  |  |
| version |  |  | W |  |  |  |  |  |  |
| when |  | R |  | R |  |  |  |  |  |
| workflowReference |  |  | R | W | R |  |  |  |  |
