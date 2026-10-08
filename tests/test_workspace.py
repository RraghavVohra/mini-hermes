"""
Tests for tools/workspace.py.

Story: this is the security core, so we attack it on purpose. Each test
builds a throwaway workspace inside pytest's temp folder, so nothing real
is touched and nothing costs money.
"""
import pytest

import config
from tools import workspace


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "workspace"
    folder.mkdir()
    return folder


def test_plain_relative_path_resolves_inside_the_workspace(root):
    assert workspace.safe_path("notes.txt", root) == root.resolve() / "notes.txt"


def test_dot_returns_the_workspace_itself(root):
    # list_dir needs to be able to look at the workspace root.
    assert workspace.safe_path(".", root) == root.resolve()


def test_new_nested_path_that_does_not_exist_yet_is_allowed(root):
    # write_file must be able to create new files and folders.
    expected = root.resolve() / "skills" / "new_skill.md"
    assert workspace.safe_path("skills/new_skill.md", root) == expected


def test_dot_dot_traversal_out_of_the_workspace_is_blocked(root):
    with pytest.raises(PermissionError):
        workspace.safe_path("../secret.txt", root)


def test_dot_dot_that_stays_inside_is_allowed(root):
    # Why we check the destination, not the spelling.
    assert workspace.safe_path("sub/../a.txt", root) == root.resolve() / "a.txt"


def test_absolute_path_outside_the_workspace_is_blocked(root, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("top secret")
    with pytest.raises(PermissionError):
        workspace.safe_path(str(outside), root)


def test_absolute_path_inside_the_workspace_is_allowed(root):
    inside = root / "a.txt"
    assert workspace.safe_path(str(inside), root) == inside.resolve()


def test_empty_path_is_rejected(root):
    with pytest.raises(ValueError):
        workspace.safe_path("   ", root)


def test_non_string_path_is_rejected(root):
    # The model can send a number or null instead of a string.
    with pytest.raises(ValueError):
        workspace.safe_path(123, root)


def test_symlink_pointing_outside_the_workspace_is_blocked(root, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("top secret")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        # Windows only lets some accounts create symlinks.
        pytest.skip("this machine cannot create symlinks")
    with pytest.raises(PermissionError):
        workspace.safe_path("link.txt", root)


def test_the_real_workspace_cannot_reach_the_env_file():
    # The exact attack we care about, against the real config.
    with pytest.raises(PermissionError):
        workspace.safe_path("../.env")