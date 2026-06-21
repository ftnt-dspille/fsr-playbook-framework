# FortiSOAR playbook step types

Generated from `store/fsr_reference.db` by `python/store/export_step_types.py`. Source-of-truth is the live FSR appliance's `/api/3/workflow_step_types/` endpoint plus mined samples from `/api/3/workflow_steps?$relationships=true`.

Each step type is ordered by **observed frequency** across the 43 step types and ~7000 step instances on the connected instance. The top of this list is what real playbooks reach for first.

**Schema completeness caveat**: the `arguments` blob shown per step type is what the API returned — it's a partial schema (often just a `script` pointer + pre-bound args). To get canonical Python signatures for each step's celery handler, run `scripts/dump_step_types.py` on the FSR appliance and ingest the result. Until then, the **examples** section per step is the most reliable guide to what `arguments` should look like.

**`for_each` is a step modifier, not a step type.** See [`docs/FOR_EACH.md`](../docs/FOR_EACH.md) for the host allowlist, fields, modes (sequential / parallel / bulk), and runtime shape of `vars.steps.<loop>`.

---

## `SetVariable`
_label: Set Variable_

**Occurrences**: 1492 · **Category**: `RunScript` · **UUID**: `04d0cf46-b6a8-42c4-8683-60a7eaa69e8f`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/set_multiple"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:0001d33e-572b-477b-a535-08971840a4e0)</summary>

```json
{
  "name": "user input",
  "arguments": {
    "selected_profile": "{{vars.steps.prompt_output_profile.input.outputProfile}}"
  }
}
```

</details>

<details><summary>Example 2 (step:00040900-448e-4f20-b3a2-c459800ea339)</summary>

```json
{
  "name": "setup env",
  "arguments": {
    "context": "{{vars.input.params.context}}",
    "raw_data": "{{vars.input.params.rawData}}",
    "target_id": "{{vars.input.records[0].id}}"
  }
}
```

</details>

<details><summary>Example 3 (step:007e2d1d-4b11-47d6-b7f4-aef73c685a3f)</summary>

```json
{
  "name": "setup env",
  "arguments": {
    "var_list": "[\n  \"domain\",\n  \"name\",\n  \"type\",\n  \"device_ip\",\n  \"device_username\",\n  \"device_password\",\n  \"device_apikey\"\n]",
    "record_id": "{{vars.input.params['target_id']}}"
  }
}
```

</details>

---

## `Connectors`
_label: Connector_

**Occurrences**: 1323 · **Category**: `RunScript` · **UUID**: `0bfed618-0316-11e7-93ae-92361f002671`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/connector"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:000d0516-e052-4b07-b198-34febf52f53b)</summary>

```json
{
  "name": "Get Organization Details",
  "arguments": {
    "name": "Fortinet FortiSIEM",
    "config": "''",
    "params": {
      "domain_id": ""
    },
    "version": "5.4.2",
    "connector": "fortinet-fortisiem",
    "operation": "get_org_name_by_org_id",
    "operationTitle": "Get Organization Details"
  }
}
```

</details>

<details><summary>Example 2 (step:001a30be-f201-437e-a45f-9f32e8e84838)</summary>

```json
{
  "name": "Update User Group",
  "arguments": {
    "name": "Fortinet FortiManager",
    "config": "",
    "params": {
      "adom": "root",
      "name": "FSR User Group",
      "method": [
        "Add",
        "Remove"
      ],
      "add_member": "test",
      "level_type": "ADOM",
      "remove_member": "guest",
      "additional_args": ""
    },
    "version": "3.0.0",
    "connector": "fortinet-fortimanager",
    "operation": "update_user_group",
    "operationTitle": "Update User Group",
    "step_variables": {
      "output_data": "{{vars.result}}"
    }
  }
}
```

</details>

<details><summary>Example 3 (step:00a39722-7b2e-4e1d-bae9-5d203a8f453e)</summary>

```json
{
  "name": "Revoke Access",
  "arguments": {
    "name": "SailPoint IdentityNow",
    "config": "test",
    "params": {
      "requestedFor": "2c918084660f45d6016617daa9210584",
      "clientMetadata": "{\n    \"requestedAppId\": \"2c91808f7892918f0178b78da4a305a1\",\n    \"requestedAppName\": \"test-app\"\n  }",
      "requestedItems": [
        {
          "id": "2c9180835d2e5168015d32f890ca1581",
          "type": "ACCESS_PROFILE",
          "comment": "Requesting access profile for John Doe",
          "removeDate": "2020-07-11T21:23:15.000Z",
          "clientMetadata": {
            "requestedAppId": "2c91808f7892918f0178b78da4a305a1",
            "requestedAppName": "test-app"
          }
        }
      ]
    },
    "version": "1.0.0",
    "connector": "sailpoint-identitynow",
    "operation": "revoke_request",
    "operationTitle": "Revoke Request",
    "step_variables": {
      "output_data": "{{vars.result}}"
    }
  }
}
```

</details>

---

## `cybersponse.action`
_label: Manual_

**Occurrences**: 830 · **Category**: `cybersponse.abstract_trigger` · **UUID**: `f414d039-bb0d-4e59-9c39-a8f1e880b18a`

Triggered when the user selects record(s) and then selects the playbook from the "Execute" list.

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (3):

<details><summary>Example 1 (step:000848ef-2946-437d-b4c1-6283686e78ff)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "route": "00f52398-081d-4358-991a-24adeb57be00",
    "title": "Link Similar Alerts",
    "resources": [
      "alerts"
    ],
    "inputVariables": [],
    "step_variables": {
      "input": {
        "records": "{{vars.input.records}}"
      }
    },
    "displayConditions": {
      "alerts": {
        "sort": [],
        "limit": 30,
        "logic": "AND",
        "filters": [
          {
            "type": "primitive",
            "field": "id",
            "value": 0,
            "operator": "eq",
            "_operator": "eq"
          }
        ]
      }
    },
    "executeButtonText": "Execute",
    "noRecordExecution": false,
    "singleRecordExecution": false
  }
}
```

</details>

<details><summary>Example 2 (step:0067b67d-c920-4518-ab4a-275b75d0b82b)</summary>

```json
{
  "name": "Alerts",
  "arguments": {
    "route": "c35e3a62-6ae1-4939-9e35-4b812e8252d5",
    "title": "Infoblox DDI: Retrieve RPZ Details",
    "resources": [
      "alerts"
    ],
    "inputVariables": [],
    "step_variables": {
      "input": {
        "records": "{{vars.input.records}}"
      }
    },
    "noRecordExecution": true,
    "singleRecordExecution": false
  }
}
```

</details>

<details><summary>Example 3 (step:00a93bc1-37bd-45de-8b04-3f1aa9e85490)</summary>

```json
{
  "name": "Alerts",
  "arguments": {
    "route": "7af437b7-0c0c-4e21-9674-80fd3e344fc3",
    "title": "Fortinet FortiManager: Create Address Group",
    "resources": [
      "alerts"
    ],
    "inputVariables": [],
    "step_variables": {
      "input": {
        "records": "{{vars.input.records[0]}}"
      }
    },
    "noRecordExecution": true,
    "singleRecordExecution": false
  }
}
```

</details>

---

## `cybersponse.abstract_trigger`
_label: Referenced_

**Occurrences**: 727 · **Category**: `SetVariable` · **UUID**: `b348f017-9a94-471f-87f8-ce88b6a7ad62`

Triggered from another playbook using a "Reference Playbook" step or from a schedule.

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (3):

<details><summary>Example 1 (step:003afd3e-e6a8-4230-bb6f-40d3638d0251)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "step_variables": {
      "input": {
        "params": []
      }
    }
  }
}
```

</details>

<details><summary>Example 2 (step:00445436-4a5d-4322-8880-7f30813d7dd3)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "step_variables": {
      "input": {
        "params": []
      }
    }
  }
}
```

</details>

<details><summary>Example 3 (step:004dbd02-daee-4550-811d-3793864e2980)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": []
      }
    },
    "triggerOnSource": true,
    "triggerOnReplicate": false
  }
}
```

</details>

---

## `WorkflowReference`
_label: Reference a Playbook_

**Occurrences**: 564 · **Category**: `RunScript` · **UUID**: `74932bdc-b8b6-4d24-88c4-1a4dfbc524f3`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/workflow_reference"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:00b4fdce-3df0-43a0-9b6f-b5cf6e4a0c52)</summary>

```json
{
  "name": "install_device_package",
  "arguments": {
    "for_each": {
      "item": "{{vars.device_idx}}",
      "parallel": false,
      "condition": ""
    },
    "arguments": {
      "adom": "{{vars.item['adom']}}",
      "devices": "{{vars.item['scope']}}",
      "package": "{{vars.input.params.policyPackage}}",
      "connector_config": "{{vars.item['fmg']}}",
      "assign_device_flag": "True"
    },
    "apply_async": false,
    "step_variables": [],
    "pass_parent_env": false,
    "pass_input_record": false,
    "workflowReference": "/api/3/workflows/ad544501-706a-48af-972e-e1035f81c021"
  }
}
```

</details>

<details><summary>Example 2 (step:0133633d-e3f5-4839-8df0-1a225dd37db5)</summary>

```json
{
  "name": "Block Mac Addresses",
  "arguments": {
    "when": "{{vars.list_of_mac_addresses_to_block | length > 0}}",
    "for_each": {
      "item": "{{vars.total_batches_mac_addresses}}",
      "parallel": false,
      "condition": ""
    },
    "arguments": {
      "macAddressList": "{{vars.item}}"
    },
    "apply_async": false,
    "step_variables": [],
    "pass_parent_env": false,
    "pass_input_record": true,
    "workflowReference": "/api/3/workflows/5976355c-90bf-4ff8-b80e-c2f8411b9aa1"
  }
}
```

</details>

<details><summary>Example 3 (step:039451fd-99ff-480d-b82b-ad4c3e95c8de)</summary>

```json
{
  "name": "calculate stats",
  "arguments": {
    "arguments": {
      "target_record_id": "{{vars.input.records[0].netshotTargets.id}}"
    },
    "apply_async": false,
    "step_variables": [],
    "pass_parent_env": false,
    "pass_input_record": false,
    "workflowReference": "/api/3/workflows/c35569ed-7415-499e-85c0-e65010facbc6"
  }
}
```

</details>

---

## `CyopsUtilites`
_label: Utilities_

**Occurrences**: 491 · **Category**: `RunScript` · **UUID**: `0109f35d-090b-4a2b-bd8a-94cbc3508562`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/connector",
  "arguments": {
    "connector": "cyops_utilities"
  }
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:00c04532-2d97-446f-b930-6320410957ee)</summary>

