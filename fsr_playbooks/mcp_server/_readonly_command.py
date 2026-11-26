"""Is a shell command line free of any write effect on the host?

An op that executes a command line (ssh `run_remote_command`) has no catalog
category and its effect is in the argument, not the op name. So the guard
tiers the invocation: a command that provably only reads (a log read, a process
listing) is a read, anything else keeps the approval gate.

The test is a grammar, not a reading of the model's prose: the line is tokenised
like a shell would, and every pipeline stage must be a program on a short allow
list of readers, called with none of the flags that make that program write,
delete, execute another program, or follow a stream forever. Anything the parser
cannot account for (redirection, command or variable substitution, `;`, `&&`,
`||`, background `&`, an unknown program, an unbalanced quote) is NOT read-only.
Fail closed: a false "not read-only" costs one approval card; a false
"read-only" would run a write ungated.
"""
from __future__ import annotations

import posixpath
import shlex

# Programs whose every invocation (minus the flags below) only reads.
_READERS = frozenset({
    "cat", "zcat", "bzcat", "xzcat", "head", "tail", "grep", "egrep", "fgrep",
    "zgrep", "ls", "wc", "sort", "uniq", "cut", "tr", "nl", "rev", "tac",
    "stat", "file", "du", "df", "ps", "pgrep", "who", "w", "last", "lastb",
    "lastlog", "id", "whoami", "hostname", "uname", "date", "uptime", "free",
    "ss", "netstat", "lsof", "journalctl", "dmesg", "getent", "echo", "pwd",
    "find", "basename", "dirname", "readlink", "realpath", "lscpu", "arch",
})

# Flags that turn an otherwise-reading program into a writer, an executor, or
# an endless stream. Matched on the exact token or its `--flag=value` head.
_BAD_FLAGS: dict[str, frozenset[str]] = {
    "find": frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir",
                       "-fprint", "-fprint0", "-fprintf", "-fls"}),
    "sort": frozenset({"-o", "--output", "--compress-program"}),
    "tail": frozenset({"-f", "-F", "--follow"}),
    "journalctl": frozenset({"-f", "--follow", "--vacuum-size", "--vacuum-time",
                             "--vacuum-files", "--rotate", "--flush", "--sync",
                             "--setup-keys", "--relinquish-var"}),
    "dmesg": frozenset({"-c", "-C", "--clear", "--read-clear", "-w", "--follow",
                        "-n", "--console-level", "-D", "-E"}),
    "date": frozenset({"-s", "--set"}),
    "hostname": frozenset({"-b", "-F", "--file"}),
}

# Programs that write if given a second positional (uniq IN OUT) or a bare one
# (date MMDDhhmm sets the clock, hostname NAME renames the host).
_MAX_POSITIONALS: dict[str, int] = {"uniq": 1, "hostname": 0}
_DATE_OK_POSITIONAL_PREFIX = "+"

_BIN_DIRS = frozenset({"/bin", "/usr/bin", "/sbin", "/usr/sbin", "/usr/local/bin"})
_FORBIDDEN_CHARS = ("`", "$", "\n", "\r", "\x00")
_ALLOWED_CONTROL = {"|"}


def _program(token: str) -> str | None:
    """The bare program name, or None for a path outside the system bin dirs."""
    if "/" not in token:
        return token
    head, tail = posixpath.split(token)
    return tail if head in _BIN_DIRS else None


def _stage_is_read_only(words: list[str]) -> bool:
    if not words:
        return False
    prog = _program(words[0])
    if prog is None or prog not in _READERS:
        return False
    args = words[1:]
    bad = _BAD_FLAGS.get(prog, frozenset())
    positionals = 0
    for a in args:
        head = a.split("=", 1)[0] if a.startswith("--") else a
        if head in bad:
            return False
        # A short-flag cluster such as `-fn` hides `-f`: check each letter.
        if prog in ("tail", "sort", "dmesg", "date", "journalctl") \
                and a.startswith("-") and not a.startswith("--") and len(a) > 2:
            if any(f"-{ch}" in bad for ch in a[1:]):
                return False
        if not a.startswith("-"):
            positionals += 1
            if prog == "date" and not a.startswith(_DATE_OK_POSITIONAL_PREFIX):
                return False
    cap = _MAX_POSITIONALS.get(prog)
    if cap is not None and positionals > cap:
        return False
    return True


def is_read_only_command(command: str) -> bool:
    """True only when `command` is a pipeline of allow-listed readers with no
    redirection, substitution, chaining or write/exec flag."""
    if not isinstance(command, str) or not command.strip():
        return False
    if any(ch in command for ch in _FORBIDDEN_CHARS):
        return False
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:  # unbalanced quote
        return False
    stage: list[str] = []
    stages: list[list[str]] = []
    for tok in tokens:
        if tok and all(c in "();<>|&" for c in tok):
            if tok not in _ALLOWED_CONTROL:
                return False
            stages.append(stage)
            stage = []
        else:
            stage.append(tok)
    stages.append(stage)
    return all(_stage_is_read_only(s) for s in stages)


# Ops that execute a command line the caller supplies. They carry no catalog
# category (their effect is in the argument, not the op), so every call used to
# land on the unknown-op tier 3, a log read included. The invocation is tiered
# instead: (connector, op) -> the param that holds the command line.
COMMAND_EXEC_OPS: dict[tuple[str, str], str] = {
    ("ssh", "run_remote_command"): "cmd",
}


def command_exec_param(connector: str, op: str) -> str | None:
    """The param holding the command line when (connector, op) executes one."""
    return COMMAND_EXEC_OPS.get((str(connector or "").lower(), str(op or "").lower()))


def op_call_is_read_only_command(connector: str, op: str, params: object) -> bool:
    """True when this is a command-exec op whose command line only reads."""
    key = command_exec_param(connector, op)
    if key is None or not isinstance(params, dict):
        return False
    return is_read_only_command(params.get(key))
