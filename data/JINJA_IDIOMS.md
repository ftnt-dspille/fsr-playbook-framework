# FSR Jinja Idioms

Patterns observed in 1,669 live FortiSOAR playbooks. These are the **idioms** —
how `{% set %}` / `{% for %}` / `{% if %}` get composed in real production
playbooks. For per-filter docs run `mcp find_jinja_filter <name>` or see
`get_filter_examples(<name>).curated_doc`. For raw corpus search use
`find_jinja_pattern(q, kind=<set|for|if|...>)`.

---

## The most common variable accesses (head of an expression)

| Path | Uses | What it is |
|---|---:|---|
| `vars.input.records` | 532 | the trigger's records list |
| `vars.input.records[0]` | 435 | the first/single trigger record |
| `vars.result` | 354 | the previous step's result (legacy/implicit) |
| `vars.input.records[0]['@id']` | 307 | the trigger record's IRI |
| `vars.input.params.<name>` | many | input params declared in `parameters:` |
| `vars.item` | 125 | the current `{% for %}` loop item |
| `vars.steps.<Name_us>` | many | a previous step's full result (see AUTHORING.md for naming rule) |

`vars.input.records[0]` vs `[0]['@id']` — most playbooks need either the
record body or its IRI; pick `[0]` when you need fields, `[0]['@id']` (or
`[0]["@id"]`) when you need to pass an IRI to another step.

---

## 1. Build a list by mutation in a loop

The Jinja idiom for "accumulate a list while iterating." Two equivalent
forms in the corpus:

```jinja
{# Form A — assignment-as-side-effect (8 corpus uses on iriList alone) #}
{% set iriList = [] %}
{% for r in vars.input.records %}
  {% set _ = iriList.append(r['@id']) %}
{% endfor %}

{# Form B — `do` extension, more explicit #}
{%- set addresses = [] -%}
{%- for a in vars.input.params.address_list -%}
  {%- do addresses.append({"type": "fqdn", "address": a }) -%}
{%- endfor -%}
```

When to use which:
- **Form A** works on stock Jinja (no `jinja2.ext.do` needed); the
  assignment-discard `set _ = …` is a common workaround pattern.
- **Form B** is cleaner and what the FSR engine prefers — `{% do %}` is
  enabled by default. Use it when the playbook author cares about
  readability.

Both compile to the same final list. **Don't** try `vars.iriList.append(...)`
— `vars` is per-step-merged, not mutable across statements.

---

## 2. Build a dict by accumulation

```jinja
{%- set idx = {} -%}
{# … or: {% set idx = dict() %} (10 corpus uses) — pure-Python dict() #}
{% for r in vars.input.records %}
  {% set _ = idx.update({r['@id']: r}) %}
{% endfor %}
```

For cross-iteration counters (the Jinja for-loop scope quirk):

```jinja
{%- set i = namespace(x=0) -%}
{% for r in vars.input.records %}
  {%- set i.x = i.x + 1 -%}
{% endfor %}
{{ i.x }}    {# 9 corpus uses of the namespace pattern — Jinja's escape from for-scope #}
```

Without `namespace`, `{% set total = total + 1 %}` inside a `{% for %}`
silently doesn't persist after the loop ends.

---

## 3. Length-guard before iterating / dereferencing

The single most common conditional pattern (22+ uses):

```jinja
{% if vars.result | length > 0 %}
  {{ vars.result[0]['@id'] }}
{% endif %}
```

Variants seen in corpus:
- `{% if vars.foundList | length != 0 %}` — explicit non-empty check (8 uses)
- `{% if vars.attributes | length > 1 %}` — "more than one"
- `{% if vars.SPF_Record | length == 0 %}` — empty check (negation)

Equivalent shorthand: `{% if vars.result %}` works for non-empty lists,
non-empty dicts, non-zero numbers, and non-empty strings — the truthy
check. Use the `| length` form when you specifically care about the count.

Also common: `{% if vars.input.records[0].tenant %}` (8 uses) — guard a
single optional field on the trigger record before reading it.

---