```json
{
  "name": "Exit the playbook",
  "arguments": {
    "params": [],
    "version": "3.1.2",
    "connector": "cyops_utilities",
    "operation": "no_op",
    "operationTitle": "Utils: No Operation",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:00cff1fb-907b-45a0-80f9-32bb9ba09756)</summary>

```json
{
  "name": "Reset Global Variables",
  "arguments": {
    "params": {
      "iri": "/api/wf/api/dynamic-variable/{{vars.item}}/?format=json",
      "body": "",
      "method": "DELETE"
    },
    "version": "3.2.1",
    "for_each": {
      "item": "{{vars.enrichment_global_variable}}",
      "parallel": false,
      "condition": ""
    },
    "connector": "cyops_utilities",
    "operation": "make_cyops_request",
    "operationTitle": "FSR: Make FortiSOAR API Call",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:01da5bd6-8b5a-4264-a356-af64587fd37e)</summary>

```json
{
  "name": "Add Comment To The Related Records",
  "arguments": {
    "params": {
      "iri": "/api/3/comments",
      "body": "{{vars.comment_payload}}"
    },
    "version": "2.7.0",
    "connector": "cyops_utilities",
    "operation": "insert_cyops_resource",
    "operationTitle": "CyOPs: Create Record",
    "step_variables": []
  }
}
```

</details>

---

## `UpdateRecord`
_label: Update Record_

**Occurrences**: 356 · **Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928722`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/update_data"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:0005ec16-d673-416e-b054-8f16db728f15)</summary>

```json
{
  "name": "Update Summary",
  "arguments": {
    "message": {
      "tags": [],
      "type": "/api/3/picklists/ff599189-3eeb-4c86-acb0-a7915e85ac3b",
      "tenant": "{{vars.input.records[0].tenant['@id']}}",
      "content": "<p><strong>Drive-by Download</strong> attack was <span style=\"background: #2aba42; color: #ffffff; padding: 2px 7px;\" class=\"badge badge-pill badge-danger\">Not Observed</span> for the URLs:</p>\n<p>{% for i in vars.steps.Get_URL_Indicators %}</p>\n<ul>\n<li>{{i.value}}</li>\n</ul>\n<p>{%endfor%}</p>",
      "records": "",
      "parentstepid": "/api/3/workflow_steps/5d69c55c-23de-45bc-bcf6-abfe619b2cf3"
    },
    "resource": {
      "__link": {
        "recordTags": []
      }
    },
    "_showJson": false,
    "operation": "Append",
    "collection": "{{vars.input.records[0]['@id']}}",
    "__recommend": [],
    "collectionType": "/api/3/alerts",
    "fieldOperation": {
      "recordTags": "Append"
    },
    "step_variables": {
      "drive_by_download_check_message": "Drive-by Download attack was <span class=\"badge badge-pill badge-danger\" style=\"background: #2aba42; color: #ffffff; padding: 1px 7px;\">Not Observed</span> for the URLs."
    }
  }
}
```

</details>

<details><summary>Example 2 (step:0148eda7-688a-4bf7-8ab3-0c95c2440703)</summary>

```json
{
  "name": "Update Record",
  "arguments": {
    "resource": {
      "fileHashes": "{{vars.file_hashes}}",
      "sourcedata": "{{vars.data_detection | toJSON}}",
      "iPAddresses": "{{vars.destination_ips}}"
    },
    "operation": "Append",
    "collection": "{{vars.input.records[0]['@id']}}",
    "__recommend": [],
    "collectionType": "/api/3/alerts",
    "fieldOperation": [],
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:02031528-eb90-4af9-a5c4-9a5581a68433)</summary>

```json
{
  "name": "update_phase",
  "arguments": {
    "for_each": {
      "item": "{{vars.device_record_iri_list}}",
      "__bulk": true,
      "parallel": false,
      "condition": "",
      "batch_size": 100
    },
    "resource": {
      "zTPPhase": "{{\"ZTP Phase\"|picklist( vars.input.params.ztp_phase )}}"
    },
    "operation": "Append",
    "collection": "{{vars.item}}",
    "__recommend": [],
    "collectionType": "/api/3/devices",
    "fieldOperation": [],
    "step_variables": []
  }
}
```

</details>

---

## `Decision`

**Occurrences**: 347 · **Category**: `RunScript` · **UUID**: `12254cf5-5db7-4b1a-8cb1-3af081924b28`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/cond"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:0039f531-3827-458e-a177-7d86f478686a)</summary>

```json
{
  "name": "Spoofing Check",
  "arguments": {
    "conditions": [
      {
        "option": "Yes",
        "step_iri": "/api/3/workflow_steps/c19becff-8c43-40bc-8170-8d1aad65d849",
        "condition": "{{ vars.sender_email_address != vars.sender_return_path }}",
        "step_name": "Add Spoofing Tag"
      },
      {
        "option": "No",
        "default": true,
        "step_iri": "/api/3/workflow_steps/6b55c2b5-083b-4fcb-8344-74f4b5f4d0f5",
        "step_name": "Add Note for No Spoofing"
      }
    ],
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:01211331-9958-4df3-8786-31de4bae5117)</summary>

```json
{
  "name": "Is indicator Found",
  "arguments": {
    "conditions": [
      {
        "option": "Yes",
        "step_iri": "/api/3/workflow_steps/aad5d903-9153-4740-ab27-033c4e5e4756",
        "condition": "{{ vars.steps.Is_Indicator_Exist | length > 0 }}",
        "step_name": "Enrich Indicator"
      },
      {
        "option": "No",
        "default": true,
        "step_iri": "/api/3/workflow_steps/aec1334b-4ead-4eb3-b04f-6875ae705b02",
        "step_name": "Create New Indicator"
      }
    ]
  }
}
```

</details>

<details><summary>Example 3 (step:01295dbf-0b59-45f1-a584-427d71f95735)</summary>

```json
{
  "name": "Handle Large Data",
  "arguments": {
    "conditions": [
      {
        "option": "Greater Limit Value",
        "step_iri": "/api/3/workflow_steps/969795e4-a07e-4751-9f77-2f7aa96516fe",
        "condition": "{{ vars.limit > 2000 }}",
        "step_name": "Calculate Total Count"
      },
      {
        "option": "Less Limit Value",
        "default": true,
        "step_iri": "/api/3/workflow_steps/7c3bc7aa-ccce-40af-8560-a506bbf0ccf7",
        "step_name": "Call Child Playbook for Less Limit"
      }
    ]
  }
}
```

</details>

---

## `FindRecords`
_label: Find Records_

**Occurrences**: 288 · **Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928770`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/find_data"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:01b0ad0d-682e-4a4c-9cb9-5040112e483c)</summary>

```json
{
  "name": "find_record",
  "arguments": {
    "query": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "primitive",
          "field": "id",
          "value": "{{vars.input.params['record_id']}}",
          "operator": "eq",
          "_operator": "eq"
        }
      ]
    },
    "module": "devices?$limit=1",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:01b45afe-ad72-4651-8138-5eced7d36773)</summary>

```json
{
  "name": "find outputs pending",
  "arguments": {
    "query": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "object",
          "field": "netshotTargets",
          "value": "{{vars.steps.find_target[0]['@id']}}",
          "_value": {
            "@id": "{{vars.steps.find_target[0]['@id']}}",
            "display": "",
            "itemValue": ""
          },
          "operator": "eq"
        },
        {
          "type": "array",
          "field": "status",
          "value": [
            "40982496-7c2f-4d6f-b0c0-bb998387821b",
            "caf00cc5-ecf8-4342-982b-3a9bdf81115a",
            "2f63f907-d342-4ad6-9a77-68c654bba2d2",
            "7c18340b-215d-4396-b052-623e4c085727"
          ],
          "module": "status",
          "display": "",
          "operator": "in",
          "template": "multiselectpicklist",
          "enableJinja": true,
          "OPERATOR_KEY": "$",
          "useInOperator": true,
          "previousOperator": "in",
          "previousTemplate": "multiselectpicklist"
        }
      ],
      "__selectFields": [
        "name",
        "id"
      ]
    },
    "module": "netshot_target_outputs?$limit=5000",
    "checkboxFields": true,
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:01c603bb-afca-4f9b-acce-8adf815d8bad)</summary>

```json
{
  "name": "Find Affected Asset",
  "arguments": {
    "query": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "primitive",
          "field": "hostname",
          "value": "{{vars.assetHostName}}",
          "operator": "eq",
          "_operator": "eq"
        }
      ]
    },
    "module": "assets?$limit=30",
    "step_variables": {
      "assetIRI": "['{{vars.result[0]['@id']}}']"
    }
  }
}
```

</details>

---

## `InsertData`
_label: Create Record_

**Occurrences**: 281 · **Category**: `WorkflowReference` · **UUID**: `2597053c-e718-44b4-8394-4d40fe26d357`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/insert_data"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:019b2c3d-1a69-4983-98cd-c4356eaf7bf7)</summary>

