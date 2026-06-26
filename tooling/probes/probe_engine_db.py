"""Reusable psql probe against the wf-engine `sealab` database.

The wf-engine keeps its own copy of every playbook (workflow_workflow,
workflow_step, workflow_step_next_steps, workflow_wfmetadata, …) in a
Postgres DB called `sealab`. This is the table set that actually drives
playbook EXECUTION — distinct from the API-platform's
workflow_collections/workflows/workflow_steps/workflow_routes which the
designer canvas reads from.

Why a probe: spinning up `manage.py shell` over SSH is 10–15s per call
because Django imports yaql/ansible/pkg_resources cold. `psql` from the
same host is sub-second. This probe SSHes once, runs psql, returns.

Usage:
    fsr_psql "SELECT count(*) FROM workflow_workflow"
    fsr_psql --file /tmp/big_query.sql
    fsr_psql --rows-only "SELECT name,uuid FROM workflow_workflow WHERE name='VT IP Reputation'"
    fsr_psql --db das "SELECT count(*) FROM workflow_collections"

DB creds are pulled from the workflow service config on first use and
cached at `~/.cache/fsrpb/engine_db.env` (mode 0600). To force a refresh:

    fsr_psql --refresh-creds "SELECT 1"

Auth: re-uses the SSH config from `probes._env` (FSR_SSH_HOST,
FSR_SSH_USER, FSR_SSH_PASSWORD, FSR_SSH_KEY_PATH).
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from . import _env

CACHE_DIR = Path.home() / ".cache" / "fsrpb"
CRED_FILE = CACHE_DIR / "engine_db.env"

# Map logical DB name -> (Postgres DB, default user). Both DBs live in the
# same Postgres instance (postgresql-16, port 5432, localhost on the box).
_DB_MAP = {
    # wf-engine (Django)
    "sealab": ("sealab", "cyberpgsql"),
    "engine": ("sealab", "cyberpgsql"),
    "wf": ("sealab", "cyberpgsql"),
    # API platform (PHP/Symfony)
    "das": ("das", "cyberpgsql"),
    "api": ("das", "cyberpgsql"),
    "platform": ("das", "cyberpgsql"),
}


def _ssh_cmd(cfg: _env.Config, remote: str) -> list[str]:
    """Build an ssh argv that runs `remote` on the FSR box.

    Uses key auth when `FSR_SSH_KEY_PATH` is set; otherwise relies on
    `sshpass`-style password injection. We don't shell out to expect —
    callers should set up key auth via probes._env (one-time `ssh-copy-id`)
    so this stays fast.
    """
    base = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes" if cfg.ssh_key_path else "BatchMode=no",
        "-p", str(cfg.ssh_port),
    ]
    if cfg.ssh_key_path:
        base += ["-i", cfg.ssh_key_path]
    base += [f"{cfg.ssh_user}@{cfg.ssh_host}", remote]
    return base


_EXPECT_TEMPLATE = r"""
# Drives openssh through a password prompt. Suppress all spawn output
# until we've consumed the password prompt, then start streaming the
# remote command's stdout to our stdout. We also discard the SSH banner
# (warnings, MOTD lines that end in "..." before the password prompt).
log_user 0
set timeout 120
set pw [lindex $argv 0]
set host [lindex $argv 1]
set user [lindex $argv 2]
set port [lindex $argv 3]
set remote [lindex $argv 4]
spawn -noecho ssh -o StrictHostKeyChecking=no \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o LogLevel=ERROR \
    -p $port $user@$host $remote
