#!/usr/bin/env bash
# fsr_recon.sh — one-shot read-only recon on a FortiSOAR appliance.
#
# Usage (as csadmin on the FSR box):
#   curl -O https://.../fsr_recon.sh   # or scp it over
#   chmod +x fsr_recon.sh
#   sudo ./fsr_recon.sh
#
# Output: /home/csadmin/fsrpb_recon/<timestamp>/  + a .tgz next to it.
#
# Read-only. Does NOT modify FSR state. Some commands need sudo because
# they read /opt/cyops-* and tail logs.

set -u
umask 022

OUT_BASE="/home/csadmin/fsrpb_recon"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${OUT_BASE}/${STAMP}"
mkdir -p "${OUT}"
cd "${OUT}"

log()  { printf '\n=== %s ===\n' "$*"; }
run()  { printf '$ %s\n' "$*"; eval "$@" 2>&1; printf '\n'; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 0. Box metadata
# ---------------------------------------------------------------------------
{
  log "uname / release"
  uname -a
  cat /etc/os-release 2>/dev/null
  log "hostname / IPs"
  hostname; ip -br a 2>/dev/null || ifconfig 2>/dev/null
  log "FSR version"
  cat /opt/cyops/configs/.fortisoar 2>/dev/null
  ls /opt/cyops 2>/dev/null
  log "cyops-* services"
  systemctl list-units --type=service --no-pager 2>/dev/null | grep -i cyops || true
} > 00_box_meta.txt 2>&1

# ---------------------------------------------------------------------------
# A. Workflow-log / execution endpoint discovery
# ---------------------------------------------------------------------------
log "A. Symfony route table (full + filtered)"
sudo php /opt/cyops-api/bin/console debug:router 2>/dev/null > A1_routes_full.txt || \
    echo "(debug:router unavailable)" > A1_routes_full.txt
grep -iE 'workflow|run|exec|log|trigger|playbook|delete-with-query|purge|import|export' \
    A1_routes_full.txt > A2_routes_workflow_filtered.txt 2>/dev/null || true

log "A. Workflow Django app urls.py / endpoints"
sudo grep -rn -E "url\(|path\(|re_path\(" /opt/cyops-workflow/sealab/ \
    --include='urls.py' 2>/dev/null > A3_workflow_urls.txt || true

# any view/route mentioning Run, Execute, WorkflowLog
sudo find /opt/cyops-api/src/Controller /opt/cyops-workflow/sealab \
    -type f \( -name '*.php' -o -name '*.py' \) 2>/dev/null \
    | xargs grep -lE '(Run|Execute|WorkflowLog|workflow_log|RunHistory|executions)' 2>/dev/null \
    > A4_runlog_files.txt || true

# Workflow-runs surface (the /api/wf/runs/ that returned 403)
sudo grep -rn -E "runs|workflow_runs|WorkflowRun" /opt/cyops-workflow/sealab/ \
    --include='*.py' 2>/dev/null \
    | head -200 > A5_workflow_runs_pyrefs.txt || true

# ---------------------------------------------------------------------------
# B. Trigger / execute surface
# ---------------------------------------------------------------------------
log "B. Trigger routes"
grep -i trigger A1_routes_full.txt > B1_routes_triggers.txt 2>/dev/null || true

# api/triggers/N/<uuid> handler
sudo grep -rn -E "triggers/|TriggerController|\\\\Trigger" /opt/cyops-api/src 2>/dev/null \
    | head -200 > B2_trigger_php_refs.txt || true

# wf/workflow/tasks/<func>/ — already used by run-op; capture full route map
sudo grep -rn -E "workflow/tasks|FUNCTION_MAP|RunFunction" /opt/cyops-workflow/sealab \
    --include='*.py' 2>/dev/null | head -200 > B3_workflow_tasks_refs.txt || true

# ---------------------------------------------------------------------------
# C. Soft-delete / purge path
# ---------------------------------------------------------------------------
log "C. Hard-purge route"
grep -iE 'delete-with-query|delete_with_query|purge|recycle|showDeleted' A1_routes_full.txt \
    > C1_routes_purge.txt 2>/dev/null || true

log "C. PlaybookConfig.php delete logic"
for f in /opt/cyops-api/src/Service/PlaybookConfig.php \
         /opt/cyops-api/src/Service/Playbook/PlaybookConfig.php \
         /opt/cyops-api/src/Service/ConfigExportImport/PlaybookConfig.php; do
    if [[ -r "$f" ]]; then
        echo "--- $f ---"
        sudo grep -nE 'delete|purge|showDeleted|recycle|hardDelete|removeUuid' "$f"
    fi
done > C2_playbookconfig_delete.txt 2>&1

sudo grep -rn -E 'showDeleted|deletedat|deletedAt|delete-with-query' /opt/cyops-api/src 2>/dev/null \
    | head -300 > C3_softdelete_refs.txt || true

# ---------------------------------------------------------------------------
# D. Step handlers (FUNCTION_MAP live + writes)
# ---------------------------------------------------------------------------
log "D. Live FUNCTION_MAP dump"
PYBIN=""
for cand in /opt/cyops-workflow/.venv/bin/python \
            /opt/cyops-workflow/venv/bin/python \
            /opt/cyops-workflow/bin/python; do
    [[ -x "$cand" ]] && PYBIN="$cand" && break
done
if [[ -n "$PYBIN" ]]; then
    sudo "$PYBIN" - <<'PY' > D1_function_map_live.json 2> D1_function_map_live.err
import json, sys
try:
    from workflow.eval import FUNCTION_MAP
    out = {k: getattr(v, '__module__', '?') + '.' + getattr(v, '__qualname__', getattr(v, '__name__', '?'))
           for k, v in FUNCTION_MAP.items()}
    print(json.dumps(out, indent=2, sort_keys=True))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
PY
else
    echo "(no workflow venv python found)" > D1_function_map_live.json
fi

log "D. FUNCTION_MAP write sites (late binding)"
sudo grep -rn 'FUNCTION_MAP\[' /opt/cyops-workflow/ 2>/dev/null > D2_function_map_writes.txt || true

# Also locate the missing handlers if present
sudo grep -rnE "def (map|fetch_email_and_explode)\(|'map'|'fetch_email_and_explode'" \
    /opt/cyops-workflow/sealab 2>/dev/null | head -200 > D3_missing_handlers_refs.txt || true

# ---------------------------------------------------------------------------
# E. Hydra / API Platform exposure manifest (no UI clicks needed)
# ---------------------------------------------------------------------------
log "E. API Platform yaml + entity files"
mkdir -p E_api_platform
sudo cp -r /opt/cyops-api/config/api_platform/. E_api_platform/ 2>/dev/null || true
mkdir -p E_routes
sudo cp -r /opt/cyops-api/config/routes/. E_routes/ 2>/dev/null || true
mkdir -p E_workflow_entities
sudo cp -r /opt/cyops-api/src/Entity/Workflow/. E_workflow_entities/ 2>/dev/null || true

# Controllers — useful for grep but bigger
sudo tar czf E_controllers.tgz -C /opt/cyops-api/src Controller 2>/dev/null || true

# ---------------------------------------------------------------------------
# F. Connector op execution surface (samples last 200 lines of integrations log)
# ---------------------------------------------------------------------------
log "F. cyops-integrations recent log"
for f in /var/log/cyops-integrations/cyops-integrations.log \
         /var/log/cyops-integrations.log; do
    if [[ -r "$f" ]] || sudo test -r "$f"; then
        sudo tail -n 500 "$f" > F1_integrations_tail.txt 2>/dev/null
        break
    fi
done

# Connector dispatcher
sudo find /opt/cyops-integrations -name '*.py' -path '*execute*' 2>/dev/null \
    > F2_integration_execute_files.txt || true

# ---------------------------------------------------------------------------
# G. Workflow-runs detail (the 403 endpoint we want to use)
# ---------------------------------------------------------------------------
log "G. /api/wf/runs/ + jinja-editor view code"
sudo grep -rnE "class .*Runs?View|class .*WorkflowRun|jinja-editor|JinjaEditor" \
    /opt/cyops-workflow/sealab --include='*.py' 2>/dev/null | head -200 \
    > G1_runs_view_refs.txt || true

# also the urls.py that wires /api/wf/
sudo find /opt/cyops-workflow -name 'urls.py' 2>/dev/null \
    | while read u; do echo "===== $u ====="; sudo cat "$u"; done \
    > G2_workflow_urlconfs.txt 2>&1

# ---------------------------------------------------------------------------
# H. Misc: nginx site config (so we know how /api/* routes split between
#    cyops-api (Symfony) and cyops-workflow (Django uWSGI))
# ---------------------------------------------------------------------------
log "H. nginx config"
sudo cp -r /etc/nginx/conf.d H_nginx_confd 2>/dev/null || true
sudo cp /etc/nginx/nginx.conf H_nginx.conf 2>/dev/null || true

# ---------------------------------------------------------------------------
# Pack
# ---------------------------------------------------------------------------
cd "${OUT_BASE}"
TGZ="${OUT_BASE}/fsrpb_recon_${STAMP}.tgz"
tar czf "${TGZ}" "${STAMP}/" 2>/dev/null
sudo chown csadmin:csadmin "${TGZ}" "${OUT}" -R 2>/dev/null || true

echo
echo "Done."
echo "  Folder : ${OUT}"
echo "  Tarball: ${TGZ}"
echo
echo "Pull back with:"
echo "  scp csadmin@<box>:${TGZ} ./"
