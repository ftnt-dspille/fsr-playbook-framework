# FortiSOAR-custom Jinja capabilities

Generated from `store/fsr_reference.db` by `python/store/export_jinja_cheatsheet.py`. Source-of-truth is the live FSR appliance via `inspect.signature()` introspection on the workflow service's Jinja Environment (`backend_introspect` method).

**These filters / globals / tests are FortiSOAR-specific** (modules `workflow.*` or `sealab.*`). They are *not* in stock Jinja2 or Ansible. Reach for these first when writing FSR playbook Jinja — they shortcut a lot of common date / IOC / connector-config patterns.

For the full 170-filter / 15-global / 39-test catalog, query `fsr_reference.db` directly:

```sql
SELECT name, signature, module FROM jinja_macros ORDER BY name;
SELECT name, signature, module FROM jinja_globals ORDER BY name;
SELECT name, signature, module FROM jinja_tests   ORDER BY name;
```

## Globals — invoked as `name(args)`, no pipe (5)

Globals are callables in scope inside any `{{ ... }}`. They are *not* piped — call them directly.

### `currentDateMinus(days)`
_sealab.jinja_

**Parameters:**
- `days`

**Usage:** `{{ currentDateMinus(...) }}`

---

### `get_current_date()`
_sealab.jinja_

**Usage:** `{{ get_current_date(...) }}`

---

### `get_current_datetime()`
_sealab.jinja_

**Usage:** `{{ get_current_datetime(...) }}`

---

### `getRelativeDate(years=0, months=0, days=0, hours=0, minutes=0, seconds=0)`
_workflow.jinja_

**Parameters:**
- `years` — default: `0`
- `months` — default: `0`
- `days` — default: `0`
- `hours` — default: `0`
- `minutes` — default: `0`
- `seconds` — default: `0`

**Usage:** `{{ getRelativeDate(...) }}`

---

### `uuid()`
_sealab.jinja_

**Usage:** `{{ uuid(...) }}`

---

## Filters — invoked as `value | name(args)` (27)

### `count_occurrence(data)`
_workflow.jinja_

:param list data: ['apple','red','apple','red','red','pear']
:return: count of occurrence of each item {'red': 3, 'apple': 2, 'pear': 1}
:rtype: dict

**Parameters:**
- `data`

**Usage:** `{{ value | count_occurrence }}`

---

### `counter(data)`
_workflow.jinja_

:param list data: ['apple','red','apple','red','red','pear']
:return: count of occurrence of each item {'red': 3, 'apple': 2, 'pear': 1}
:rtype: dict

**Parameters:**
- `data`

**Usage:** `{{ value | counter }}`

---

### `extract_artifacts(data)`
_workflow.jinja_

**Parameters:**
- `data`

**Usage:** `{{ value | extract_artifacts }}`

---

### `extract_cef(cef_input)`
_workflow.jinja_

**Parameters:**
- `cef_input`

**Usage:** `{{ value | extract_cef }}`

---

### `find_indicators(context, iri, indicator_types=None, indicator_reputations=None, indicator_values=None, include_related_records=False)`
_workflow.jinja_

**Parameters:**
- `context`
- `iri`
- `indicator_types` — default: `None`
- `indicator_reputations` — default: `None`
- `indicator_values` — default: `None`
- `include_related_records` — default: `False`

**Usage:** `{{ value | find_indicators }}`

---

### `fromIRI(context, iri)`
_workflow.jinja_

**Parameters:**
- `context`
- `iri`

**Usage:** `{{ value | fromIRI }}`

---

### `getRelativeDate(years=0, months=0, days=0, hours=0, minutes=0, seconds=0)`
_workflow.jinja_

**Parameters:**
- `years` — default: `0`
- `months` — default: `0`
- `days` — default: `0`
- `hours` — default: `0`
- `minutes` — default: `0`
- `seconds` — default: `0`

**Usage:** `{{ value | getRelativeDate }}`

---

### `html2text(string)`
_workflow.jinja_

