"""Tests for olla.tools.files.read_file."""

from olla.tools.files import read_file


def test_read_file_success(tmp_path):
    path = tmp_path / "hello.txt"
    path.write_text("hello from file\n")

    result = read_file(str(path))

    assert result["path"] == str(path)
    assert result["content"] == "hello from file\n"
    assert "error" not in result


def test_read_file_not_found(tmp_path):
    path = tmp_path / "nope.txt"

    result = read_file(str(path))

    assert "error" in result
    assert str(path) in result["error"]
    assert "content" not in result