```json
{
  "name": "Detection T1",
  "arguments": {
    "resource": {
      "id": null,
      "name": "Determine if an Incident has occurred",
      "type": "{{(\"TaskType\" | picklist(\"Incident Response\"))[\"@id\"]}}",
      "dueBy": null,
      "notes": null,
      "alerts": null,
      "assets": null,
      "owners": null,
      "status": null,
      "persons": null,
      "comments": null,
      "priority": null,
      "taskdata": null,
      "tasktype": null,
      "companies": null,
      "incidents": "['{{vars.request.data['@id']}}']",
      "startDate": null,
      "createDate": null,
      "createUser": null,
      "modifyDate": null,
      "modifyUser": null,
      "workflowid": null,
      "attachments": null,
      "description": null,
      "approvalhost": null,
      "actualMinutes": null,
      "assignedOnDate": null,
      "completedOnDate": null,
      "vulnerabilities": null,
      "assignedToPerson": null,
      "systemAssignedQueue": null
    },
    "_showJson": false,
    "collection": "/api/3/tasks",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:02c79896-096d-447c-a081-db1a3cc123f8)</summary>

```json
{
  "name": "Create Alert Record",
  "arguments": {
    "resource": {
      "name": "{{vars.steps.Alert_Manual_Input_Form.input.alertName}}",
      "type": "/api/3/picklists/574a6ee2-7265-4701-815e-cff83b053bce",
      "state": "/api/3/picklists/a1bac09b-1441-45aa-ad1b-c88744e48e72",
      "status": "/api/3/picklists/7de816ff-7140-4ee5-bd05-93ce22002146",
      "severity": "/api/3/picklists/58d0753f-f7e4-403b-953c-b0f521eab759",
      "__replace": "",
      "description": "{{vars.steps.Alert_Manual_Input_Form.input.alertDescription}}",
      "ackSlaStatus": "/api/3/picklists/72979f64-e8b9-4888-a965-957e0ec24818",
      "respSlaStatus": "/api/3/picklists/72979f64-e8b9-4888-a965-957e0ec24818",
      "priorityWeight": 1,
      "escalatedtoincident": "/api/3/picklists/2128a09c-153d-4db3-985d-de6be33deae5",
      "alertRemainingAckSLA": 0
    },
    "_showJson": false,
    "operation": "Overwrite",
    "collection": "/api/3/alerts",
    "__recommend": [],
    "fieldOperation": [],
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:041ca4fe-3bd6-42a1-8b45-f1123e660d69)</summary>

```json
{
  "name": "Add Note For Clean Asset",
  "arguments": {
    "resource": {
      "type": {
        "id": 248,
        "@id": "/api/3/picklists/ff599189-3eeb-4c86-acb0-a7915e85ac3b",
        "icon": null,
        "@type": "Picklist",
        "color": null,
        "display": "Comment",
        "@context": "/api/3/contexts/Picklist",
        "listName": "/api/3/picklist_names/0841c1eb-a0a3-4abd-b29c-9f68e4d9b14f",
        "itemValue": "Comment",
        "orderIndex": 1
      },
      "people": [],
      "content": "Asset cleaned Successfully.",
      "__replace": "",
      "incidents": "{{vars.input.params['incident_iri']}}",
      "isImportant": false,
      "peopleUpdated": false
    },
    "_showJson": false,
    "operation": "Overwrite",
    "collection": "/api/3/comments",
    "__recommend": [],
    "fieldOperation": {
      "recordTags": "Overwrite"
    },
    "step_variables": []
  }
}
```

</details>

---

## `ManualInput`
_label: Manual Input_

**Occurrences**: 166 · **Category**: `RunScript` · **UUID**: `fc04082a-d7dc-4299-96fb-6837b1baa0fe`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/manual_input"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:00c8a0b4-6633-4bd6-89d5-bf0abb6230d5)</summary>

```json
{
  "name": "test",
  "arguments": {
    "type": "InputBased",
    "input": {
      "schema": {
        "title": "test",
        "description": "test",
        "inputVariables": [
          {
            "name": "test",
            "type": "array",
            "label": "test",
            "title": "Dynamic List",
            "usable": true,
            "options": "{{vars.dyn_list}}",
            "tooltip": "",
            "dataType": "dynamicList",
            "formType": "dynamicList",
            "required": false,
            "_expanded": true,
            "mmdUpdate": true,
            "collection": false,
            "searchable": false,
            "templateUrl": "app/components/form/fields/dynamicList.html",
            "defaultValue": null,
            "_previousName": "",
            "playbookField": true,
            "lengthConstraint": true,
            "allowedGridColumn": false,
            "requiredCondition": "notrequired",
            "jinjaExpressionView": true,
            "useRecordFieldDefault": false,
            "_addRequiredConditions": false
          }
        ]
      }
    },
    "record": "",
    "is_approval": false,
    "owner_detail": {
      "isAssigned": false
    },
    "isRecordLinked": false,
    "step_variables": [],
    "response_mapping": {
      "options": [
        {
          "option": "test"
        }
      ],
      "duplicateOption": false,
      "customSuccessMessage": "Awaiting Playbook resumed successfully."
    },
    "email_notification": {
      "enabled": false,
      "smtpParameters": []
    },
    "inline_channel_list": [],
    "external_channel_list": [],
    "unauthenticated_input": false
  }
}
```

</details>

<details><summary>Example 2 (step:01526160-88de-4645-a1b8-a4e7ce20ffed)</summary>

```json
{
  "name": "confirm_auth",
  "arguments": {
    "type": "InputBased",
    "input": {
      "schema": {
        "title": "Are we sure we want to re-install to these device packages?",
        "description": "| FMG | ADOM  | DEVICE | VDOM | PACKAGE |\n| --- | --- | --- | --- | --- |\n{% for d in vars.fmg_devices -%} \n| {{d[0]}} | {{d[1]}} | {{d[2]}} | {{d[3]}} | {{d[4]}} |\n{% endfor -%}",
        "inputVariables": []
      }
    },
    "record": "",
    "owner_detail": {
      "isAssigned": false,
      "assignedToRecord": false
    },
    "isRecordLinked": false,
    "step_variables": [],
    "response_mapping": {
      "options": [
        {
          "option": "yes",
          "step_iri": "/api/3/workflow_steps/3417da3a-be23-40e3-9e18-8845526b3e83"
        },
        {
          "option": "no",
          "primary": true,
          "step_iri": "/api/3/workflow_steps/16080941-1b8e-4d33-ad06-848dbfdef747"
        }
      ],
      "duplicateOption": false
    },
    "email_notification": {
      "enabled": false,
      "smtpParameters": []
    },
    "inline_channel_list": [],
    "external_channel_list": [],
    "unauthenticated_input": false
  }
}
```

</details>

<details><summary>Example 3 (step:0185145e-790b-4e0c-87e7-aef6c6cb6219)</summary>

```json
{
  "name": "Manual Task to Action",
  "arguments": {
    "type": "DecisionBased",
    "input": {
      "schema": {
        "title": "Block {{vars.indicatorValue}}",
        "description": "<p>Configure your firewall to block:&nbsp;{{vars.indicatorValue}} and Click \"Block Completed\" to confirm the status.</p>\n<p>*Consider changing this step to automation using a connector. That would accelerate your response time and allow you to focus on advanced threats</p>",
        "inputVariables": []
      }
    },
    "record": "{{ vars.input.records[0][\"@id\"] }}",
    "resources": "indicators",
    "owner_detail": {
      "isAssigned": false
    },
    "step_variables": [],
    "response_mapping": {
      "options": [
        {
          "option": "Block Completed",
          "primary": true,
          "step_iri": "/api/3/workflow_steps/14c39b65-80a1-46bc-b498-83c3deb57b90"
        },
        {
          "option": "Unable to Block",
          "step_iri": "/api/3/workflow_steps/a6dba580-d8fc-407c-b1dd-f944ed3b48cf"
        }
      ],
      "duplicateOption": false
    }
  }
}
```

</details>

---

## `cybersponse.post_update`
_label: On Update_

**Occurrences**: 60 · **Category**: `cybersponse.abstract_trigger` · **UUID**: `9300bf69-5063-486d-b3a6-47eb9da24872`

Triggered on the updation of records that match the specified criteria.

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (3):

<details><summary>Example 1 (step:022d5dc5-10b0-470b-ae56-50ca572aa0c3)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "devices",
    "resources": [
      "devices"
    ],
    "step_variables": {
      "input": {
        "params": [],
        "records": [
          "{{vars.input.records[0]}}"
        ]
      },
      "ztpphase_input": "{{vars.input.records[0].zTPPhase.itemValue}}",
      "status_update_html": "<img src=\"data:image/gif;base64,R0lGODlhDQANAPQAAAAAABMTExUVFR8fHyoqKi4uLj8/P1FRUVVVVWBgYGpqam5ubn9/f5CQkJSUlJ6enqmpqa2trb+/v9DQ0NTU1ODg4Ovr6+/v7////wAAAAAAAAAAAAAAAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQFBAAAACH/C0ltYWdlTWFnaWNrDmdhbW1hPTAuNDU0NTQ1ACH+J0dJRiByZXNpemVkIG9uIGh0dHBzOi8vZXpnaWYuY29tL3Jlc2l6ZQAh/wt4bXAgZGF0YXhtcP8/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+IDx4OnhtcG10YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgNS42LWMxMTEgNzkuMTU4MzI1LCAyMDE1LzA5LzEwLTAxOjEwOjIwICAgICAgICAiPjxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53Lm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZjphYm91dD0iIiD/eG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIgeG1uczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1wOkNyZWF0b3JUb29sPSJBZG9iZSBQaG90b3Nob3AgQ0MgMjAxNSAoTWFjaW50b3MpIiB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOkFFODBBQUU0MUJBQjExRTY5MkUyRDRBNjI4MDc1/zM1RSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpBRTgwQUFFNTFCQUIxMUU5MkUyRDRBNjI4MDc1MzVFIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQieG1wLmlpZDpBRTgwQUFFMjFCQUIxMUU2OTJFMkQ0QTYyODA3NTM1RSIgc3RSZWY6ZG9jdW1lbnRJRD0ibXAu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\">"
    },
    "fieldbasedtrigger": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "object",
          "field": "zTPPhase",
          "value": "",
          "_value": {
            "@id": "",
            "display": "",
            "itemValue": ""
          },
          "operator": "changed"
        },
        {
          "type": "array",
          "field": "zTPPhase",
          "value": [
            "/api/3/picklists/32d675a0-1c16-476c-b249-8da4a05c3a84"
          ],
          "module": "zTPPhase",
          "display": "",
          "operator": "in",
          "template": "multiselectpicklist",
          "OPERATOR_KEY": "$",
          "useInOperator": true,
          "previousOperator": "in",
          "previousTemplate": "multiselectpicklist"
        }
      ]
    }
  }
}
```

</details>

<details><summary>Example 2 (step:04988c73-8fa0-4555-aac5-8f340f7a36d8)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "tasks",
    "step_variables": {
      "record": "{{vars.input.records[0]}}"
    },
    "fieldbasedtrigger": {
      "limit": 30,
      "logic": "OR",
      "filters": [
        {
          "type": "object",
          "field": "status",
          "value": "/api/3/picklists/343f4b67-e929-4205-bf95-ba5b70545fed",
          "_value": {
            "itemValue": "Completed"
          },
          "operator": "eq"
        },
        {
          "type": "object",
          "field": "status",
          "value": "/api/3/picklists/7bf6c03d-8e04-46d0-b392-febd78d72bad",
          "_value": {
            "display": "Skipped",
            "itemValue": "Skipped"
          },
          "operator": "eq"
        }
      ]
    }
  }
}
```

</details>

<details><summary>Example 3 (step:059571d8-6736-4086-b895-f1a279dc5218)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "netshot_target_outputs",
    "resources": [
      "netshot_target_outputs"
    ],
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": [],
        "records": [
          "{{vars.input.records[0]}}"
        ]
      }
    },
    "triggerOnSource": true,
    "fieldbasedtrigger": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "object",
          "field": "status",
          "value": "",
          "_value": {
            "@id": "",
            "display": "",
            "itemValue": ""
          },
          "operator": "changed"
        },
        {
          "type": "object",
          "field": "status",
          "value": "/api/3/picklists/7c18340b-215d-4396-b052-623e4c085727",
          "_value": {
            "@id": "/api/3/picklists/7c18340b-215d-4396-b052-623e4c085727",
            "display": "Running",
            "itemValue": "Running"
          },
          "operator": "eq"
        }
      ]
    },
    "triggerOnReplicate": false
  }
}
```

</details>

---

## `cybersponse.post_create`
_label: On Create_

**Occurrences**: 37 · **Category**: `cybersponse.abstract_trigger` · **UUID**: `ea155646-3821-4542-9702-b246da430a8d`

Triggered on the creation of records that match the specified criteria.

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (3):

<details><summary>Example 1 (step:0a690f0b-f0e5-477e-9c75-44ef16739e55)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "threat_actors",
    "resources": [
      "threat_actors"
    ],
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": [],
        "records": [
          "{{vars.input.records[0]}}"
        ]
      }
    },
    "triggerOnSource": true,
    "fieldbasedtrigger": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": []
    },
    "triggerOnReplicate": false
  }
}
```

</details>

<details><summary>Example 2 (step:0d3702a6-0950-4a03-a0f3-da6532db0af6)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "incidents",
    "resources": [
      "incidents"
    ],
    "step_variables": {
      "input": {
        "records": [
          "{{vars.input.records[0]}}"
        ]
      }
    },
    "fieldbasedtrigger": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "object",
          "field": "category",
          "value": "/api/3/picklists/8fea3472-6bd7-4bbf-a080-ca4e778617f8",
          "_value": {
            "display": "Other",
            "itemValue": "Other"
          },
          "operator": "eq"
        }
      ]
    }
  }
}
```

</details>

<details><summary>Example 3 (step:1c26d9d3-732a-430a-970c-69faa147c022)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "food",
    "resources": [
      "food"
    ],
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": [],
        "records": [
          "{{vars.input.records[0]}}"
        ]
      }
    },
    "triggerOnSource": true,
    "fieldbasedtrigger": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": [
        {
          "type": "primitive",
          "field": "calories",
          "value": 100,
          "operator": "gt",
          "_operator": "gt"
        }
      ]
    },
    "triggerOnReplicate": false
  }
}
```