**Parameters:**
- `string`

**Usage:** `{{ value | html2text }}`

---

### `htmltotext(string)`
_workflow.jinja_

**Parameters:**
- `string`

**Usage:** `{{ value | htmltotext }}`

---

### `ip_range(ip_address, cidr)`
_workflow.jinja_

**Parameters:**
- `ip_address`
- `cidr`

**Usage:** `{{ value | ip_range }}`

---

### `iriToLink(record_iri, base_uri='')`
_workflow.jinja_

**Parameters:**
- `record_iri`
- `base_uri` — default: `''`

**Usage:** `{{ value | iriToLink }}`

---

### `json2html(data, row_fields=None, template='Stylized with row selection', display='Horizontal', styling=False, table_style=None)`
_workflow.jinja_

**Parameters:**
- `data`
- `row_fields` — default: `None`
- `template` — default: `'Stylized with row selection'`
- `display` — default: `'Horizontal'`
- `styling` — default: `False`
- `table_style` — default: `None`

**Usage:** `{{ value | json2html }}`

---

### `loadRelationships(record_iri, module, selected_fields=[])`
_workflow.jinja_

**Parameters:**
- `record_iri`
- `module`
- `selected_fields` — default: `[]`

**Usage:** `{{ value | loadRelationships }}`

---

### `logParse(data: 'str', log_type: 'str')`
_workflow.jinja_

**Parameters:**
- `data` — type: `str`
- `log_type` — type: `str`

**Usage:** `{{ value | logParse }}`

---

### `markdown2html(markdown_string)`
_workflow.jinja_

**Parameters:**
- `markdown_string`

**Usage:** `{{ value | markdown2html }}`

---

### `np_batch(data, batch_size)`
_workflow.np_filters_

**Parameters:**
- `data`
- `batch_size`

**Usage:** `{{ value | np_batch }}`

---

### `np_join(list1, list2)`
_workflow.np_filters_

**Parameters:**
- `list1`
- `list2`

**Usage:** `{{ value | np_join }}`

---

### `np_split(data, batch_size)`
_workflow.np_filters_

**Parameters:**
- `data`
- `batch_size`

**Usage:** `{{ value | np_split }}`

---

### `np_unique(data)`
_workflow.np_filters_

**Parameters:**
- `data`

**Usage:** `{{ value | np_unique }}`

---

### `picklist(context, name, value=None, key=None)`
_workflow.jinja_

**Parameters:**
- `context`
- `name`
- `value` — default: `None`
- `key` — default: `None`

**Usage:** `{{ value | picklist }}`

---

### `resolveRange(value, rangeDict)`
_sealab.jinja_

**Parameters:**
- `value`
- `rangeDict`

**Usage:** `{{ value | resolveRange }}`

---

### `toDict(string)`
_sealab.jinja_

**Parameters:**
- `string`

**Usage:** `{{ value | toDict }}`

---

### `toJSON(data)`
_workflow.jinja_

Converts a python data type into a JSON string.

.. note::
     This filter will put the data through two iterations of `json.dumps`
     because one iteration will automatically be stripped off by
     `workflow.environment.Environment.expand`

:param dict data: The object to be converted

:return: a valid json string
:rtype: str

**Parameters:**
- `data`

**Usage:** `{{ value | toJSON }}`

---

### `urldecode(url)`
_workflow.jinja_

**Parameters:**
- `url`

**Usage:** `{{ value | urldecode }}`

---

### `urlencode(url)`
_workflow.jinja_

**Parameters:**
- `url`

**Usage:** `{{ value | urlencode }}`

---

### `xml_to_dict(xml)`
_workflow.jinja_

**Parameters:**
- `xml`

**Usage:** `{{ value | xml_to_dict }}`

---

### `yaql(context, data, yaqlExpression)`
_workflow.jinja_

**Parameters:**
- `context`
- `data`
- `yaqlExpression`

**Usage:** `{{ value | yaql }}`

---
