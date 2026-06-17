"""PicklistMixin — resolving and rewriting picklist friendly token references."""
from __future__ import annotations

import difflib
import sqlite3
from typing import Any

from ..errors import CompileError, ErrorCode
from ..ir import Step


class PicklistMixin:
    """Methods for resolving and rewriting picklist friendly tokens."""

    conn: sqlite3.Connection

    def _resolve_picklist_friendly_tokens(
        self, step: Step, path: str, errors: list[CompileError],
    ) -> None:
        """Rewrite bare picklist-field string values in `arguments.resource`
        to the canonical `/api/3/picklists/<uuid>` IRI.

        Module is derived from `collection` (create/insert) or
        `collectionType` (update). A field is a candidate iff
        `module_fields.picklist_name IS NOT NULL`. A value is rewritten iff
        it's a non-empty string that:
          - is not already an IRI (`/api/...`),
          - contains no Jinja template markers (`{{`, `{%`),
          - matches a row in `picklists` for that listName.
        Unknown labels emit a BAD_VALUE with a "did you mean" suggestion.

        List values are walked element-wise (covers multiselectpicklist).
        """
        a = step.arguments if isinstance(step.arguments, dict) else {}
        resource = a.get("resource")
        if not isinstance(resource, dict):
            return

        # Module IRI source per step type. `collection` on create/insert is
        # the module IRI; on update it's the record IRI — use collectionType
        # there. Bail if we can't pin down the module — without it we can't
        # look up which fields are picklist-backed.
        if step.type in ("create_record", "insert_record"):
            mod_iri = a.get("collection")
        else:
            mod_iri = a.get("collectionType")
        if not isinstance(mod_iri, str) or not mod_iri.startswith("/api/3/"):
            return
        module = mod_iri.split("/api/3/", 1)[1].split("?", 1)[0].rstrip("/")
        if not module:
            return

        picklist_fields = {
            row[0]: row[1] for row in self.conn.execute(
                "SELECT field_name, picklist_name FROM module_fields "
                "WHERE module_name=? AND picklist_name IS NOT NULL",
                (module,),
            ).fetchall()
        }
        if not picklist_fields:
            return

        rpath = f"{path}.arguments.resource"
        for fname, fvalue in list(resource.items()):
            list_name = picklist_fields.get(fname)
            if not list_name:
                continue
            if isinstance(fvalue, list):
                new_list = []
                changed = False
                for i, item in enumerate(fvalue):
                    out = self._rewrite_one_picklist_token(
                        item, list_name, f"{rpath}.{fname}[{i}]", errors,
                    )
                    if out is not item:
                        changed = True
                    new_list.append(out)
                if changed:
                    resource[fname] = new_list
            else:
                out = self._rewrite_one_picklist_token(
                    fvalue, list_name, f"{rpath}.{fname}", errors,
                )
                if out is not fvalue:
                    resource[fname] = out

    def _rewrite_one_picklist_token(
        self, value: Any, list_name: str, vpath: str,
        errors: list[CompileError],
    ) -> Any:
        """Return the IRI for a friendly token, or the original value if
        it's already an IRI / Jinja expression / non-string. Appends a
        BAD_VALUE error to `errors` when the label doesn't match.
        """
        if not isinstance(value, str) or not value:
            return value
        # Pass-through: already canonical, or a Jinja expression that
        # resolves at runtime.
        if value.startswith("/api/") or "{{" in value or "{%" in value:
            return value
        row = self.conn.execute(
            "SELECT item_iri FROM picklists WHERE list_name=? AND item_value=?",
            (list_name, value),
        ).fetchone()
        if row:
            return row[0]
        # Build a "did you mean" suggestion from the same picklist.
        candidates = [r[0] for r in self.conn.execute(
            "SELECT item_value FROM picklists WHERE list_name=?",
            (list_name,),
        ).fetchall()]
        sug = difflib.get_close_matches(value, candidates, n=1, cutoff=0.6)
        # Recipe-template placeholders are intentional — flag as a
        # warning so the template compiles cleanly until the author
        # fills it in.
        is_placeholder = value.startswith("TODO") or value.startswith("<TODO")
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(f"picklist value {value!r} is not in picklist "
                     f"{list_name!r} (valid: "
                     f"{', '.join(sorted(candidates)[:8])}"
                     f"{'…' if len(candidates) > 8 else ''})"),
            path=vpath,
            near=sug[0] if sug else None,
            suggestion=(f"did you mean {sug[0]!r}?" if sug else None),
            severity="warning" if is_placeholder else "error",
        ))
        return value

    # Friendly `kind:` → canonical (formType, dataType, type, templateUrl)
    # for the inputVariables section of a manual_input step. Each row was
    # picked by querying live FSR (`probe playbook-steps --live`) for the
    # dominant (formType, dataType, type, templateUrl) tuple — see the
    # SQL in MI_DECISION_VALIDATION_AUDIT.md §4.
    _WEBADDR = "app/components/form/fields/webAddress.html"
    _INPUT_HTML = "app/components/form/fields/input.html"
    _INPUT_FIELD_KINDS: dict[str, dict[str, Any]] = {
        # text family
        "text":     {"formType": "text",     "dataType": "text", "type": "string",  "templateUrl": _INPUT_HTML},
        "textarea": {"formType": "textarea", "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/textarea.html"},
        "richtext": {"formType": "richtext", "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/markdownEditor.html"},
        "html":     {"formType": "html",     "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/htmlEditor.html"},
        "password": {"formType": "password", "dataType": "text", "type": "string",  "templateUrl": "app/components/form/fields/password.html"},
        # webAddress.html family — text dataType but typed sub-formats. Confirmed
        # against live FSR (ipv4/ipv6/domain present in store/fsr_reference.db).
        "ipv4":     {"formType": "ipv4",     "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "ipv6":     {"formType": "ipv6",     "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "domain":   {"formType": "domain",   "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "email":    {"formType": "email",    "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "url":      {"formType": "url",      "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "phone":    {"formType": "phone",    "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        "filehash": {"formType": "filehash", "dataType": "text", "type": "string",  "templateUrl": _WEBADDR},
        # numeric
        "integer":  {"formType": "integer",  "dataType": "text", "type": "integer", "templateUrl": _INPUT_HTML},
        "number":   {"formType": "integer",  "dataType": "text", "type": "integer", "templateUrl": _INPUT_HTML},
        "decimal":  {"formType": "decimal",  "dataType": "text", "type": "number",  "templateUrl": _INPUT_HTML},
        # bool
        "checkbox": {"formType": "checkbox", "dataType": "checkbox", "type": "boolean", "templateUrl": "app/components/form/fields/checkbox.html"},
        "boolean":  {"formType": "checkbox", "dataType": "checkbox", "type": "boolean", "templateUrl": "app/components/form/fields/checkbox.html"},
        # date / time
        "datetime": {"formType": "datetime", "dataType": "text", "type": "string",  "templateUrl": _INPUT_HTML},
        "date":     {"formType": "date",     "dataType": "text", "type": "string",  "templateUrl": _INPUT_HTML},
        # selectors. `select` is the friendly name for FSR's "Dynamic List"
        # (static enum). Distinct from `picklist` (FSR-managed list) and
        # `multiselect`/`multiselectpicklist` (their multi-value variants).
        "select":             {"formType": "dynamicList",         "dataType": "dynamicList", "type": "array",     "templateUrl": "app/components/form/fields/dynamicList.html"},
        "multiselect":        {"formType": "multiselect",         "dataType": "dynamicList", "type": "array",     "templateUrl": "app/components/form/fields/dynamicList.html"},
        "picklist":           {"formType": "picklist",            "dataType": "picklist",    "type": "picklists", "templateUrl": "app/components/form/fields/typeahead.html"},
        "multiselectpicklist":{"formType": "multiselectpicklist", "dataType": "picklist",    "type": "picklists", "templateUrl": "app/components/form/fields/typeahead.html"},
        # lookup — `type` is overridden per-field with the target module name
        # (people / indicators / alerts / etc.); see _expand_input_variables.
        "lookup":   {"formType": "lookup", "dataType": "lookup", "type": "lookup", "templateUrl": "app/components/form/fields/typeahead.html"},
        # files / structured
        "file":     {"formType": "file",   "dataType": "file",   "type": "string", "templateUrl": "app/components/form/fields/file.html"},
        "image":    {"formType": "image",  "dataType": "file",   "type": "string", "templateUrl": "app/components/form/fields/file.html"},
        "json":     {"formType": "object", "dataType": "object", "type": "object", "templateUrl": "app/components/form/fields/json.html"},
        "object":   {"formType": "object", "dataType": "object", "type": "object", "templateUrl": "app/components/form/fields/json.html"},
    }

    # Per-kind humanised "title" shown next to the field in the FSR UI.
    _INPUT_FIELD_TITLE: dict[str, str] = {
        "text": "Text", "textarea": "Text Area", "richtext": "Rich Text",
        "html": "Rich Text (HTML)", "password": "Password",
        "ipv4": "IPv4", "ipv6": "IPv6", "domain": "Domain",
        "email": "Email", "url": "URL", "phone": "Phone Number",
        "filehash": "File Hash",
        "integer": "Integer", "number": "Integer", "decimal": "Decimal",
        "checkbox": "Checkbox", "boolean": "Checkbox",
        "datetime": "Datetime", "date": "Date",
        "select": "Dynamic List", "multiselect": "Multi Select",
        "picklist": "Picklist", "multiselectpicklist": "Multi Picklist",
        "lookup": "Lookup",
        "file": "File", "image": "Image",
        "json": "JSON", "object": "JSON",
    }

    # Name/label substring → more specific input `kind:`. Order matters —
    # ipv4 must beat the bare "ip" rule for ip_address-style fields.
    _KIND_HINTS = (
        ("ipv6", "ipv6"),
        ("ipv4", "ipv4"),
        ("ip_address", "ipv4"), ("ipaddress", "ipv4"), ("ip address", "ipv4"),
        ("email", "email"), ("e-mail", "email"),
        ("url", "url"),
        ("domain", "domain"), ("hostname", "domain"), ("fqdn", "domain"),
        ("filehash", "filehash"), ("sha256", "filehash"), ("sha1", "filehash"),
        ("md5", "filehash"), ("file_hash", "filehash"),
    )

    def _suggest_specific_kind(self, name: str, label: str) -> str | None:
        hay = f"{name} {label}".lower()
        for needle, kind in self._KIND_HINTS:
            if needle in hay:
                return kind
        return None

