"""Tests for olla.safety.check."""

from olla.safety import ALLOWLIST, check


def test_allowlist_members_allow():
    for binary in ("ls", "pwd", "cat", "echo", "grep", "head", "tail", "wc", "file", "date", "whoami"):
        assert check([binary, "arg"], yes=False)["kind"] == "ALLOW", binary


def test_non_allowlisted_non_blocked_binary_confirms():
    assert check(["git", "status"], yes=False)["kind"] == "CONFIRM"


def test_allowlist_matches_whole_binary_only_not_subcommand():
    # argv[0] is "git", not allowlisted — never matches on subcommand.
    assert check(["git", "rm", "-rf", "."], yes=False)["kind"] != "ALLOW"


def test_env_not_in_allowlist():
    assert "env" not in ALLOWLIST


def test_find_not_in_allowlist():
    assert "find" not in ALLOWLIST


def test_env_wrapping_blocked_command_blocks():
    decision = check(["env", "rm", "-rf", "/"], yes=False)
    assert decision["kind"] == "BLOCK"
    assert "'env' wraps a blocked command" in decision["reason"]


def test_env_wrapping_rm_dangerous_target_blocks():
    decision = check(["env", "rm", "-rf", "/"], yes=False)
    assert decision["kind"] == "BLOCK"
    assert "rm" in decision["reason"]


def test_env_wrapping_sudo_blocks():
    assert check(["env", "sudo", "ls"], yes=False)["kind"] == "BLOCK"


def test_env_wrapping_dd_on_raw_device_blocks():
    assert check(["env", "dd", "if=/dev/zero", "of=/dev/sda"], yes=False)["kind"] == "BLOCK"


def test_env_with_var_assignment_and_harmless_command_confirms():
    assert check(["env", "FOO=bar", "ls", "-la"], yes=False)["kind"] == "CONFIRM"


def test_env_unset_flag_with_arg_wrapping_sudo_blocks():
    decision = check(["env", "-u", "FOO", "sudo", "rm", "-rf", "/"], yes=False)
    assert decision["kind"] == "BLOCK"
    assert "env" in decision["reason"]
    assert "sudo" in decision["reason"]


def test_env_chdir_flag_with_arg_wrapping_sudo_blocks():
    assert check(["env", "-C", "/tmp", "sudo", "ls"], yes=False)["kind"] == "BLOCK"


def test_env_split_string_flag_wrapping_sudo_confirms():
    # -S consumes its argument as a single string for env to re-split itself;
    # _unwrap_env does not parse into that string, so this remains CONFIRM.
    assert check(["env", "-S", "sudo rm -rf /"], yes=False)["kind"] == "CONFIRM"


def test_find_exec_rm_on_placeholder_confirms_not_allow():
    assert check(["find", ".", "-exec", "rm", "-rf", "{}", ";"], yes=False)["kind"] != "ALLOW"


def test_find_exec_sudo_blocks():
    assert check(["find", "/", "-exec", "sudo", "rm", "{}", ";"], yes=False)["kind"] == "BLOCK"


def test_find_multi_exec_second_clause_sudo_blocks():
    decision = check(
        ["find", ".", "-exec", "true", ";", "-exec", "sudo", "rm", "-rf", "/", ";"],
        yes=False,
    )
    assert decision["kind"] == "BLOCK"
    assert "find" in decision["reason"]
    assert "sudo" in decision["reason"]


def test_fork_bomb_unspaced_variant_blocks():
    assert check([":(){:|:&};:"], yes=False)["kind"] == "BLOCK"


def test_fork_bomb_as_echo_data_allows():
    decision = check(["echo", "Avoid running :(){ :|:& };: it's a fork bomb"], yes=False)
    assert decision["kind"] == "ALLOW"


def test_fork_bomb_via_bash_dash_c_blocks():
    assert check(["bash", "-c", ":(){ :|:& };:"], yes=False)["kind"] == "BLOCK"


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


def test_chmod_combined_recursive_force_on_root_blocks():
    decision = check(["chmod", "-Rf", "777", "/"], yes=False)
    assert decision["kind"] == "BLOCK"
    assert "chmod -R" in decision["reason"]
    assert "/" in decision["reason"]


def test_chown_combined_recursive_force_on_root_blocks():
    assert check(["chown", "-Rf", "user", "/"], yes=False)["kind"] == "BLOCK"


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