</details>

---

## `Delay`
_label: Wait_

**Occurrences**: 30 · **Category**: `RunScript` · **UUID**: `6832e556-b9c7-497a-babe-feda3bd27dbf`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/delay"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:04127935-6e52-4b73-90ae-0755a65bfaa5)</summary>

```json
{
  "name": "Wait 1 sec",
  "arguments": {
    "rule": {
      "actions": [
        {
          "type": "resume_playbook",
          "enabled": true,
          "channel_uuid": "e2ce87c2-c55a-11ec-9d64-0242ac120002"
        }
      ],
      "is_active": true,
      "event_source": "crudhub"
    },
    "type": "TimeBased",
    "delay": {
      "days": 0,
      "hours": 0,
      "minutes": 0,
      "seconds": 1
    }
  }
}
```

</details>

<details><summary>Example 2 (step:1633ff49-05af-445f-92c8-e73f482c9044)</summary>

```json
{
  "name": "Wait 15 seconds",
  "arguments": {
    "rule": {
      "actions": [
        {
          "type": "resume_playbook",
          "enabled": true,
          "channel_uuid": "e2ce87c2-c55a-11ec-9d64-0242ac120002"
        }
      ],
      "is_active": true,
      "event_source": "crudhub"
    },
    "type": "TimeBased",
    "delay": {
      "days": 0,
      "hours": 0,
      "weeks": 0,
      "minutes": 0,
      "seconds": 15
    }
  }
}
```

</details>

<details><summary>Example 3 (step:2a3366d0-67e3-4823-9696-fa9e87b65838)</summary>

```json
{
  "name": "random_wait_1",
  "arguments": {
    "rule": {
      "actions": [
        {
          "type": "resume_playbook",
          "enabled": true,
          "channel_uuid": "e2ce87c2-c55a-11ec-9d64-0242ac120002"
        }
      ],
      "is_active": true,
      "event_source": "crudhub"
    },
    "type": "TimeBased",
    "delay": {
      "days": 0,
      "hours": 0,
      "minutes": 0,
      "seconds": "{{vars.random_wait}}"
    }
  }
}
```

</details>

---

## `CodeSnippet`
_label: Code Snippet_

**Occurrences**: 28 · **Category**: `RunScript` · **UUID**: `1fdd14cc-d6b4-4335-a3af-ab49c8ed2fd8`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/connector",
  "arguments": {
    "connector": "code-snippet"
  }
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:05ee52b9-dee1-4fa3-b333-64a0c5db8de1)</summary>

