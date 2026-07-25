---
title: FSR Jinja Quick Reference
category: playbook-authoring
status: reference
topics:
  - jinja
  - patterns
  - quick-reference
  - task-oriented
summary: >
  Task-oriented Jinja pattern catalog for FortiSOAR playbook authoring. Maps
  common tasks to working patterns with gotchas and real examples. Not a
  filter list — a "how do I..." cheat sheet. Cross-references the fsr_reference.db
  and JINJA_IDIOMS.md for deeper detail.
---

# FSR Jinja Quick Reference

Task-oriented patterns for the most common FortiSOAR Jinja authoring tasks.
Each pattern includes a working snippet, the gotcha that bit us at least once,
and pointers to real examples in the corpus.

For the full filter catalog (170+ filters, 15 globals, 39 tests), use:

```bash
pyfsr jinja find picklist       # show a filter by name
pyfsr jinja search "query"      # full-text search
pyfsr jinja list --kind globals  # list all globals
pyfsr jinja examples picklist    # real usage examples
pyfsr jinja idioms               # common composition patterns
```

---

## 1. Resolve a picklist IRI (the #1 portability bug)

**Task:** Set a picklist field on a record, or build a query filter on a
picklist field — needs the IRI, not the label string.

**Pattern:**
```jinja
{{ "AlertState" | picklist("Indicator Extracted", "@id") }}
```

**Gotchas:**
- The `key` argument (`"@id"`) is **critical** for query-body JSON. Without
  it, the filter returns a full dict object, which produces invalid JSON
  when dropped into a template string.
- **Wrap in JSON quotes** when embedding in a query body string:
  `"value": "{{ ... | picklist(..., \"@id\") }}"` — unquoted, the IRI
  renders as a bare token (`/api/3/...`), making the JSON invalid.
- The picklist NAME goes in the pipeline input (left of `|`); the option
  label is the first argument.

**Forms:**
```jinja
{{ 'Severity' | picklist('High') }}              → "/api/3/picklists/<uuid>" (default key=@id)
{{ 'Severity' | picklist('High', '@id') }}       → "/api/3/picklists/<uuid>" (explicit)
{{ 'Severity' | picklist('High', 'uuid') }}      → "<uuid>" (just the UUID)
{{ 'Severity' | picklist('High', 'itemValue') }}  → "High" (the display name)
{{ 'Severity' | picklist('High') }}              → {...} (full dict, omit key — rare)
```

**Real examples (from 226 picklist usages in the corpus):**
```jinja
{{"SLAState" | picklist("NA", "@id")}}
{{"Closure Reason" | picklist("Resolved", "@id")}}
{{"AlertStatus" | picklist(vars.sla_time_list.altPauseSLAOn[0], "@id")}}
```

**For dynamic resolution in a playbook definition (no Jinja at author time):**
```python
# From pyfsr:
expr = client.picklists.jinja_picklist_expr("AlertState", "Indicator Extracted")
# → '{{ "AlertState" | picklist("Indicator Extracted", "@id") }}'
```

---

## 2. Build a query JSON body (Record Query step)

**Task:** Construct a query body with filters in a `SetVariable` step, then
pass it to a `Query Record` step.

**Pattern:**
```jinja
{{
{
  "__selectFields": ["name", "state", "id"],
  "logic": "AND",
  "filters": [
    {
      "type": "object",
      "field": "state",
      "value": "{{ "AlertState" | picklist("Indicator Extracted", "@id") }}",
      "_value": {
        "@id": "{{ "AlertState" | picklist("Indicator Extracted", "@id") }}",
        "display": "Indicator Extracted",
        "itemValue": "Indicator Extracted"
      },
      "operator": "eq"
    },
    {
      "type": "primitive",
      "field": "uuid",
      "value": "{{ vars.match_results.uuid }}",
      "operator": "eq"
    }
  ]
}
}}
```

**Gotchas:**
- Picklist IRIs inside JSON **must be quoted** — see pattern #1.
- Use `vars.match_results.uuid` (or whatever your previous step named the
  record) for the UUID filter — not `vars.input.records[0].uuid` (that's
  the trigger record, not the queried record).