## 4. For-loop with inline filter

Jinja supports `{% for x in iter if cond %}` to filter and iterate in
one block (8 uses observed):

```jinja
{% for var in vars.SPF_Record if vars.SPF_Record %}
  {# only iterate when SPF_Record is truthy #}
  …
{% endfor %}
```

Equivalent to `{% if vars.SPF_Record %}{% for var in vars.SPF_Record %}…{% endfor %}{% endif %}`,
but more compact when you have no `else` branch.

For projecting + iterating you can chain a filter into the iterable:

```jinja
{%- for d in vars.input.records | json_query('[]."@id"') -%}
  {{ d }}
{%- endfor -%}
```

---

## 5. Iterate a dict's items

```jinja
{% for key, value in vars.attributes.items() %}    {# 8 uses #}
  {{ key }} = {{ value }}
{% endfor %}
```

When you need both keys and values, `.items()` is the canonical way.
For values-only use `.values()`; for keys-only just `for k in dct`.

To use `selectattr` / `json_query` on a dict, run it through
`dict2items` first (see that filter's curated doc).

---

## 6. Tuple-unpack via split

```jinja
{%- set name = dev.split(":") -%}      {# 12 uses #}
{{ name[0] }} on port {{ name[1] }}
```

Jinja doesn't natively unpack `{% set a, b = … %}`. Split-and-index is
the standard workaround. Same pattern works for any ordered collection.

---

## 7. Ternary fallback chain (param-or-trigger)

The "use param if provided, else use trigger record field" pattern (heavy
corpus use):

```jinja
{{ vars.input.params['indicator_value']
   | ternary(vars.input.params['indicator_value'], vars.input.records[0].value) }}
```

See the `ternary` curated doc for why this beats `cond if cond else other`
in FSR (engine quirks around evaluating undefined keys).

---

## 8. Decision-step condition (most common shape)

A `decision` step's `condition:` is just a Jinja expression that has to
return truthy/falsy. The corpus pattern:

```yaml
- id: route
  type: decision
  arguments:
    conditions:
      - option: yes
        condition: "{{ vars.steps.Is_Indicator_Exist | length > 0 }}"
      - option: no
        default: true     # ← unconditional fallback branch
```

The default branch should always have `default: true` and no condition.

---

## 9. WorkflowReference `for_each` looping

```yaml
- id: block_macs
  type: workflow_reference
  arguments:
    when: "{{ vars.list_of_mac_addresses_to_block | length > 0 }}"
    for_each:
      item: "{{ vars.total_batches_mac_addresses }}"
      parallel: false
      condition: ""
    arguments:
      macAddressList: "{{ vars.item }}"     # ← in the child, vars.item is the current batch
    workflowReference: /api/3/workflows/<uuid>
```

Inside the called workflow, the bound name is **`vars.item`** (not
the dotted path you passed). FSR sets a fresh `vars.item` per iteration.

---

## 10. The `set _` mutation idiom — full example

This pulls together patterns 1–3 — accumulating an index of records by
key, then iterating to look something up:

```jinja
{%- set idx = {} -%}
{%- for r in vars.steps.Find_Records.records -%}
  {%- set _ = idx.update({r.email: r}) -%}
{%- endfor -%}
{%- set list_vals = vars.record_metadata.get(key) if vars.record_metadata.get(key)
                    | type_debug == 'list' else vars.record_metadata.get(key).split(',') -%}
{# now idx[<email>] gives the full record #}
```

The `| type_debug` filter tells you the runtime type of a value — use
it when chaining a filter that expects one shape but the upstream might
return something else.

---

## How to discover more

```
fsrpb explain filter <name>             # one filter, signature + corpus example
fsrpb jinja '<template>' --from-pb-execution <pk>   # test against a real run env

# MCP (in Claude Desktop / IDE):
find_jinja_filter("<query>")            # filter catalog ordered by corpus_uses
get_filter_examples("<filter>")          # rich examples + curated_doc
find_jinja_pattern("<query>", kind="set"|"for"|"if"|"expr"|"macro"|None)
```
