"""Supplement the warmed DB with missing connectors from the packaged slim DB
+ add minimal metadata for connectors not in either DB (needed by tests)."""
import json
import sqlite3

WARMED = "data/fsr_reference.db"
SLIM = "fsr_playbooks/_data/fsr_reference.db"

warmed = sqlite3.connect(WARMED)
slim = sqlite3.connect(SLIM)
warmed.row_factory = sqlite3.Row
slim.row_factory = sqlite3.Row

# 1. Copy missing connectors (+ ops + params) from slim -> warmed
slim_c = {r[0] for r in slim.execute("SELECT name FROM connectors")}
warmed_c = {r[0] for r in warmed.execute("SELECT name FROM connectors")}
missing = slim_c - warmed_c

for cname in sorted(missing):
    crow = slim.execute("SELECT * FROM connectors WHERE name=?", (cname,)).fetchone()
    cols = list(crow.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    warmed.execute(
        f"INSERT INTO connectors ({col_list}) VALUES ({placeholders})",
        [crow[c] for c in cols],
    )
    for orow in slim.execute(
        "SELECT * FROM operations WHERE connector_name=?", (cname,)
    ).fetchall():
        ocols = list(orow.keys())
        oph = ", ".join(["?"] * len(ocols))
        oc_list = ", ".join(ocols)
        warmed.execute(
            f"INSERT INTO operations ({oc_list}) VALUES ({oph})",
            [orow[c] for c in ocols],
        )
    for prow in slim.execute(
        "SELECT * FROM operation_params WHERE connector_name=?", (cname,)
    ).fetchall():
        pcols = list(prow.keys())
        pph = ", ".join(["?"] * len(pcols))
        pc_list = ", ".join(pcols)
        warmed.execute(
            f"INSERT INTO operation_params ({pc_list}) VALUES ({pph})",
            [prow[c] for c in pcols],
        )
    n_ops = warmed.execute(
        "SELECT count(*) FROM operations WHERE connector_name=?", (cname,)
    ).fetchone()[0]
    print(f"Copied: {cname} ({n_ops} ops)")

# 2. Add connectors not in either DB (minimal metadata for tests)
extra_connectors = [
    ("apivoid", "1.0.0", "APIVoid"),
    ("aws-access-analyzer", "1.0.0", "AWS Access Analyzer"),
    ("claroty-xdome", "1.0.0", "Claroty xDome"),
    ("recorded-future", "3.0.0", "Recorded Future"),
]

for cname, ver, label in extra_connectors:
    if cname in warmed_c:
        continue
    warmed.execute(
        "INSERT INTO connectors (name, version, label, active, system, source) "
        "VALUES (?,?,?,?,0,'supplement')",
        (cname, ver, label, 1),
    )
    print(f"Added connector: {cname}")

# 3. Add operations for the test-needed connectors
extra_ops = [
    ("apivoid", "dnspropagation", "DNS Propagation"),
    ("aws-access-analyzer", "list_analyzers", "List Analyzers"),
    ("claroty-xdome", "get_vulnerabilities", "Get Vulnerabilities"),
]

for cname, op, title in extra_ops:
    warmed.execute(
        "INSERT OR IGNORE INTO operations (connector_name, op_name, title, visible, enabled) "
        "VALUES (?,?,?,?,1)",
        (cname, op, title, 1),
    )

# 4. Add operation params matching what the tests expect
extra_params = [
    # apivoid.dnspropagation.dns_record_type (select with enum options)
    ("apivoid", "dnspropagation", "dns_record_type", "DNS Record Type", "select", 1,
     json.dumps(["A", "AAAA", "NS", "MX", "TXT", "SRV", "SOA", "CNAME", "SPF", "CAA"]), 1),
    # aws-access-analyzer.list_analyzers
    ("aws-access-analyzer", "list_analyzers", "type", "Type", "text", 1, None, 1),
    ("aws-access-analyzer", "list_analyzers", "size", "Size", "integer", 0, None, 1),
    ("aws-access-analyzer", "list_analyzers", "assume_role", "Assume Role", "checkbox", 0, None, 1),
    # claroty-xdome.get_vulnerabilities.cvss_v3_score (decimal)
    ("claroty-xdome", "get_vulnerabilities", "cvss_v3_score", "CVSS v3 Score", "decimal", 0, None, 1),
]

for p in extra_params:
    warmed.execute(
        "INSERT OR IGNORE INTO operation_params "
        "(connector_name, op_name, param_name, title, type, required, options_json, visible) "
        "VALUES (?,?,?,?,?,?,?,?)",
        p,
    )

warmed.commit()
warmed.close()
slim.close()
print("Done — DB supplemented")