```json
{
  "name": "run python",
  "arguments": {
    "config": "1d6e2214-3ff0-4635-ac37-8dd7b5e0d7b9",
    "params": {
      "python_function": "import json\nfrom typing import Any, Dict, Optional, Tuple\n\nimport requests\nfrom urllib3.exceptions import InsecureRequestWarning\n\nrequests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)\n\n\ndef create_session(host: str, username: str, password: str, verify_ssl: bool = False) -> Dict[str, Any]:\n    \"\"\"\n    Create a session configuration dictionary\n    \n    Args:\n        host: FortiOS device IP or hostname\n        username: Authentication username\n        password: Authentication password\n        verify_ssl: Whether to verify SSL certificates\n    \n    Returns:\n        Session configuration dictionary\n    \"\"\"\n    return {\n        \"host\": host,\n        \"base_url\": f\"https://{host}/api/v2\",\n        \"username\": username,\n        \"password\": password,\n        \"verify_ssl\": verify_ssl,\n        \"session\": requests.Session(),\n        \"csrf_token\": None,\n        \"use_bearer_auth\": False,\n        \"status\": {},  # Status dictionary to collect messages\n    }\n\n\ndef login(config: Dict[str, Any]) -> bool:\n    \"\"\"\n    Authenticate and obtain CSRF token or access token\n    Automatically detects authentication method:\n    - If access_token in response: uses Bearer authentication\n    - If cookie found: uses X-CSRFTOKEN authentication\n    \n    Args:\n        config: Session configuration dictionary\n    \n    Returns:\n        True if login successful, False otherwise\n    \"\"\"\n    payload = {\n        \"username\": config[\"username\"],\n        \"password\": config[\"password\"],\n        \"secretkey\": config[\"password\"],\n        \"ack_post_disclaimer\": True,\n        \"request_key\": True,\n    }\n    \n    url = f\"{config['base_url']}/authentication\"\n    \n    try:\n        response = config[\"session\"].post(\n            url, \n            json=payload, \n            verify=config[\"verify_ssl\"]\n        )\n        response.raise_for_status()\n        \n        result = response.json() if response.content else {}\n        \n        # Check for session_key in response (alternative token field)\n        if result.get(\"session_key\"):\n            config[\"status\"][\"login\"] = \"Found session_key in response, using Bearer authentication\"\n            config[\"csrf_token\"] = result[\"session_key\"]\n            config[\"use_bearer_auth\"] = True\n            return True\n        \n        # Extract CSRF token from cookies (older versions - use X-CSRFTOKEN)\n        for cookie in config[\"session\"].cookies:\n            if \"ccsrf_token\" in cookie.name.lower():\n                config[\"csrf_token\"] = cookie.value\n                config[\"use_bearer_auth\"] = False\n                config[\"status\"][\"login\"] = f\"Login successful with cookie. Token: {config['csrf_token'][:10]}...\"\n                return True\n        \n        config[\"status\"][\"login\"] = \"Warning: No CSRF token or access_token found\"\n        return False\n        \n    except requests.exceptions.RequestException as e:\n        config[\"status\"][\"login\"] = f\"Login failed: {e}\"\n        return False\n\n\ndef logout(config: Dict[str, Any]) -> bool:\n    \"\"\"\n    End the session\n    \n    Args:\n        config: Session configuration dictionary\n    \n    Returns:\n        True if logout successful, False otherwise\n    \"\"\"\n    if not config[\"csrf_token\"]:\n        return False\n    \n    url = f\"{config['base_url']}/authentication\"\n    headers = {\"Content-Type\": \"application/json\"}\n    \n    # Use appropriate authentication header\n    if config[\"use_bearer_auth\"]:\n        headers[\"Authorization\"] = f\"Bearer {config['csrf_token']}\"\n    else:\n        headers[\"X-CSRFTOKEN\"] = config[\"csrf_token\"]\n    \n    try:\n        response = config[\"session\"].delete(\n            url,\n            headers=headers,\n            verify=config[\"verify_ssl\"]\n        )\n        response.raise_for_status()\n        \n        config[\"session\"].close()\n        config[\"csrf_token\"] = None\n        config[\"use_bearer_auth\"] = False\n        config[\"status\"][\"logout\"] = \"Logout successful\"\n        \n        return True\n        \n    except requests.exceptions.RequestException as e:\n        config[\"status\"][\"logout\"] = f\"Logout failed: {e}\"\n        return False\n\n\ndef make_request(\n    config: Dict[str, Any],\n    method: str,\n    endpoint: str,\n    **kwargs\n) -> Optional[Dict[str, Any]]:\n    \"\"\"\n    Generic request handler\n    \n    Args:\n        config: Session configuration dictionary\n        method: HTTP method (GET, POST, PUT, DELETE)\n        endpoint: API endpoint (e.g., '/cmdb/firewall/address')\n        **kwargs: Additional arguments to pass to requests\n    \n    Returns:\n        Response JSON or None if failed\n    \"\"\"\n    url = f\"{config['base_url']}{endpoint}\"\n    \n    # Set default headers\n    headers = kwargs.pop(\"headers\", {})\n    headers.setdefault(\"Content-Type\", \"application/json\")\n    \n    # Use appropriate authentication header\n    if config[\"csrf_token\"]:\n        if config[\"use_bearer_auth\"]:\n            headers[\"Authorization\"] = f\"Bearer {config['csrf_token']}\"\n        else:\n            headers[\"X-CSRFTOKEN\"] = config[\"csrf_token\"]\n    \n    kwargs[\"headers\"] = headers\n    kwargs.setdefault(\"verify\", config[\"verify_ssl\"])\n    \n    try:\n        response = config[\"session\"].request(method, url, **kwargs)\n        response.raise_for_status()\n        return response.json() if response.content else {}\n    except requests.exceptions.RequestException as e:\n        # Store error in status dictionary with a unique key\n        error_key = f\"request_error_{method}_{endpoint.replace('/', '_')}\"\n        config[\"status\"][error_key] = f\"Request failed: {e}\"\n        return None\n\n\n# CMDB Operations (Configuration Database)\n\n\ndef get(config: Dict[str, Any], path: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:\n    \"\"\"\n    Generic GET operation for CMDB\n    \n    Args:\n        config: Session configuration dictionary\n        path: Resource path (e.g., 'system/interface', 'firewall/address')\n        params: Query parameters\n    \n    Returns:\n        Response data or None\n    \"\"\"\n    return make_request(config, \"GET\", f\"/cmdb/{path}\", params=params)\n\n\ndef create(config: Dict[str, Any], path: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:\n    \"\"\"\n    Generic CREATE operation for CMDB\n    \n    Args:\n        config: Session configuration dictionary\n        path: Resource path (e.g., 'firewall/address')\n        data: Object data\n    \n    Returns:\n        Response data or None\n    \"\"\"\n    return make_request(config, \"POST\", f\"/cmdb/{path}\", json=data)\n\n\ndef update(\n    config: Dict[str, Any],\n    path: str,\n    name: str,\n    data: Dict[str, Any]\n) -> Optional[Dict[str, Any]]:\n    \"\"\"\n    Generic UPDATE operation for CMDB\n    \n    Args:\n        config: Session configuration dictionary\n        path: Resource path\n        name: Object name/identifier\n        data: Updated data\n    \n    Returns:\n        Response data or None\n    \"\"\"\n    return make_request(config, \"PUT\", f\"/cmdb/{path}/{name}\", json=data)\n\n\ndef delete(config: Dict[str, Any], path: str, name: str) -> Optional[Dict[str, Any]]:\n    \"\"\"\n    Generic DELETE operation for CMDB\n    \n    Args:\n        config: Session configuration dictionary\n        path: Resource path\n        name: Object name/identifier\n    \n    Returns:\n        Response data or None\n    \"\"\"\n    return make_request(config, \"DELETE\", f\"/cmdb/{path}/{name}\")\n\n\n# Convenience functions for common operations\n\n\ndef get_interfaces(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:\n    \"\"\"Get all system interfaces\"\"\"\n    return get(config, \"system/interface\")\n\n\ndef get_addresses(config: Dict[str, Any], name: Optional[str] = None) -> Optional[Dict[str, Any]]:\n    \"\"\"Get firewall address objects\"\"\"\n    path = f\"firewall/address/{name}\" if name else \"firewall/address\"\n    return get(config, path.replace(\"//\", \"/\"))\n\n\ndef create_address(\n    config: Dict[str, Any],\n    name: str,\n    subnet: str,\n    address_type: str = \"ipmask\"\n) -> Optional[Dict[str, Any]]:\n    \"\"\"Create a firewall address object\"\"\"\n    data = {\n        \"name\": name,\n        \"subnet\": subnet,\n        \"type\": address_type,\n    }\n    return create(config, \"firewall/address\", data)\n\n\ndef create_address_group(\n    config: Dict[str, Any],\n    name: str,\n    members: list\n) -> Optional[Dict[str, Any]]:\n    \"\"\"Create a firewall address group\"\"\"\n    data = {\n        \"name\": name,\n        \"member\": [{\"name\": member} for member in members],\n    }\n    return create(config, \"firewall/addrgrp\", data)\n\n\ndef get_policies(config: Dict[str, Any], policy_id: Optional[int] = None) -> Optional[Dict[str, Any]]:\n    \"\"\"Get firewall policies\"\"\"\n    path = f\"firewall/policy/{policy_id}\" if policy_id else \"firewall/policy\"\n    return get(config, path.replace(\"//\", \"/\"))\n\n\ndef main():\n    \"\"\"Example usage demonstrating the functional API\"\"\"\n    host = \"198.51.100.10\"\n    username = \"admin\"\n    password = \"fortinet\"\n    \n    # Create session configuration\n    config = create_session(host, username, password)\n    \n    if not login(config):\n        print(json.dumps(config[\"status\"], indent=2))\n        exit(1)\n    \n    try:\n        # Get interfaces\n        interfaces = get_interfaces(config)\n        if interfaces:\n            config[\"status\"][\"get_interfaces\"] = \"Interfaces retrieved successfully\"\n            config[\"status\"][\"interfaces_data\"] = interfaces\n        \n        # Create address object\n        address = create_address(config, \"TEST_SUBNET\", \"10.0.0.0 255.255.255.0\")\n        if address:\n            config[\"status\"][\"create_address\"] = f\"Address created successfully\"\n            config[\"status\"][\"address_data\"] = address\n            \n            # Delete the created address\n            if \"mkey\" in address:\n                deleted = delete(config, \"firewall/address\", address[\"mkey\"])\n                if deleted:\n                    config[\"status\"][\"delete_address\"] = \"Address deleted successfully\"\n                    config[\"status\"][\"delete_data\"] = deleted\n    \n    finally:\n        logout(config)\n        # Print all status information at the end\n        print(json.dumps(config[\"status\"], indent=2))\n\nmain()"
    },
    "version": "2.1.4",
    "connector": "code-snippet",
    "operation": "python_inline_code_editor",
    "operationTitle": "Execute Python Code",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:1a0ad736-f23e-40f5-8f58-10c6363c5dc1)</summary>

```json
{
  "name": "Create first name and time message",
  "arguments": {
    "config": "74c7e349-a99d-44ac-a576-8c1b158fc364",
    "params": {
      "python_function": "approver = \"{{vars.steps.Show_data_for_approval.username}}\"\napproval_time = \"{{vars.steps.Show_data_for_approval.datetime}}\"\n\napprover_first_name = approver.split()[0]\n\napproval_message = f\"{approver_first_name} approved the food at {approval_time}\"\n\nprint(approval_message)\n"
    },
    "version": "2.1.4",
    "connector": "code-snippet",
    "operation": "python_inline_code_editor",
    "operationTitle": "Execute Python Code",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:39ec5cef-f36e-4158-bd3d-d3695333839b)</summary>

```json
{
  "name": "sample_python",
  "arguments": {
    "config": "1d6e2214-3ff0-4635-ac37-8dd7b5e0d7b9",
    "params": {
      "python_function": "import ipaddress\nimport json\nfrom datetime import datetime\n\ndef main():\n    \"\"\"Main function to run all analyses and return results dict\"\"\"\n    \n    # Sample IP addresses from your PsExec detection\n    ip_addresses = [\n        \"192.168.10.31\",  # Source IP from PsExec activity\n        \"192.168.10.10\",  # Destination IP (DC1)\n        \"10.0.1.100\",     # Additional test IP\n        \"172.16.5.50\",    # Private network IP\n        \"8.8.8.8\",        # Public DNS\n        \"2001:db8::1\"     # IPv6 example\n    ]\n    \n    # Initialize results dictionary\n    results = {\n        \"analysis_time\": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),\n        \"total_ips_analyzed\": len(ip_addresses),\n        \"ip_analysis\": [],\n        \"network_analysis\": [],\n        \"psexec_analysis\": {},\n        \"security_findings\": [],\n        \"network_operations\": {}\n    }\n    \n    # Analyze each IP address\n    for ip_str in ip_addresses:\n        try:\n            ip = ipaddress.ip_address(ip_str)\n            \n            analysis = {\n                \"ip_address\": str(ip),\n                \"version\": f\"IPv{ip.version}\",\n                \"is_private\": ip.is_private,\n                \"is_global\": ip.is_global,\n                \"is_loopback\": ip.is_loopback,\n                \"is_multicast\": ip.is_multicast,\n                \"is_reserved\": ip.is_reserved\n            }\n            \n            if ip.version == 4:\n                analysis[\"is_link_local\"] = ip.is_link_local\n                analysis[\"packed\"] = ip.packed.hex()\n                \n                if ip.is_private:\n                    if str(ip).startswith('10.'):\n                        analysis[\"rfc1918_class\"] = \"Class A (10.0.0.0/8)\"\n                    elif str(ip).startswith('172.'):\n                        analysis[\"rfc1918_class\"] = \"Class B (172.16.0.0/12)\"\n                    elif str(ip).startswith('192.168'):\n                        analysis[\"rfc1918_class\"] = \"Class C (192.168.0.0/16)\"\n            \n            results[\"ip_analysis\"].append(analysis)\n            \n        except ValueError as e:\n            results[\"ip_analysis\"].append({\n                \"ip_address\": ip_str,\n                \"error\": str(e)\n            })\n    \n    # Analyze network ranges\n    networks = [\n        \"192.168.10.0/24\",\n        \"10.0.0.0/8\", \n        \"172.16.0.0/16\",\n        \"2001:db8::/32\"\n    ]\n    \n    for net_str in networks:\n        try:\n            network = ipaddress.ip_network(net_str)\n            \n            net_analysis = {\n                \"network\": str(network),\n                \"network_address\": str(network.network_address),\n                \"broadcast_address\": str(network.broadcast_address),\n                \"netmask\": str(network.netmask),\n                \"total_addresses\": network.num_addresses\n            }\n            \n            if network.version == 4:\n                net_analysis[\"usable_hosts\"] = network.num_addresses - 2\n            \n            # Check if PsExec IPs are in this network\n            psexec_source = ipaddress.ip_address(\"192.168.10.31\")\n            psexec_dest = ipaddress.ip_address(\"192.168.10.10\")\n            \n            net_analysis[\"contains_psexec_source\"] = psexec_source in network\n            net_analysis[\"contains_psexec_dest\"] = psexec_dest in network\n            \n            results[\"network_analysis\"].append(net_analysis)\n            \n        except ValueError as e:\n            results[\"network_analysis\"].append({\n                \"network\": net_str,\n                \"error\": str(e)\n            })\n    \n    # PsExec specific analysis\n    source_ip = ipaddress.ip_address(\"192.168.10.31\")\n    dest_ip = ipaddress.ip_address(\"192.168.10.10\")\n    \n    results[\"psexec_analysis\"] = {\n        \"source_ip\": str(source_ip),\n        \"destination_ip\": str(dest_ip),\n        \"both_private\": source_ip.is_private and dest_ip.is_private,\n        \"ip_distance\": abs(int(source_ip) - int(dest_ip)),\n        \"same_network\": None\n    }\n    \n    # Find common network\n    for prefix_len in range(24, 31):\n        try:\n            source_net = ipaddress.ip_network(f\"{source_ip}/{prefix_len}\", strict=False)\n            if dest_ip in source_net:\n                results[\"psexec_analysis\"][\"same_network\"] = str(source_net)\n                results[\"psexec_analysis\"][\"subnet_prefix\"] = prefix_len\n                break\n        except:\n            continue\n    \n    # Security analysis\n    security_findings = []\n    \n    if source_ip.is_private and dest_ip.is_private:\n        security_findings.append(\"Both IPs are private (internal network)\")\n    \n    if str(dest_ip).endswith('.10'):\n        security_findings.append(\"Destination ends in .10 (common server pattern)\")\n    \n    if str(source_ip).endswith('.31'):\n        security_findings.append(\"Source ends in .31 (workstation range)\")\n    \n    results[\"security_findings\"] = security_findings\n    \n    # Network operations demo\n    demo_network = ipaddress.ip_network(\"192.168.10.0/28\")\n    hosts = list(demo_network.hosts())\n    \n    results[\"network_operations\"] = {\n        \"demo_network\": str(demo_network),\n        \"first_5_hosts\": [str(host) for host in hosts[:5]],\n        \"total_hosts\": len(hosts)\n    }\n    \n    # Subnet operations\n    large_net = ipaddress.ip_network(\"192.168.0.0/16\")\n    subnets = list(large_net.subnets(new_prefix=24))\n    \n    results[\"network_operations\"][\"subnet_demo\"] = {\n        \"original_network\": str(large_net),\n        \"total_subnets\": len(subnets),\n        \"first_3_subnets\": [str(subnet) for subnet in subnets[:3]]\n    }\n    \n    return results\n\n\nanalysis_results = main()\nprint(analysis_results)"
    },
    "version": "2.1.3",
    "connector": "code-snippet",
    "operation": "python_inline_code_editor",
    "operationTitle": "Execute Python Code",
    "step_variables": []
  }
}
```

</details>

---

## `SendMail`
_label: Send Email_

**Occurrences**: 22 · **Category**: `RunScript` · **UUID**: `4c0019b2-055c-44d0-968c-678a0c2d762e`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/connector",
  "arguments": {
    "from_str": "admin@example.com",
    "connector": "smtp"
  }
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:09784943-df4e-4ace-9a49-b5609cf15260)</summary>