set sent_pw 0
expect {
  -re {(P|p)assword:\s*$} {
    if {$sent_pw == 0} {
      send "$pw\r"
      set sent_pw 1
      log_user 1
      exp_continue
    }
    send_user "AUTH_FAILED\n"
    exit 2
  }
  -re {Permission denied} { send_user "AUTH_FAILED\n"; exit 2 }
  -re {Connection refused|Could not resolve} { send_user "CONN_FAILED\n"; exit 3 }
  timeout { send_user "TIMEOUT\n"; exit 4 }
  eof { exit 0 }
}
"""


def _run_ssh(cfg: _env.Config, remote: str, *, stdin: str | None = None) -> str:
    """Run a remote command, returning stdout. Raises on non-zero exit.

    Uses key auth when available; otherwise drives ssh through `expect`
    to handle the password prompt. Stdin (if provided) is base64-encoded
    and decoded on the remote — that's the only quoting-safe way to ferry
    arbitrary SQL across ssh + bash without escaping land mines.
    """
    import base64
    env = os.environ.copy()
    if stdin is not None:
        b64 = base64.b64encode(stdin.encode()).decode()
        # Replace the trailing flags region with: base64 -> stdin into psql
        remote = f"echo {b64} | base64 -d | {remote}"

    if cfg.ssh_key_path or not cfg.ssh_password:
        cmd = _ssh_cmd(cfg, remote)
        res = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=180,
        )
    else:
        # Drive openssh via expect. The expect script lives in /tmp so we
        # don't have to escape the password through three levels of quoting.
        script = CACHE_DIR / "_ssh_driver.exp"
        if not script.exists() or script.read_text() != _EXPECT_TEMPLATE:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            script.write_text(_EXPECT_TEMPLATE)
            script.chmod(0o700)
        cmd = [
            "/usr/bin/expect", "-f", str(script), "--",
            cfg.ssh_password, cfg.ssh_host, cfg.ssh_user,
            str(cfg.ssh_port), remote, "",
        ]
        res = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=180,
        )

    if res.returncode != 0:
        msg = res.stderr.strip() or res.stdout.strip() or f"exit {res.returncode}"
        raise RuntimeError(f"ssh failed: {msg}")
    return res.stdout


def _bootstrap_creds(cfg: _env.Config) -> tuple[str, str]:
    """One-time fetch of (pg_user, pg_password) from the FSR box.

    Source of truth on FSR: the postgres password is the device UUID,
    stored at ~/device_uuid in the SSH user's home (readable by that
    user, no sudo). The user is always `cyberpgsql`. Cached locally so
    we never re-pay this cost.
    """
    if CRED_FILE.exists():
        env = {k.strip(): v.strip() for k, v in (
            line.split("=", 1) for line in CRED_FILE.read_text().splitlines()
            if "=" in line
        )}
        if "PGPASSWORD" in env and env["PGPASSWORD"]:
            return env.get("PGUSER", "cyberpgsql"), env["PGPASSWORD"]

    if not cfg.ssh_password and not cfg.ssh_key_path:
        raise RuntimeError(
            "no cached creds and no SSH auth configured. "
            f"Provide creds manually in {CRED_FILE} as PGUSER=…/PGPASSWORD=…"
        )

    pw = _run_ssh(cfg, "cat ~/device_uuid").strip()
    if not pw:
        raise RuntimeError(
            "could not read ~/device_uuid from FSR — file empty "
            "or unreadable as the SSH user"
        )
    user = "cyberpgsql"

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CRED_FILE.write_text(f"PGUSER={user}\nPGPASSWORD={pw}\n")
    CRED_FILE.chmod(0o600)
    return user, pw


def run_psql(
    sql: str, *, db: str = "sealab", rows_only: bool = False,
    expanded: bool = False, refresh_creds: bool = False,
) -> str:
    """Execute `sql` against the FSR box's Postgres and return stdout.

    `db` accepts logical names: sealab/engine/wf for the wf-engine,
    das/api/platform for the API platform.
    """
    cfg = _env.get_config()
    if refresh_creds and CRED_FILE.exists():
        CRED_FILE.unlink()

    pg_user, pg_pw = _bootstrap_creds(cfg)
    pg_db, default_user = _DB_MAP.get(db, (db, "cyberpgsql"))
    pg_user = pg_user or default_user

    flags = ["-X", "-A", "-q"]  # -A unaligned, -q quiet, -X no rcfile
    if rows_only:
        flags += ["-t"]
    if expanded:
        flags += ["-x"]

    # Pass SQL via stdin so we don't need to escape it for the remote shell.
    remote = (
        f"PGPASSWORD={shlex.quote(pg_pw)} "
        f"psql -h localhost -U {shlex.quote(pg_user)} -d {shlex.quote(pg_db)} "
        + " ".join(flags) + " -F '\\t' "
    )
    return _run_ssh(cfg, remote, stdin=sql)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fsr_psql",
        description="Run SQL against the FSR box's Postgres via SSH+psql.",
    )
    p.add_argument("sql", nargs="?", help="SQL to run (omit when using --file)")
    p.add_argument("--file", help="read SQL from file instead of positional arg")
    p.add_argument(
        "--db", default="sealab",
        help="logical DB: sealab/engine/wf (default) or das/api/platform",
    )
    p.add_argument(
        "--rows-only", action="store_true",
        help="psql -t (no headers, no row count)",
    )
    p.add_argument(
        "--expanded", "-x", action="store_true",
        help="psql -x (one column per line, easier on wide tables)",
    )
    p.add_argument(
        "--refresh-creds", action="store_true",
        help="discard cached PG creds and re-bootstrap",
    )
    args = p.parse_args(argv)

    if args.file:
        sql = Path(args.file).read_text()
    elif args.sql:
        sql = args.sql
    else:
        sql = sys.stdin.read()
    if not sql.strip():
        print("no SQL provided (positional, --file, or stdin)", file=sys.stderr)
        return 2

    try:
        out = run_psql(
            sql, db=args.db, rows_only=args.rows_only,
            expanded=args.expanded, refresh_creds=args.refresh_creds,
        )
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
