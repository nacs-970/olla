"""Tests for inspection tools."""

import os

from olla.tools.inspect import grep_files, list_dir


def test_list_dir_populated(tmp_path):
    (tmp_path / "a_file.txt").write_bytes(b"hello")
    (tmp_path / "z_file.txt").write_bytes(b"world")
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "y_dir").mkdir()
    os.symlink(tmp_path / "b_dir", tmp_path / "s_link")

    result = list_dir(str(tmp_path))
    content = result["content"].split("\n")
    
    assert "[d] b_dir" in content[0]
    assert "[d] y_dir" in content[1]
    assert "[f] a_file.txt" in content[2]
    assert "[l] s_link -> " in content[3]
    assert "[f] z_file.txt" in content[4]


def test_list_dir_human_size(tmp_path):
    (tmp_path / "file.txt").write_bytes(b"x" * 1500)
    result = list_dir(str(tmp_path))
    assert "1.5K" in result["content"]


def test_list_dir_symlink_not_followed(tmp_path):
    target = tmp_path / "target_dir"
    target.mkdir()
    link = tmp_path / "link"
    os.symlink(target, link)

    result = list_dir(str(tmp_path))
    assert "[l] link -> " in result["content"]
    assert "[d] link" not in result["content"]


def test_list_dir_hidden_dotfile(tmp_path):
    (tmp_path / ".env").write_bytes(b"SECRET=1")
    result = list_dir(str(tmp_path))
    assert "[f] .env" in result["content"]


def test_list_dir_truncation(tmp_path):
    for i in range(51):
        (tmp_path / f"file_{i:02d}.txt").touch()

    result = list_dir(str(tmp_path))
    lines = result["content"].split("\n")
    assert len(lines) == 51
    assert "not shown" in lines[-1]


def test_list_dir_nonexistent():
    result = list_dir("/does/not/exist/ever")
    assert "content" not in result
    assert "error" in result
    assert "not found" in result["error"]


def test_list_dir_on_file(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.touch()
    result = list_dir(str(file_path))
    assert "content" not in result
    assert "error" in result
    assert "not a directory" in result["error"]


def test_grep_files_matches_case_sensitive(tmp_path):
    (tmp_path / "file.txt").write_text("hello world\nHELLO world\n", encoding="utf-8")
    result = grep_files("hello", str(tmp_path))
    assert "file.txt:1:hello world" in result["content"]
    assert "HELLO" not in result["content"]


def test_grep_files_recursive_false_skips_subdir(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("hello\n", encoding="utf-8")
    result = grep_files("hello", str(tmp_path), recursive=False)
    assert result["content"] == ""


def test_grep_files_recursive_true_descends(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("hello\n", encoding="utf-8")
    result = grep_files("hello", str(tmp_path), recursive=True)
    assert "file.txt:1:hello" in result["content"]


def test_grep_files_excludes_git(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("hello\n", encoding="utf-8")
    result = grep_files("hello", str(tmp_path), recursive=True)
    assert result["content"] == ""


def test_grep_files_skips_binary(tmp_path):
    (tmp_path / "bin.dat").write_bytes(b"\x00hello")
    result = grep_files("hello", str(tmp_path))
    assert result["content"] == ""


def test_grep_files_invalid_regex(tmp_path):
    result = grep_files("(", str(tmp_path))
    assert "content" not in result
    assert "error" in result
    assert "invalid regex" in result["error"]


def test_grep_files_truncation(tmp_path):
    lines = ["hello\n"] * 30
    (tmp_path / "file.txt").write_text("".join(lines), encoding="utf-8")
    result = grep_files("hello", str(tmp_path))
    out_lines = result["content"].split("\n")
    assert len(out_lines) == 26
    assert "not shown" in out_lines[-1]
