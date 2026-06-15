"""Tests for olla.tools.files.read_file."""

from olla.tools.files import read_file, write_file


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


def test_write_file_success(tmp_path):
    path = tmp_path / "out.txt"

    result = write_file(str(path), "hello\n")

    assert path.read_text(encoding="utf-8") == "hello\n"
    assert result["path"] == str(path)
    assert result["bytes_written"] == 6
    assert "error" not in result


def test_write_file_missing_parent_dir_errors(tmp_path):
    path = tmp_path / "nonexistent_dir" / "out.txt"

    result = write_file(str(path), "content")

    assert "error" in result
    assert "parent directory" in result["error"]
    assert not path.parent.exists()
