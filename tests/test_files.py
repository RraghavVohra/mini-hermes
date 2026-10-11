"""
Tests for tools/files.py (read_file).

Story: all free, no API. The paging rules are tested on their own with
read_page(), then read_file is tested against a throwaway workspace that
pytest builds in a temp folder (config.WORKSPACE_DIR is pointed at it).
"""
import pytest
import os

import agent_loop
import config

from tools.files import (
    format_listing,
    list_dir,
    read_file,
    read_page,
    registry,
    write_file,
)

BIG = 100_000  # a character budget too large to matter in the paging tests


@pytest.fixture
def workspace_dir(tmp_path, monkeypatch):
    folder = tmp_path / "workspace"
    folder.mkdir()
    # safe_path reads config.WORKSPACE_DIR at call time, so this redirects
    # every file tool into the temp folder.
    monkeypatch.setattr(config, "WORKSPACE_DIR", folder)
    return folder


def numbered(count):
    return "\n".join(f"L{i}" for i in range(1, count + 1))


# --- read_page: the paging rules, pure ---

def test_page_returns_a_short_file_unchanged():
    assert read_page("a\nb\nc", 1, 200, BIG) == "a\nb\nc"


def test_page_reports_an_empty_file():
    assert read_page("", 1, 200, BIG) == "[File is empty]"


def test_page_first_page_tells_the_model_how_to_continue():
    result = read_page(numbered(10), 1, 3, BIG)
    assert result.startswith("L1\nL2\nL3")
    assert "Showing lines 1-3 of 10" in result
    assert "start_line=4" in result


def test_page_middle_page_uses_the_requested_start_line():
    result = read_page(numbered(10), 4, 3, BIG)
    assert result.startswith("L4\nL5\nL6")
    assert "Showing lines 4-6 of 10" in result


def test_page_last_page_has_no_continue_instruction():
    result = read_page(numbered(10), 8, 3, BIG)
    assert "Showing lines 8-10 of 10" in result
    assert "To continue" not in result


def test_page_start_past_the_end_is_rejected():
    with pytest.raises(ValueError):
        read_page(numbered(5), 99, 3, BIG)


def test_page_stops_at_the_character_budget_before_the_line_limit():
    text = "\n".join(["x" * 100] * 5)  # each line costs 101 characters
    result = read_page(text, 1, 10, 250)
    assert "Showing lines 1-2 of 5" in result


def test_page_cuts_a_single_line_that_is_too_long():
    result = read_page("y" * 1000, 1, 10, 100)
    assert result.startswith("y" * 100)
    assert "was longer than the output limit" in result


# --- read_file: the tool itself ---

def test_read_file_returns_file_content(workspace_dir):
    (workspace_dir / "a.txt").write_text("hello", encoding="utf-8")
    assert read_file("a.txt") == "hello"


def test_read_file_default_page_size_comes_from_config(workspace_dir):
    count = config.READ_DEFAULT_MAX_LINES + 50
    (workspace_dir / "big.txt").write_text(numbered(count), encoding="utf-8")
    result = read_file("big.txt")
    assert f"Showing lines 1-{config.READ_DEFAULT_MAX_LINES} of {count}" in result


def test_read_file_missing_file_error_steers_the_model_to_list_dir(workspace_dir):
    with pytest.raises(FileNotFoundError, match="list_dir"):
        read_file("nope.txt")


def test_read_file_directory_error_steers_the_model_to_list_dir(workspace_dir):
    (workspace_dir / "sub").mkdir()
    with pytest.raises(IsADirectoryError, match="list_dir"):
        read_file("sub")


def test_read_file_rejects_binary_files(workspace_dir):
    (workspace_dir / "blob.bin").write_bytes(b"\xff\xfe\xfd")
    with pytest.raises(ValueError, match="UTF-8"):
        read_file("blob.bin")


def test_read_file_cannot_escape_the_workspace(workspace_dir, tmp_path):
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    with pytest.raises(PermissionError):
        read_file("../secret.txt")