- `"type": "object"` for picklist fields; `"type": "primitive"` for
  scalar fields like `uuid`.
- For a multi-value `nin` (not-in) filter on a picklist, use an array of
  quoted IRIs:
  ```jinja
  "value": [
    "{{ "IndicatorReputation" | picklist("Good", "@id") }}",
    "{{ "IndicatorReputation" | picklist("TBD", "@id") }}",
    "{{ "IndicatorReputation" | picklist("No Reputation Available", "@id") }}"
  ]
  ```

---

## 3. Convert datetime string to epoch integer

**Task:** An alert's `eventTime` field is `type=integer, formType=datetime` —
the API expects an epoch integer, but source data often comes as a datetime
string. Convert it.

**Pattern:**
```jinja
{{ arrow.get(vars.item["firstSeen"]).int_timestamp }}
```

**Gotchas:**
- `arrow` is a Jinja **global** (not a filter) — call it directly, no pipe.
- `.int_timestamp` gives epoch **seconds** (integer). The API may want
  **milliseconds** in some contexts — check the field schema.
- For "now": `{{ arrow.utcnow().int_timestamp }}`
- For computing elapsed time:
  ```jinja
  {%- set seconds = arrow.utcnow().int_timestamp - arrow.get(vars.input.records[0].zTPProfileStarted).int_timestamp -%}
  ```

**Real examples:**
```jinja
{% set _ = nfm.update({'firstSeen': (arrow.get(fs).int_timestamp)}) %}
{% set _ = nfm.update({'lastSeen': (arrow.get(ls).int_timestamp)}) %}
```

---

## 4. Access the trigger record

**Task:** Get fields from the record that triggered the playbook.

**Pattern:**
```jinja
{{ vars.input.records[0].name }}          # a field value
{{ vars.input.records[0]['@id'] }}        # the record's IRI
{{ vars.input.records[0].uuid }}          # the record's UUID
{{ vars.input.params.my_param }}          # a manual-input parameter
```

**Gotchas:**
- `vars.input.records` is a **list** — use `[0]` for the single-record case.
  For record-action triggers, it always has one element.
- `@id` needs bracket notation (`['@id']`) because `.` syntax doesn't work
  with keys starting with `@`.
- Manual-input parameters live under `vars.input.params.<name>`, not
  `vars.<name>`.

**Corpus stats:** `vars.input.records[0]` appears 435 times; `vars.input.records`
appears 532 times — the most common variable access in the entire corpus.

---

## 5. Reference a previous step's result

**Task:** Use the output of a step that ran earlier in the playbook.

**Pattern:**
```jinja
{{ vars.steps.Query_Record_State.data["hydra:member"] }}
{{ vars.steps.Set_Malicious_IOCs.malicious_ip_indicators }}
```

**Gotchas:**
- The step name has **spaces replaced by underscores**: a step named
  `"Query Record State"` is accessed as `vars.steps.Query_Record_State`.
- The shape depends on the step type — `data` for query results
  (with `hydra:member`), direct fields for SetVariable steps.
- With debug logging off (the default), `set_variable` / jinja values may
  not be captured in the run record. Assert on `status` (which always
  survives) rather than a value that may be absent.

---

## 6. Extract IRIs from a list of records

**Task:** Get all `@id` values from a list of records (e.g., to pass to a
bulk operation or build a comma-separated list).

**Pattern A — json_query filter:**
```jinja
{{ vars.input.records | json_query('[].["@id"]') }}
{{ vars.result | json_query('[]."@id"') }}
```

**Pattern B — loop accumulator:**
```jinja
{% set iri_list = [] %}
{% for r in vars.input.records %}
  {% set _ = iri_list.append(r['@id']) %}
{% endfor %}
{{ iri_list | join(',') }}
```