```json
{
  "name": "Send Email",
  "arguments": {
    "config": "88c3d39c-2fa9-4731-b00d-29815008f17c",
    "params": {
      "cc": "",
      "to": "{{vars.toEmailAddress}}",
      "bcc": "",
      "from": "{{vars.fromEmailAddress}}",
      "type": "Manual Input",
      "content": "Incident Export at {{ arrow.utcnow() }}",
      "subject": "Incident Export Attached",
      "iri_list": "",
      "body_type": "Plain Text",
      "file_name": "{{ vars.resultsFileName }}.zip",
      "file_path": "{{ vars.resultsFileName }}.zip"
    },
    "version": "2.6.0",
    "from_str": "soc@cybersponse.com",
    "connector": "smtp",
    "operation": "send_email_new",
    "operationTitle": "Send Email",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:1d7f98b5-2700-4481-8139-16d5f1bbe5ad)</summary>

```json
{
  "name": "SEND_EMAIL",
  "arguments": {
    "config": "88c3d39c-2fa9-4731-b00d-29815008f17c",
    "params": {
      "cc": "",
      "to": "mborrow@fortinet.com",
      "bcc": "",
      "from": "soarlab@wavespray.net",
      "type": "Manual Input",
      "content": "FAC instance 1 is not responding appropriately.  FGT has been changed to FAC instance 2.",
      "subject": "FAC ALERT!",
      "iri_list": "",
      "body_type": "Plain Text",
      "file_name": "",
      "file_path": ""
    },
    "version": "2.6.0",
    "from_str": "admin@example.com",
    "connector": "smtp",
    "operation": "send_email_new",
    "operationTitle": "Send Email (Advanced)",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:271207fa-b5b6-4e8f-997e-1f7903c0baf4)</summary>

```json
{
  "name": "Send Email step",
  "arguments": {
    "config": "88c3d39c-2fa9-4731-b00d-29815008f17c",
    "version": "2.6.0",
    "from_str": "admin@example.com",
    "connector": "smtp",
    "step_variables": []
  }
}
```

</details>

---

## `cybersponse.api_call`
_label: Custom API Endpoint_

**Occurrences**: 19 · **Category**: `cybersponse.abstract_trigger` · **UUID**: `df26c7a2-4166-4ca5-91e5-548e24c01b5f`

Triggered from an API request to a custom endpoint.

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (3):

<details><summary>Example 1 (step:06a00316-ca7e-4380-ad15-5f20948239ea)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "route": "splunkAlert",
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": {
          "api_body": "{{vars.request.data}}",
          "api_params": "{{vars.request.params}}",
          "request_data": "{{ vars.request_data }}"
        }
      },
      "sourcedata": "{%if 'data' in vars.request %}\n{%set _dummy = vars.request.data.update({'uri': vars.request.uri})%}\n{%if 'result' in vars.request.data %}\n{%if vars.request.data.result is not string %}\n{%for k,v in vars.request.data.result.items()%}\n{%set _dummy= vars.request.data.update({k:v})%}\n{%endfor%}\n{%endif%}\n{%set _dummy= vars.request.data.pop('result') %}\n{%endif%}\n{{vars.request.data}}\n{%else%}\n{%set _dummy = vars.request_data.update( { \"route\": vars.route})%}{{vars.request_data}}\n{%endif%}"
    },
    "triggerOnSource": true,
    "triggerOnReplicate": false,
    "authentication_methods": [
      ""
    ]
  }
}
```

</details>

<details><summary>Example 2 (step:13d2e91e-5592-478d-89af-de76c84f13b5)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "route": "fetch_emails_exchange",
    "step_variables": {
      "input": {
        "params": {
          "api_body": "{{vars.request.data}}"
        }
      }
    },
    "authentication_methods": [
      ""
    ]
  }
}
```

</details>

