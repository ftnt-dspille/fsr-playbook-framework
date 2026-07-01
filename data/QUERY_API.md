---
title: FortiSOAR Query API (pointer)
category: api-reference
status: reference
source: live-verified
topics:
- query-api
- filtering
- aggregation
- endpoints
- semantics
canonical: false
summary: 'Pointer — full Query API reference consolidated into the hub canonical
  (Miscellaneous/fortisoar/FortiSOAR_Query_Aggregation_and_Filter_Options.md).'
see_also:
- <fortisoar-docs>/FortiSOAR_Query_Aggregation_and_Filter_Options.md
---

# FortiSOAR Query API — moved

The full FortiSOAR Query API reference (all three surfaces — URL-param `GET`, `POST /api/query`,
and Elasticsearch global search — plus the complete operator/aggregation grammar, `$search` semantics,
pagination, and source anchors) has been **consolidated into the canonical hub doc**:

> **`<fortisoar-docs>/FortiSOAR_Query_Aggregation_and_Filter_Options.md`**

That doc is now the single source of truth — this file's former content (recon of
`/opt/cyops-api/src/{Query,Constants,Filter}` + live probes, 2026-05-03) was merged there verbatim.
Edit the canonical doc, not this pointer.

For **building** these queries in Python, see the pyfsr `Query` DSL guide:
`pyfsr/docs/source/guides/querying.md`.