def test_read_file_rejects_start_line_below_one(workspace_dir):
    (workspace_dir / "a.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="start_line"):
        read_file("a.txt", start_line=0)


def test_read_file_refuses_files_over_the_size_limit(workspace_dir, monkeypatch):
    monkeypatch.setattr(config, "MAX_READ_FILE_BYTES", 10)
    (workspace_dir / "big.txt").write_text("x" * 50, encoding="utf-8")
    with pytest.raises(ValueError, match="read limit"):
        read_file("big.txt")


def test_read_file_output_never_exceeds_the_tool_output_cap(workspace_dir):
    # Page plus footer must always fit, so run_tool_call's blunt
    # truncation never has to fire.
    (workspace_dir / "huge.txt").write_text(
        "\n".join(["x" * 50] * 5000), encoding="utf-8"
    )
    result = read_file("huge.txt")
    assert len(result) <= config.MAX_TOOL_OUTPUT_CHARS
    assert "To continue" in result


# --- registry and loop integration ---

def test_read_file_is_registered_with_a_strict_definition():
    # The registry validated the schema when files.py was imported.
    definitions = {d["name"]: d for d in registry.definitions()}
    assert definitions["read_file"]["strict"] is True


def make_call(arguments):
    from types import SimpleNamespace

    return SimpleNamespace(name="read_file", call_id="c1", arguments=arguments)


def test_read_file_works_through_run_tool_call_with_null_arguments(workspace_dir):
    (workspace_dir / "a.txt").write_text("hello", encoding="utf-8")
    call = make_call('{"path":"a.txt","start_line":null,"max_lines":null}')
    out = agent_loop.run_tool_call(call, registry.functions())
    assert out["output"] == "hello"


def test_read_file_jail_violation_becomes_an_error_for_the_model(workspace_dir):
    call = make_call('{"path":"../x.txt","start_line":null,"max_lines":null}')
    out = agent_loop.run_tool_call(call, registry.functions())
    assert out["output"].startswith("Error:")
    assert "outside the workspace" in out["output"]

# --- write_file ---

def test_write_file_creates_a_new_file(workspace_dir):
    result = write_file("a.txt", "hello", False)
    assert (workspace_dir / "a.txt").read_text(encoding="utf-8") == "hello"
    assert result.startswith("Created a.txt")


def test_write_file_creates_missing_parent_folders(workspace_dir):
    write_file("skills/research/notes.md", "hi", False)
    assert (workspace_dir / "skills" / "research" / "notes.md").exists()


def test_write_file_refuses_to_overwrite_unless_asked(workspace_dir):
    (workspace_dir / "a.txt").write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError, match="overwrite"):
        write_file("a.txt", "new", False)
    # The protected file is untouched.
    assert (workspace_dir / "a.txt").read_text(encoding="utf-8") == "original"


def test_write_file_overwrites_when_asked(workspace_dir):
    (workspace_dir / "a.txt").write_text("original", encoding="utf-8")
    result = write_file("a.txt", "new", True)
    assert (workspace_dir / "a.txt").read_text(encoding="utf-8") == "new"
    assert result.startswith("Overwrote a.txt")


def test_write_file_rejects_oversized_content(workspace_dir):
    too_big = "x" * (config.MAX_WRITE_CHARS + 1)
    with pytest.raises(ValueError, match="limit"):
        write_file("big.txt", too_big, False)
    assert not (workspace_dir / "big.txt").exists()


def test_write_file_cannot_escape_the_workspace(workspace_dir, tmp_path):
    with pytest.raises(PermissionError):
        write_file("../evil.txt", "x", True)
    assert not (tmp_path / "evil.txt").exists()


def test_write_file_rejects_a_directory_path(workspace_dir):
    (workspace_dir / "sub").mkdir()
    with pytest.raises(IsADirectoryError):
        write_file("sub", "x", True)


def test_write_file_uses_unix_newlines(workspace_dir):
    # On Windows, plain text mode would have written b"a\r\nb".
    write_file("n.txt", "a\nb", False)
    assert (workspace_dir / "n.txt").read_bytes() == b"a\nb"


def test_write_file_handles_non_ascii_text(workspace_dir):
    text = "नमस्ते दुनिया"
    write_file("hi.txt", text, False)
    assert read_file("hi.txt") == text


def test_failed_replace_leaves_the_original_intact_and_no_temp_files(
    workspace_dir, monkeypatch
):
    target = workspace_dir / "a.txt"
    target.write_text("original", encoding="utf-8")

    def locked(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(PermissionError, match="another program"):
        write_file("a.txt", "new content", True)

    # The point of atomic writes: the old file survives, and no half-written
    # temp file is left lying around.
    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in workspace_dir.iterdir()] == ["a.txt"]


