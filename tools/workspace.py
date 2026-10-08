"""
tools/workspace.py: the jail for the agent's file tools.

Story: the model chooses the path, but OUR code touches the disk, with our
Windows account's permissions. Without a check, a wrong guess or a prompt
injection hidden in a file could make the agent read .env or overwrite our
code. Every file tool must call safe_path() before touching anything.
"""
from pathlib import Path

import config


def safe_path(relative_path, root=None) -> Path:
    """Return the real absolute path for `relative_path`, or raise.

    Raises ValueError for a missing/non-string path and PermissionError for
    a path that lands outside the workspace. run_tool_call turns both into
    an "Error: ..." the model can read and correct.

    `root` defaults to the configured workspace. It is a parameter so tests
    can use a temporary folder.
    """
    # The model writes the arguments, so it may send a number, null, or "".
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Path must be a non-empty string")

    root = (root or config.WORKSPACE_DIR).resolve()

    # Join, then resolve. resolve() removes ".." and follows symlinks, so
    # `candidate` is where the path REALLY points. If relative_path is
    # absolute (like C:\Windows), the join throws our root away and the
    # absolute path wins; the check below catches that too.
    candidate = (root / relative_path).resolve()

    # Judge the destination, not the spelling. A string check for ".." would
    # block legit "sub/../a.txt" and miss absolute paths and symlinks.
    if not candidate.is_relative_to(root):
        raise PermissionError(f"Path is outside the workspace: {relative_path}")

    return candidate