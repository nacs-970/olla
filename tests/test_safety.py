"""Tests for olla.safety.check."""

from olla.safety import ALLOWLIST, check


def test_allowlist_members_allow():
    for binary in ("ls", "pwd", "cat", "echo", "find", "grep", "head", "tail", "wc", "file", "date", "whoami", "env"):
        assert check([binary, "arg"], yes=False)["kind"] == "ALLOW", binary


def test_non_allowlisted_non_blocked_binary_confirms():
    assert check(["git", "status"], yes=False)["kind"] == "CONFIRM"


def test_allowlist_matches_whole_binary_only_not_subcommand():
    # argv[0] is "git", not allowlisted — never matches on subcommand.
    assert check(["git", "rm", "-rf", "."], yes=False)["kind"] != "ALLOW"


def test_hard_blocked_binaries_block():
    for binary in ("sudo", "su", "shutdown", "reboot", "poweroff", "halt"):
        decision = check([binary, "ls"], yes=False)
        assert decision["kind"] == "BLOCK", binary
        assert binary in decision["reason"]


def test_rm_dangerous_targets_block():
    for target in ("/", "~", "/*", "$HOME", "."):
        assert check(["rm", "-rf", target], yes=False)["kind"] == "BLOCK", target


def test_rm_non_dangerous_target_confirms():
    assert check(["rm", "myfile.txt"], yes=False)["kind"] == "CONFIRM"


def test_dd_on_raw_block_device_blocks():
    assert check(["dd", "if=/dev/zero", "of=/dev/sda"], yes=False)["kind"] == "BLOCK"


def test_mkfs_on_raw_block_device_blocks():
    assert check(["mkfs.ext4", "/dev/nvme0n1"], yes=False)["kind"] == "BLOCK"


def test_dd_not_targeting_raw_block_device_confirms():
    assert check(["dd", "if=/dev/zero", "of=/tmp/test.img"], yes=False)["kind"] == "CONFIRM"


def test_fork_bomb_pattern_blocks():
    assert check([":(){", ":|:&", "};:"], yes=False)["kind"] == "BLOCK"


def test_chmod_recursive_on_root_blocks():
    assert check(["chmod", "-R", "777", "/"], yes=False)["kind"] == "BLOCK"


def test_chown_recursive_on_root_blocks():
    assert check(["chown", "-R", "user", "/"], yes=False)["kind"] == "BLOCK"


def test_chmod_recursive_not_on_root_confirms():
    assert check(["chmod", "-R", "755", "/tmp/x"], yes=False)["kind"] == "CONFIRM"


def test_block_takes_precedence_over_allow():
    # Sanity: a genuinely allowlisted command with no blocklist match is ALLOW.
    assert check(["echo", "hi"], yes=False)["kind"] == "ALLOW"
    # `rm` is never in ALLOWLIST, so a blocklisted rm command can never fall
    # through to ALLOW.
    assert "rm" not in ALLOWLIST
    assert check(["rm", "-rf", "/"], yes=False)["kind"] == "BLOCK"


def test_yes_does_not_change_block_kind():
    assert check(["rm", "-rf", "/"], yes=True)["kind"] == "BLOCK"


def test_yes_does_not_change_confirm_kind():
    assert check(["git", "status"], yes=True)["kind"] == "CONFIRM"


def test_empty_argv_blocks_with_reason():
    decision = check([], yes=False)
    assert decision["kind"] == "BLOCK"
    assert "empty" in decision["reason"]