<details><summary>Example 3 (step:25f63132-eff9-4987-927b-649ce4b2bfc1)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "route": "deferred/restart_service",
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": {
          "api_body": "{{vars.request.data}}",
          "api_params": "{{vars.request.params}}"
        }
      }
    },
    "triggerOnSource": true,
    "triggerOnReplicate": false,
    "authentication_methods": [
      "anonymous"
    ]
  }
}
```

</details>

---

## `IngestBulkFeed`
_label: Ingest Bulk Feed_

**Occurrences**: 12 · **Category**: `WorkflowReference` · **UUID**: `7b221880-716b-4726-a2ca-5e568d330b3e`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/ingest_bulk_feed"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:09b80f07-d280-4c93-b5ae-c1efec41968a)</summary>

```json
{
  "name": "Create Record",
  "arguments": {
    "for_each": {
      "item": "{{vars.input.params.ingestedData}}",
      "__bulk": true,
      "parallel": false,
      "condition": "",
      "batch_size": 8000
    },
    "resource": {
      "tLP": "{{vars.tlp_resolved}}",
      "name": "{{vars.item.name}}",
      "label": "{{vars.item.labels | toJSON}}",
      "value": "{{ vars.item.name.split(\": \")[1].strip() }}",
      "source": "FortiGuard Threat Intelligence",
      "created": "{% if vars.item.created %}{{arrow.get(vars.item.created).int_timestamp}}{% endif %}",
      "pattern": "{{vars.item.pattern}}",
      "modified": "{% if vars.item.modified %}{{arrow.get(vars.item.modified).int_timestamp}}{% endif %}",
      "sourceId": "{{ vars.item.id.split(\"--\")[-1] }}",
      "__replace": "true",
      "expiresOn": "{% if vars.expiry %}{% if vars.item.valid_until %}{{ arrow.get(vars.item.valid_until).int_timestamp + (vars.expiry | int)*24*60*60 }}{% else %}{{ arrow.utcnow().int_timestamp + (vars.expiry | int)*24*60*60 }}{% endif %}{% endif %}",
      "validFrom": "{% if vars.item.valid_from %}{{arrow.get(vars.item.valid_from).int_timestamp}}{% endif %}",
      "confidence": "{% if vars.item.confidence %}{{ vars.item.confidence }}{% else %}{{ vars.confidence }}{% endif %}",
      "recordTags": "{% if vars.item.labels | length > 1 %}{{ vars.item.labels[1].split(\"tags:\")[-1].split(\",\") }}{% endif %}",
      "reputation": "{{vars.reputation_resolved}}",
      "sourceData": "{{ vars.item | toJSON}}",
      "typeOfFeed": "{{ vars.item.name.split(\": \")[0].strip() | resolveRange(vars.typeOfFeed_map) }}",
      "validUntil": "{% if vars.item.valid_until %}{{arrow.get(vars.item.valid_until).int_timestamp + (vars.expiry | int)*24*60*60 }}{% else %}{{ arrow.utcnow().int_timestamp + (vars.expiry | int)*24*60*60 }}{% endif %}",
      "description": "{{ vars.item.description }}",
      "patternType": "{{vars.item.pattern_type}}",
      "threatTypes": "{% if vars.item.labels and 'threat_types' in vars.item.labels[0] %}{% set types=[] %}{% for type in vars.item.labels[0].split(\"threat_types:\")[-1].split(\",\") %}{% if type | resolveRange(vars.threatTypes_map) %}{% set _temp=types.append(type | resolveRange(vars.threatTypes_map)) %}{% else %}{% set _temp=types.append(\"Threat Type\" | picklist(\"Unknown\", \"uuid\")) %}{% endif %}{% endfor %}{{types}}{% else %}None{% endif %}",
      "indicatorTypes": "{% if vars.item.pattern.split(\":\")[0][1:].strip() == \"autonomous-system\" %}[\"network-traffic\"]{% else %}{{[vars.item.pattern.split(\":\")[0][1:].strip()] | toJSON}}{% endif %}",
      "patternVersion": "{{vars.item.spec_version}}",
      "killChainPhases": "{% if vars.item.kill_chain_phases %}['{{ vars.item.kill_chain_phases[0].phase_name | resolveRange(vars.killChainPhases_map) }}']{% else %}None{% endif %}"
    },
    "_showJson": false,
    "collection": "/api/ingest-feeds/threat_intel_feeds",
    "__recommend": [],
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:2072b79a-023d-40fe-b345-91fe6b686535)</summary>

```json
{
  "name": "Create Record",
  "arguments": {
    "for_each": {
      "item": "{{vars.input.params.ingestedData}}",
      "__bulk": true,
      "parallel": false,
      "condition": "",
      "batch_size": 8000
    },
    "resource": {
      "tLP": "{{vars.tlp_resolved}}",
      "name": "{{vars.item.name}}",
      "label": "{{vars.item.labels | toJSON}}",
      "value": "{{ vars.item.name.split(\": \")[1].strip() }}",
      "source": "FortiGuard Threat Intelligence",
      "created": "{% if vars.item.created %}{{arrow.get(vars.item.created).int_timestamp}}{% endif %}",
      "pattern": "{{vars.item.pattern}}",
      "modified": "{% if vars.item.modified %}{{arrow.get(vars.item.modified).int_timestamp}}{% endif %}",
      "sourceId": "{{ vars.item.id.split(\"--\")[-1] }}",
      "__replace": "true",
      "expiresOn": "{% if vars.expiry %}{% if vars.item.valid_until %}{{ arrow.get(vars.item.valid_until).int_timestamp + (vars.expiry | int)*24*60*60 }}{% else %}{{ arrow.utcnow().int_timestamp + (vars.expiry | int)*24*60*60 }}{% endif %}{% endif %}",
      "validFrom": "{% if vars.item.valid_from %}{{arrow.get(vars.item.valid_from).int_timestamp}}{% endif %}",
      "confidence": "{% if vars.item.confidence %}{{ vars.item.confidence }}{% else %}{{ vars.confidence }}{% endif %}",
      "recordTags": "{% if vars.item.labels | length > 1 %}{{ vars.item.labels[1].split(\"tags:\")[-1].split(\",\") }}{% endif %}",
      "reputation": "{{vars.reputation_resolved}}",
      "sourceData": "{{ vars.item | toJSON}}",
      "typeOfFeed": "{{ vars.item.name.split(\": \")[0].strip() | resolveRange(vars.typeOfFeed_map) }}",
      "validUntil": "{% if vars.item.valid_until %}{{arrow.get(vars.item.valid_until).int_timestamp + (vars.expiry | int)*24*60*60 }}{% else %}{{ arrow.utcnow().int_timestamp + (vars.expiry | int)*24*60*60 }}{% endif %}",
      "description": "{{ vars.item.description }}",
      "patternType": "{{vars.item.pattern_type}}",
      "threatTypes": "{% if vars.item.labels and 'threat_types' in vars.item.labels[0] %}{% set types=[] %}{% for type in vars.item.labels[0].split(\"threat_types:\")[-1].split(\",\") %}{% if type | resolveRange(vars.threatTypes_map) %}{% set _temp=types.append(type | resolveRange(vars.threatTypes_map)) %}{% else %}{% set _temp=types.append(\"Threat Type\" | picklist(\"Unknown\", \"uuid\")) %}{% endif %}{% endfor %}{{types}}{% else %}None{% endif %}",
      "indicatorTypes": "{% if vars.item.pattern.split(\":\")[0][1:].strip() == \"autonomous-system\" %}[\"network-traffic\"]{% else %}{{[vars.item.pattern.split(\":\")[0][1:].strip()] | toJSON}}{% endif %}",
      "patternVersion": "{{vars.item.spec_version}}",
      "killChainPhases": "{% if vars.item.kill_chain_phases %}['{{ vars.item.kill_chain_phases[0].phase_name | resolveRange(vars.killChainPhases_map) }}']{% else %}None{% endif %}"
    },
    "_showJson": false,
    "collection": "/api/ingest-feeds/threat_intel_feeds",
    "__recommend": [],
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:42d867ee-38ec-48b5-b470-c3ad28ab5217)</summary>

```json
{
  "name": "Bulk Ingest Vulnerability Records",
  "arguments": {
    "when": "{{vars.steps.Fetch_Asset_Vulnerabilities.data | length > 0}}",
    "for_each": {
      "item": "{{vars.vulnerabilityData}}",
      "__bulk": true,
      "parallel": false,
      "condition": "",
      "batch_size": 100
    },
    "resource": {
      "cvss": "{{vars.item.info['risk_information']['cvss_base_score']}}",
      "name": "{{vars.item.info['plugin_details']['name']}}",
      "risk": "{{vars.item.info['risk_information']['risk_factor']}}",
      "cveId": "{{ vars.item.info['reference_information'] | json_query(\"[?contains(name, 'cve')].values\") | flatten(levels=1) | join(', ')}}",
      "status": "/api/3/picklists/e001be1d-d050-473c-a82d-003bf14c4b1b",
      "severity": "{% set _cvss_score = vars.item.info['risk_information']['cvss_base_score'] %}{{ ((_cvss_score | float | round(0, 'ceil')) if (_cvss_score | float < 1.0) else (_cvss_score | float | round(0, 'floor'))) | resolveRange(vars.vulnSeverityMapping)}}",
      "__replace": "",
      "cvssVector": "{{vars.item.info['risk_information']['cvss_vector']}}",
      "pluginName": "{{vars.item.info['plugin_details']['name']}}",
      "pluginType": "{{vars.item.info['plugin_details'].type}}",
      "sourceData": "{{vars.item | toJSON}}",
      "cvss3Vector": "{{vars.item.info['risk_information']['cvss3_vector']}}",
      "description": "### Synopsis\n{{vars.item.info.synopsis}}\n\n### Description\n{{vars.item.info.description}}\n\n### Solution\n{{vars.item.info.solution}}\n",
      "lastSeenDate": "{{ arrow.get(vars.item.info.discovery['seen_last']).timestamp }}",
      "pluginFamily": "{{vars.item.info['plugin_details'].family}}",
      "firstSeenDate": "{{ arrow.get(vars.item.info.discovery['seen_first']).timestamp }}",
      "pluginVersion": "{{vars.item.info['plugin_details'].version}}",
      "cvss3BaseScore": "{{vars.item.info['risk_information']['cvss3_base_score']}}",
      "vulnerabilityId": "{{vars.item.info['plugin_details']['plugin_id']}}",
      "cvssTemporalScore": "{{vars.item.info['risk_information']['cvss_temporal_score']}}",
      "cvss3TemporalScore": "{{vars.item.info['risk_information']['cvss3_temporal_score']}}",
      "cvssTemporalVector": "{{vars.item.info['risk_information']['cvss_temporal_vector']}}",
      "cvss3TemporalVector": "{{vars.item.info['risk_information']['cvss3_temporal_vector']}}",
      "pluginPublicationDate": "{{arrow.get(vars.item.info.plugin_details.publication_date).format('MM/DD/YYYY hh:mm A')}}",
      "pluginModificationDate": "{{arrow.get(vars.item.info.plugin_details.modification_date).format('MM/DD/YYYY hh:mm A')}}"
    },
    "_showJson": false,
    "collection": "/api/ingest-feeds/vulnerabilities",
    "__recommend": [],
    "step_variables": []
  }
}
```

</details>

---

## `ManualTask`
_label: Manual Task_

**Occurrences**: 8 · **Category**: `RunScript` · **UUID**: `dc6ac63d-c5a5-472f-9eb4-6b18473a98b8`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/wait"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:2679c714-89e9-4226-9b6d-2d70ddc2123b)</summary>

```json
{
  "name": "Write a Procedure",
  "arguments": {
    "message": {
      "tenant": "",
      "content": "<p>Please check task -&nbsp;<span style=\"text-decoration: underline;\"><strong>{{vars.result.id}}</strong></span>&nbsp;&nbsp;to&nbsp;write a procedure for detecting, investigating and remediating identified malware</p>",
      "records": "",
      "parentstepid": "/api/3/workflow_steps/fd5cc6e6-4b72-47d1-b8fe-01e294d2843d"
    },
    "resource": {
      "name": "Write a Procedure to Remove the Malware",
      "status": "/api/3/picklists/7669725a-28cc-4b19-98a3-9ca71e0f88f4",
      "priority": "/api/3/picklists/90088ebe-0a7d-4aa6-9c9c-93b937a4e4f8",
      "incidents": "['{{vars.input.records[0]['@id']}}']",
      "description": "<p>Reference Links</p>\n<ul>\n<li>Remove malware from&nbsp;<a href=\"https://heimdalsecurity.com/blog/malware-removal/\">window machine</a>&nbsp;</li>\n<li>Remove malware from&nbsp;<a href=\"https://www.techrepublic.com/article/how-to-scan-and-clean-malware-from-a-linux-server/\">Linux machine</a>&nbsp;</li>\n</ul>",
      "assignedToPerson": "/api/3/people/3451141c-bac6-467c-8d72-85e0fab569ce"
    },
    "collection": "tasks",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:35b7ed97-e05f-4fa2-a7c5-a33dd772b733)</summary>

```json
{
  "name": "Restore Corrupted Files",
  "arguments": {
    "message": {
      "tenant": "",
      "content": "<p>Please check task -&nbsp;<span style=\"text-decoration: underline;\"><strong>{{vars.result.id}}</strong></span>&nbsp;&nbsp;to identify and restore corrupted files on customer systems</p>",
      "records": "",
      "parentstepid": "/api/3/workflow_steps/cd251ad8-eaf9-4d15-b870-846602a8e7da"
    },
    "resource": {
      "name": "Identify and Restore Possibly Corrupted Files",
      "status": "/api/3/picklists/7669725a-28cc-4b19-98a3-9ca71e0f88f4",
      "priority": "/api/3/picklists/90088ebe-0a7d-4aa6-9c9c-93b937a4e4f8",
      "incidents": "['{{vars.input.records[0]['@id']}}']",
      "description": "<p>&nbsp;Reference Links</p>\n<ul>\n<li>Restore&nbsp;<a href=\"https://support.microsoft.com/en-in/help/929833/use-the-system-file-checker-tool-to-repair-missing-or-corrupted-system\">Windows corrupted file</a></li>\n<li>Restore<a href=\"https://www.tecmint.com/fsck-repair-file-system-errors-in-linux/\"> Linux corrupted file</a></li>\n</ul>",
      "assignedToPerson": "/api/3/people/3451141c-bac6-467c-8d72-85e0fab569ce"
    },
    "collection": "tasks",
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 3 (step:4c9e9853-c575-4725-8bc9-73fc02eea4fb)</summary>

```json
{
  "name": "Asset Isolation Task",
  "arguments": {
    "resource": {
      "name": "Task for Asset Isolation",
      "status": "/api/3/picklists/7669725a-28cc-4b19-98a3-9ca71e0f88f4",
      "tenant": "/api/3/tenants/b3a700f7-00be-4ef9-90c6-3c8fe6e1be63",
      "priority": "/api/3/picklists/90088ebe-0a7d-4aa6-9c9c-93b937a4e4f8",
      "incidents": "{{vars.input.params['incident_iri']}}",
      "description": "Isolate the Asset",
      "assignedToPerson": "/api/3/people/3451141c-bac6-467c-8d72-85e0fab569ce"
    },
    "collection": "tasks",
    "step_variables": []
  }
}
```

</details>

---

## `ApprovalManualInput`
_label: Approval_

**Occurrences**: 4 · **Category**: `RunScript` · **UUID**: `a19333c2-c822-11ed-afa1-0242ac120002`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/manual_input"
}
```

**Real-world examples** (3):

<details><summary>Example 1 (step:222fdf48-d88c-490c-9942-df52f9195db1)</summary>

```json
{
  "name": "Seek Admins Permission",
  "arguments": {
    "type": "InputBased",
    "input": {
      "schema": {
        "title": "Approval - Deploy Patch",
        "description": "Please approve deploying patch {{vars.request.data.patchID}} on Asset:{{vars.request.data.records[0].hostname}}",
        "inputVariables": []
      }
    },
    "record": "{{ vars.input.records[0][\"@id\"] }}",
    "agent_id": null,
    "resources": "assets",
    "is_approval": true,
    "owner_detail": {
      "isAssigned": true,
      "assignedToTeam": [],
      "assignedToField": null,
      "emailRecipients": "",
      "assignedToPerson": [
        {
          "iri": "/api/3/people/3451141c-bac6-467c-8d72-85e0fab569ce",
          "lastname": "Admin",
          "firstname": "CS"
        }
      ],
      "assignedToRecord": false
    },
    "isRecordLinked": false,
    "step_variables": [],
    "response_mapping": {
      "options": [
        {
          "option": "Approve",
          "primary": true,
          "step_iri": "/api/3/workflow_steps/7e569a7a-0ae1-41b3-8e98-80d94b413193"
        },
        {
          "option": "Reject",
          "primary": false,
          "step_iri": null
        }
      ],
      "connecteStepsLength": 1,
      "customSuccessMessage": "Awaiting Playbook resumed successfully."
    },
    "email_notification": {
      "enabled": false,
      "smtpParameters": []
    },
    "customEmailExternal": false,
    "inline_channel_list": [],
    "external_channel_list": [],
    "unauthenticated_input": false,
    "external_email_subject": null,
    "internal_email_subject": "A FortiSOAR playbook is requesting your input",
    "custom_email_body_external": null,
    "external_email_attachments": null
  }
}
```

</details>

<details><summary>Example 2 (step:5aaa73ba-eea3-4aa8-8361-b57b876b76f7)</summary>

```json
{
  "name": "Show data for approval",
  "arguments": {
    "type": "InputBased",
    "input": {
      "schema": {
        "title": "Show the sentence to someone",
        "description": "{{vars.steps.Call_child_playbook_for_logic.sentence}}",
        "inputVariables": []
      }
    },
    "record": "{{ vars.input.records[0][\"@id\"] }}",
    "agent_id": null,
    "resources": "food",
    "is_approval": true,
    "owner_detail": {
      "isAssigned": false,
      "emailRecipients": ""
    },
    "isRecordLinked": false,
    "step_variables": [],
    "response_mapping": {
      "options": [
        {
          "option": "Approve",
          "primary": true,
          "step_iri": "/api/3/workflow_steps/1a0ad736-f23e-40f5-8f58-10c6363c5dc1"
        },
        {
          "option": "Reject",
          "primary": false,
          "step_iri": "/api/3/workflow_steps/undefined"
        }
      ],
      "connecteStepsLength": 1,
      "customSuccessMessage": "Awaiting Playbook resumed successfully."
    },
    "email_notification": {
      "enabled": false,
      "smtpParameters": []
    },
    "customEmailExternal": false,
    "inline_channel_list": [],
    "external_channel_list": [],
    "unauthenticated_input": false,
    "external_email_subject": null,
    "internal_email_subject": "A FortiSOAR playbook is requesting your input",
    "custom_email_body_external": null,
    "external_email_attachments": null
  }
}
```

</details>

<details><summary>Example 3 (step:8754bd44-be25-4bde-b10a-6b23666be391)</summary>

```json
{
  "name": "approval step",
  "arguments": {
    "type": "InputBased",
    "input": {
      "schema": {
        "title": "test",
        "description": "test",
        "inputVariables": []
      }
    },
    "record": "",
    "agent_id": null,
    "resources": "alerts",
    "is_approval": true,
    "owner_detail": {
      "isAssigned": false,
      "emailRecipients": ""
    },
    "isRecordLinked": false,
    "step_variables": [],
    "response_mapping": {
      "options": [
        {
          "option": "Approve",
          "primary": true,
          "step_iri": null
        },
        {
          "option": "Reject",
          "primary": false,
          "step_iri": null
        }
      ],
      "connecteStepsLength": 0,
      "customSuccessMessage": "Awaiting Playbook resumed successfully."
    },
    "email_notification": {
      "enabled": false,
      "smtpParameters": []
    },
    "customEmailExternal": false,
    "inline_channel_list": [],
    "external_channel_list": [],
    "unauthenticated_input": false,
    "external_email_subject": null,
    "internal_email_subject": "A FortiSOAR playbook is requesting your input",
    "custom_email_body_external": null,
    "external_email_attachments": null
  }
}
```

</details>

---

## `RunScript`
_label: Run Utility Functions_

**Occurrences**: 4 · **UUID**: `ee73e569-2188-43fe-a7f0-1964ba82a4de`

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (3):

<details><summary>Example 1 (step:47502f55-1cba-410f-aa08-e80f6dfab736)</summary>

```json
{
  "name": "Do Nothing",
  "arguments": {
    "script": "/wf/workflow/tasks/no_op",
    "arguments": [],
    "step_variables": []
  }
}
```

</details>

<details><summary>Example 2 (step:5c9690a6-2aca-4ffd-8994-fa3e00970f43)</summary>

```json
{
  "name": "Do Nothing",
  "arguments": {
    "script": "/wf/workflow/tasks/no_op",
    "arguments": []
  }
}
```

</details>

<details><summary>Example 3 (step:cdcccc3a-dd8d-479b-9138-655c8a7172fa)</summary>

```json
{
  "name": "Get approval record by ID",
  "arguments": {
    "script": "/wf/workflow/tasks/crudhub_crud",
    "arguments": {
      "method": "GET",
      "resource": "",
      "collection": "/api/3/approvals?id$eq={{vars.record_id}}"
    },
    "step_variables": {
      "record": "{{vars.result['hydra:member'][0]}}"
    }
  }
}
```

</details>

---

## `SetAPIKeys`
_label: Set API Keys_

**Occurrences**: 2 · **Category**: `RunScript` · **UUID**: `b104e839-fc31-48b3-8c50-7e9433f33d79`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/set_multiple"
}
```

**Real-world examples** (2):

<details><summary>Example 1 (step:60ebd2b4-303c-4a16-8027-4f02769b59af)</summary>

```json
{
  "name": "set keys",
  "arguments": {
    "public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1WIZc1clBbiNouF6JzGi\nm+mAICI3RRe+N5nr3I12ovulm+IThEB6RosAc0ybKNAxRNpIP9h6eWhsrgINpnFR\nXFw3+yJ+qsnSmoubx1e2MzUBPXsJNnDtgzes7StUG7Dpr9PVXSc+I8djlDNcX/c9\nasuocBPQ356OJQBHsVqnhweYHbpYOcDKg7AKXZSjV0TmlzTDhFL6HkEZtzYTLFZI\nt/1RJC1kbvbq76jQO7yKUPWXAU8I1pUo4uAKa/BU+ysXle90i2D5UbFpJWpGMLIY\nZGpW7bB1pcRmbPzoZv8Qjp4KnZKLNHCTgVqkRJZVtwRFWl04vNDXMBr0IiiDAfXO\n2QIDAQAB\n-----END PUBLIC KEY-----",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA1WIZc1clBbiNouF6JzGim+mAICI3RRe+N5nr3I12ovulm+IT\nhEB6RosAc0ybKNAxRNpIP9h6eWhsrgINpnFRXFw3+yJ+qsnSmoubx1e2MzUBPXsJ\nNnDtgzes7StUG7Dpr9PVXSc+I8djlDNcX/c9asuocBPQ356OJQBHsVqnhweYHbpY\nOcDKg7AKXZSjV0TmlzTDhFL6HkEZtzYTLFZIt/1RJC1kbvbq76jQO7yKUPWXAU8I\n1pUo4uAKa/BU+ysXle90i2D5UbFpJWpGMLIYZGpW7bB1pcRmbPzoZv8Qjp4KnZKL\nNHCTgVqkRJZVtwRFWl04vNDXMBr0IiiDAfXO2QIDAQABAoIBAAZ+ckzW0ZsfdzwG\nRavssEizbgFMWUdChjj1974iFgK2yt74HeTv+2irMUvRAIXY9C7mv70lrvCD847G\nJDk1CKdZbSC494bmFoE6j3adHj/ntI508J5WCHxuVNZw86HWG/6MYVlw6My49Dhd\n6clH4ngeE5W5nKk5j5Tjscrdeey7ibUDm0b3CGGG9DZ5KArRzSo+Y2StJ7/GEpVw\nxFdEcyyOzQXbwU280J5LPOS5dqoXLYRYSpJEScQhiXv/wQM04eyvKhi77XWaLBqX\ntqK7tyeRn9YcOKwQdk16TBQ1q9Mc532mx+T5J6w3JgGn9LIA2e8hii3IUcPuErJ7\nx7FJCOMCgYEA5yvANB3Ts3/l0gPb373L8hGeNVZg9JxU8MBks8soPDANWlYvyOnm\nJDAAgJQaxeI1ngJIxFa8vIvcyE+XElPjw+ifHGIdvt79jxm1YsOjI7T1C7mWy+sN\njuqeV0ytnw50hVo8DqykWntuhCkr6Xkzumdto5zUB0JAXB7oXyadTH8CgYEA7E1C\njxUE+7trh2zc9SWW/eLD+YnXA0U8A4ws+wDQS2xHz7NiywLmgKdqzlgSSG/MBiZC\ny/fwCTKV82z86K7dazihK7MsveCvI/Fq7YIxDEQOHDI7UcVZrLYVNLAS7loDEMaL\nO87Vs77GCk/quw4wjw77/jRlWX3Sji+6TztTGKcCgYEAqJl6JwiR/FqNjWyPElHk\nyvoafyAuunjCYoyPZaoIAE2zj21IkKo21bHEzAI4vJZNMJ7N35S7NnBzaAzUS+Ov\nPJUOZq8QrsMH/zRq3Et/Um2KQzDqUHNwggmPzm/4OQdb6F51auZzQCLB6dX1VuS0\n24DPsAKTiW/CbO2F4M/S7ZUCgYA8I2GIFpphEo7INX16ammmDZtAm8L70xf18yvT\naZ6ZQ2J3Srke34sYPQNipmloxAMRoZUoYd5WCOi+vgMTmMVDL3NdMsl1PYR1SlCj\nR5oB/CP3KxWLtwUefmyhLxpyTLgxAcaXnwkmKKwwHayolHDpR6/8Pwt4HhyDEUSC\nO5/nSwKBgEEIsYq3Ig6MVRaugFsC9/X2PJJgYGjv8o6ppp8ePL8BBOGtMHaLoqg+\nfDv1PR6y55DEwwoMQ0YgfWsitfwELCTyRoXxPOZvJ7cIAXPh6mY+D3QK+MzwdzX5\nstOyh6aPPws9Ah9hjYcjwkz224UwpOAKfc5Jcux/q0usMAYGtCfD\n-----END RSA PRIVATE KEY-----"
  }
}
```

</details>

<details><summary>Example 2 (step:ec9c54c2-8f18-4eb3-b9fe-8c6dc806c04e)</summary>

```json
{
  "name": "set api keys",
  "arguments": {
    "public_key": "a",
    "private_key": "a"
  }
}
```

</details>

---

## `cybersponse.post_delete`
_label: On Delete_

**Occurrences**: 1 · **Category**: `cybersponse.abstract_trigger` · **UUID**: `ef350fda-1771-477a-8f90-16f68cd7e5cb`

Triggered on the deletion of records that match the specified criteria.

**Declared arguments shape** (from API):
```json
[]
```

**Real-world examples** (1):

<details><summary>Example 1 (step:5f5f0dea-2d10-4d92-9c74-607619d9ba68)</summary>

```json
{
  "name": "Start",
  "arguments": {
    "resource": "tasks",
    "resources": [
      "tasks"
    ],
    "__triggerLimit": true,
    "step_variables": {
      "input": {
        "params": [],
        "records": [
          "{{vars.input.records[0]}}"
        ]
      },
      "record": "{{vars.input.records[0]}}"
    },
    "triggerOnSource": true,
    "fieldbasedtrigger": {
      "sort": [],
      "limit": 30,
      "logic": "AND",
      "filters": []
    },
    "triggerOnReplicate": false
  }
}
```

</details>

---

## `APICall`
_label: Make API Call_

**Category**: `RunScript` · **UUID**: `949779e9-c4c2-4652-9ad2-c1875be6be54`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/api_call",
  "arguments": {
    "verify": true
  }
}
```

---

## `Approval`

**Category**: `RunScript` · **UUID**: `6832e556-b9c7-497a-babe-feda3bd27dcg`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/wait"
}
```

---

## `DatabaseConnector`
_label: Database Connector_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928745`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/database_connector_test"
}
```

---

## `DatabaseQuery`
_label: Database Query_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928799`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/database_query"
}
```

---

## `DownloadFile`
_label: Download File from URL_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928723`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/download_file_from_url"
}
```

---

## `FetchEmail`
_label: Fetch Email_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928789`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/fetch_email_and_explode"
}
```

---

## `FileAttachment`
_label: Create Attachment From File_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928796`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/upload_to_crudhub"
}
```

---

## `FileSFTP`
_label: SFTP_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928725`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/upload_to_url"
}
```

---

## `FileStringAttachment`
_label: Create File From String_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928724`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/create_file_from_string"
}
```

---

## `ManualDecision`
_label: Manual Decision_

**Category**: `RunScript` · **UUID**: `dc61b68b-4967-4e82-b4ed-a1315aa81998`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/wait"
}
```