def test_write_file_rejects_a_path_that_runs_through_a_file(workspace_dir):
    (workspace_dir / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not a folder"):
        write_file("a.txt/b.md", "x", False)


def test_write_file_is_registered_with_a_strict_definition():
    definitions = {d["name"]: d for d in registry.definitions()}
    assert definitions["write_file"]["strict"] is True
    overwrite = definitions["write_file"]["parameters"]["properties"]["overwrite"]
    assert overwrite["type"] == "boolean"


def make_tool_call(name, arguments):
    from types import SimpleNamespace

    return SimpleNamespace(name=name, call_id="c1", arguments=arguments)


def test_write_file_works_through_run_tool_call_with_a_boolean(workspace_dir):
    call = make_tool_call(
        "write_file", '{"path":"n.txt","content":"hi","overwrite":false}'
    )
    out = agent_loop.run_tool_call(call, registry.functions())
    assert out["output"].startswith("Created n.txt")
    assert (workspace_dir / "n.txt").read_text(encoding="utf-8") == "hi"


def test_write_file_jail_violation_becomes_an_error_for_the_model(workspace_dir):
    call = make_tool_call(
        "write_file", '{"path":"../x.txt","content":"hi","overwrite":true}'
    )
    out = agent_loop.run_tool_call(call, registry.functions())
    assert out["output"].startswith("Error:")
    assert "outside the workspace" in out["output"]

# --- list_dir ---

def test_listing_puts_folders_first_then_files_alphabetically():
    entries = [
        ("b.txt", False, 5),
        ("Zeta", True, None),
        ("a.txt", False, 1234),
        ("alpha", True, None),
    ]
    result = format_listing(entries, 200, BIG)
    assert result.split("\n") == [
        "alpha/",
        "Zeta/",
        "a.txt (1,234 bytes)",
        "b.txt (5 bytes)",
    ]


def test_listing_reports_an_empty_folder():
    assert format_listing([], 200, BIG) == "[Folder is empty]"


def test_listing_caps_entries_and_steers_the_model():
    entries = [(f"f{i}.txt", False, 1) for i in range(5)]
    result = format_listing(entries, 3, BIG)
    assert "Showing 3 of 5 entries" in result
    assert "subfolder" in result
    assert len([l for l in result.split("\n") if l.endswith("bytes)")]) == 3


def test_listing_stops_at_the_character_budget():
    # Each line is 100 + len(" (1 bytes)") = 110 characters, plus a newline.
    entries = [(f"{i}" + "x" * 99, False, 1) for i in range(5)]
    result = format_listing(entries, 200, 250)
    assert "Showing 2 of 5 entries" in result


def test_listing_shows_unknown_size_without_crashing():
    result = format_listing([("ghost.txt", False, None)], 200, BIG)
    assert result == "ghost.txt (size unknown)"


def test_list_dir_lists_workspace_contents(workspace_dir):
    (workspace_dir / "sub").mkdir()
    (workspace_dir / "a.txt").write_text("hello", encoding="utf-8")
    assert list_dir(".") == "sub/\na.txt (5 bytes)"


def test_list_dir_on_a_workspace_that_does_not_exist_yet_reports_empty(
    tmp_path, monkeypatch
):
    missing = tmp_path / "workspace"
    monkeypatch.setattr(config, "WORKSPACE_DIR", missing)
    assert list_dir(".") == "[Folder is empty]"
    assert not missing.exists()  # listing must not create anything


def test_list_dir_missing_folder_error_steers_the_model(workspace_dir):
    with pytest.raises(FileNotFoundError, match="list_dir"):
        list_dir("nope")


def test_list_dir_on_a_file_steers_the_model_to_read_file(workspace_dir):
    (workspace_dir / "a.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(NotADirectoryError, match="read_file"):
        list_dir("a.txt")


def test_list_dir_cannot_escape_the_workspace(workspace_dir):
    with pytest.raises(PermissionError):
        list_dir("..")


def test_list_dir_caps_entries_from_config(workspace_dir, monkeypatch):
    monkeypatch.setattr(config, "MAX_LIST_ENTRIES", 3)
    for i in range(5):
        (workspace_dir / f"f{i}.txt").write_text("", encoding="utf-8")
    assert "Showing 3 of 5 entries" in list_dir(".")


def test_list_dir_output_never_exceeds_the_tool_output_cap(workspace_dir):
    # 250 files with long names: the character budget cuts before the count does.
    for i in range(250):
        (workspace_dir / f"{'f' * 60}{i:03d}").write_text("", encoding="utf-8")
    result = list_dir(".")
    assert len(result) <= config.MAX_TOOL_OUTPUT_CHARS
    assert "Showing" in result


def test_list_dir_is_registered_with_a_strict_definition():
    definitions = {d["name"]: d for d in registry.definitions()}
    assert definitions["list_dir"]["strict"] is True


def test_list_dir_works_through_run_tool_call(workspace_dir):
    (workspace_dir / "a.txt").write_text("hello", encoding="utf-8")
    call = make_tool_call("list_dir", '{"path":"."}')
    out = agent_loop.run_tool_call(call, registry.functions())
    assert "a.txt (5 bytes)" in out["output"]

