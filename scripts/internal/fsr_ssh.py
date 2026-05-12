#!/usr/bin/env python3
"""SSH/SCP utility for the FSR appliance — reads password from .env.

Usage:
    fsr_ssh.py [-u csadmin|root] -- <remote command...>
    fsr_ssh.py [-u csadmin|root] --put  <local>  <remote>
    fsr_ssh.py [-u csadmin|root] --get  <remote> <local>

The password is read once from FSR_PASSWORD in the project .env and
passed to the child via an environment variable so it is never written
to argv, the filesystem, or stdout. The expect wrapper consumes it
inside the spawn'd child and is unset before any user output.

Exit code propagates the remote command's exit code.
"""
from __future__ import annotations

import argparse
import os
import pty
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_HOST = os.environ.get("FSR_SSH_HOST", "10.99.249.205")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Banner / warning lines we discard before scanning for "password:"
_BANNER_RE = re.compile(
    rb"(WARNING:|This session|The server may|See https://openssh|"
    rb"connection is not using|post-quantum|csadmin@.*Permission denied)"
)


def _load_password() -> str:
    if not ENV_PATH.exists():
        sys.exit(f"missing {ENV_PATH}")
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("FSR_PASSWORD="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if not v:
                sys.exit("FSR_PASSWORD is empty in .env")
            return v
    sys.exit("FSR_PASSWORD not found in .env")


def _spawn_with_password(argv: list[str], password: str) -> int:
    """Run argv in a PTY, intercept the first 'password:' prompt, then
    stream stdout/stderr until EOF. Password is sent over the PTY (never
    echoed; ssh doesn't echo password input). Returns child exit code.
    """
    pid, fd = pty.fork()
    if pid == 0:
        # child
        try:
            os.execvp(argv[0], argv)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"exec failed: {e}\n")
            os._exit(127)

    # parent
    sent = False
    buf = b""
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        # Only feed password before we've seen a clean prompt+newline
        if not sent:
            if b"password:" in buf.lower() or b"password: " in buf.lower():
                os.write(fd, password.encode() + b"\n")
                sent = True
                # Drop the prompt line so we don't print "password:" to user
                buf = buf.split(b"\n", 1)[-1] if b"\n" in buf else b""
                continue
        # Strip banner lines from output
        lines = buf.split(b"\n")
        buf = lines[-1]  # keep partial last line in buffer
        for line in lines[:-1]:
            if not _BANNER_RE.search(line):
                sys.stdout.buffer.write(line + b"\n")
                sys.stdout.flush()
    if buf and not _BANNER_RE.search(buf):
        sys.stdout.buffer.write(buf)
        sys.stdout.flush()
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else (status >> 8)


def main() -> int:
    p = argparse.ArgumentParser(
        description="SSH/SCP to the FSR appliance using password from .env"
    )
    p.add_argument("-u", "--user", default="csadmin",
                   choices=["csadmin", "root"],
                   help="remote user (default: csadmin; root has same password)")
    p.add_argument("-H", "--host", default=DEFAULT_HOST,
                   help=f"host (default: {DEFAULT_HOST})")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--put", nargs=2, metavar=("LOCAL", "REMOTE"),
                   help="upload LOCAL → user@host:REMOTE")
    g.add_argument("--get", nargs=2, metavar=("REMOTE", "LOCAL"),
                   help="download user@host:REMOTE → LOCAL")
    g.add_argument("cmd", nargs="*", default=None,
                   help="remote command to run")
    args = p.parse_args()

    password = _load_password()
    target = f"{args.user}@{args.host}"
    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
    ]

    if args.put:
        local, remote = args.put
        argv = ["scp"] + ssh_opts + [local, f"{target}:{remote}"]
    elif args.get:
        remote, local = args.get
        argv = ["scp"] + ssh_opts + [f"{target}:{remote}", local]
    else:
        if not args.cmd:
            p.error("no remote command given")
        argv = ["ssh"] + ssh_opts + [target, " ".join(args.cmd)]

    return _spawn_with_password(argv, password)


if __name__ == "__main__":
    sys.exit(main())
