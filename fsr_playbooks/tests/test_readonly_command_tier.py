"""A shell-exec op is tiered by the command it runs, not by its name.

`ssh.run_remote_command` has no catalog category, so every call used to resolve
to tier 3 and a plain log read stopped on an approval card. A command that only
reads now runs as a read (tier 2); anything that can change the host stays
tier 3.
"""
import pytest

from fsr_playbooks.llm.tools import _resolve_tier, _tier_for_run_op
from fsr_playbooks.mcp_server._readonly_command import is_read_only_command

SSH = {"connector": "ssh", "op": "run_remote_command"}


def _call(cmd, **extra):
    return {**SSH, "params": {"cmd": cmd, **extra}}


@pytest.mark.parametrize("cmd", [
    "ls -lt /var/log",
    "tail -n 200 /var/log/auth.log",
    "grep -i sgreer /var/log/auth.log | tail -n 20",
    "cat /var/log/syslog | grep rclone | wc -l",
    "journalctl -u sshd --since today",
    "ps aux | grep rclone",
    "last -n 20",
    "find /var/log -name '*.log' -mtime -1",
    "date +%s",
])
def test_a_read_only_command_runs_as_a_read(cmd):
    assert is_read_only_command(cmd)
    assert _tier_for_run_op(_call(cmd)) == 2
    assert _resolve_tier("run_op", _call(cmd)) == 2
    # Running it as root does not make a read a write.
    assert _tier_for_run_op(_call(cmd, is_super_user=True)) == 2


@pytest.mark.parametrize("cmd", [
    "rm -rf /var/log/old",
    "cat /etc/passwd > /tmp/x",
    "echo hi >> /etc/motd",
    "grep foo /var/log/syslog; rm x",
    "ls && reboot",
    "ls & reboot",
    "echo $(reboot)",
    "ls `reboot`",
    "find / -name x -delete",
    "find / -name x -exec rm {} +",
    "tail -f /var/log/syslog",
    "sort -o /etc/hosts /etc/hosts",
    "uniq in out",
    "date -s 2020-01-01",
    "date 010100002030",
    "hostname newname",
    "journalctl --vacuum-time=1s",
    "dmesg -C",
    "systemctl stop sshd",
    "bash -c ls",
    "sudo ls",
    "/tmp/ls",
    "cat 'unbalanced",
    "",
    "   ",
])
def test_anything_that_can_change_the_host_stays_gated(cmd):
    assert not is_read_only_command(cmd)
    assert _tier_for_run_op(_call(cmd)) >= 3


def test_a_missing_or_non_text_command_stays_gated():
    assert _tier_for_run_op(SSH) >= 3
    assert _tier_for_run_op({**SSH, "params": {"cmd": ["ls"]}}) >= 3


def test_only_the_declared_command_op_is_reclassified():
    # Same param name on another connector's op: no reclassification.
    other = {"connector": "fortigate-firewall", "op": "execute_command",
             "params": {"cmd": "ls"}}
    assert _tier_for_run_op(other) >= 4