**Real examples (json_query — 289 usages, top 3 filter):**
```jinja
{%- for d in vars.input.records | json_query('[].["@id"]') -%}
{{ vars.result | json_query('[]."@id"') }}
{{ vars.input.records | json_query('[].id') }}
```

---

## 7. Resolve an IRI to its object

**Task:** Fetch the full record for an IRI (e.g., a related record's
details).

**Pattern:**
```jinja
{{ vars.input.records[0]['@id'] | fromIRI }}
{{ (vars.input.records[0]['@id'] + "?$relationships=true") | fromIRI }}
```

**Gotchas:**
- `fromIRI` makes a live API call — it's not free. Don't use it in a loop
  without batching.
- Chain with `json_query` to extract a nested field:
  ```jinja
  {{ "/api/3/workflows/{}".format(uri) | fromIRI | json_query('recordTags | [? contains(@, `FMG_Config`)]') | first }}
  ```

---

## 8. Build a list in a loop (accumulator pattern)

**Task:** Collect values across a loop into a list.

**Pattern A — assignment-as-side-effect (most common):**
```jinja
{% set iri_list = [] %}
{% for r in vars.input.records %}
  {% set _ = iri_list.append(r['@id']) %}
{% endfor %}
```

**Pattern B — `do` extension (more explicit):**
```jinja
{%- set addresses = [] -%}
{%- for a in vars.input.params.address_list -%}
  {%- do addresses.append({"type": "fqdn", "address": a }) -%}
{%- endfor -%}
```

**Gotchas:**
- Jinja has **no block scoping** — a `{% set %}` inside a loop leaks to
  the surrounding scope. The accumulator pattern works because of this.
- Use `{%- ... -%}` (whitespace control) when building JSON to avoid
  spurious newlines in the output.

---

## 9. Conditional value with a default

**Task:** Use a value if it exists, fall back to a default.

**Pattern:**
```jinja
{{ vars.input.params.severity | default('Medium') }}
{{ vars.steps.Some_Step.result | default([]) | length }}
```

**Gotchas:**
- `default` only triggers on `undefined`, not on `None` or empty string.
  For "default if falsy", use `or`:
  ```jinja
  {{ vars.input.params.severity or 'Medium' }}
  ```

---

## 10. Format a date string

**Task:** Format an epoch or ISO datetime as a human-readable string.

**Pattern:**
```jinja
{{ vars.createDate | strftime('%Y-%m-%d %H:%M:%S') }}
{{ vars.firstSeen | to_datetime }}
```

**For relative dates (FortiSOAR globals):**
```jinja
{{ currentDateMinus(7) }}                    # 7 days ago
{{ getRelativeDate(days=-1) }}                # yesterday
{{ get_current_datetime() }}                 # now
```

---

## Quick lookup table

| Task | Pattern | Key gotcha |
|---|---|---|
| Picklist IRI | `picklist("Value", "@id")` | Must quote in JSON: `"{{ ... }}"` |
| Datetime → epoch | `arrow.get(str).int_timestamp` | `arrow` is a global, not a filter |
| Trigger record | `vars.input.records[0]` | Use `['@id']` not `.@id` |
| Step result | `vars.steps.Step_Name.result` | Spaces → underscores |
| Extract IRIs from list | `json_query('[].["@id"]')` | 289 usages in corpus |
| Resolve IRI to object | `fromIRI` | Makes a live API call |
| Build list in loop | `{% set _ = list.append(x) %}` | No block scoping |
| Default value | `value | default('fallback')` | Only triggers on undefined |
| Relative date | `currentDateMinus(7)` | Global, not a filter |
| Multi-value picklist filter | Array of quoted `picklist()` calls | Each needs `"@id"` key |

---

## See also

- `pyfsr jinja find <name>` — full signature + curated doc for any filter
- `pyfsr jinja examples <name>` — real usage from the 1,669-playbook corpus
- `pyfsr jinja idioms` — composition patterns (set/for/if in production)
- `FSR_CUSTOM_JINJA.md` — the canonical 170-filter cheatsheet
- `JINJA_IDIOMS.md` — patterns from 1,669 playbooks