---

## `MapPlaybook`
_label: Map Playbook_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928728`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/map"
}
```

---

## `ReferenceBlock`
_label: Add Reference Block_

**Category**: `RunScript` · **UUID**: `9f85dabc-dbc8-4d0a-905d-c99b2ef06b71`

**Declared arguments shape** (from API):
```json
[]
```

---

## `RemoteCommand`
_label: Remote Command_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928726`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/run_remote_command"
}
```

---

## `RemotePlaybookReference`
_label: Trigger Tenant Playbook_

**Category**: `RunScript` · **UUID**: `ab3b2e02-5e77-4ed6-8ebd-580f390063a5`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/remote_workflow_reference"
}
```

---

## `SendEmail`
_label: Send Email_

**Category**: `RunScript` · **UUID**: `b593663d-7d13-40ce-a3a3-96dece928778`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/send_email",
  "arguments": {
    "from_str": "admin@example.com"
  }
}
```

---

## `SetPlaybookResult`
_label: Set Playbook Result_

**Category**: `RunScript` · **UUID**: `9dcc4bf5-b6cf-4a5c-b545-1fac3b9e33e6`

**Declared arguments shape** (from API):
```json
{
  "script": "/wf/workflow/tasks/set_result"
}
```

---

## `action.reference.block`
_label: Trigger Block_

**Category**: `cybersponse.abstract_trigger` · **UUID**: `0f2e6d50-9cb9-403f-9990-85dc5fbb571d`

Readymade blocks for commonly used playbook trigger conditions.

**Declared arguments shape** (from API):
```json
[]
```

---

## `cybersponse.pre_create`
_label: Pre-Create Trigger_

**Category**: `cybersponse.abstract_trigger` · **UUID**: `aed55d18-1974-4743-b061-7f5a4292e657`

**Declared arguments shape** (from API):
```json
[]
```

---

## `cybersponse.pre_delete`
_label: Pre-Delete Trigger_

**Category**: `cybersponse.abstract_trigger` · **UUID**: `a987479e-9c96-46b0-9598-7f0b35e16ad2`

**Declared arguments shape** (from API):
```json
[]
```

---

## `cybersponse.pre_update`
_label: Pre-Update Trigger_

**Category**: `cybersponse.abstract_trigger` · **UUID**: `0d375573-1c17-47bb-9790-934cff200ec4`

**Declared arguments shape** (from API):
```json
[]
```

---
