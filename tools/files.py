"""
tools/files.py: the agent's file tools. Built one at a time; this step
adds read_file.

Story: a file tool is where three things meet. The path jail (safe_path)
keeps the agent inside the workspace. Paging keeps one read from flooding
the context, since every tool result is re-billed on later loop iterations.
And error messages are written for the MODEL: they say what went wrong and
what to try next.
"""

import os
import tempfile

import config
from tools.registry import ToolRegistry, object_schema
from tools.workspace import safe_path


registry = ToolRegistry()

# Room kept for the "[Showing lines ...]" footer, so that page + footer
# always fit under MAX_TOOL_OUTPUT_CHARS and run_tool_call's blunt
# truncation never has to fire.
FOOTER_RESERVE = 300


def read_page(text: str, start_line: int, max_lines: int, char_budget: int) -> str:
    """Return one page of `text`, with a footer if the file is not fully shown.

    Pure function (no disk, no config), so the paging rules are tested alone.
    """
    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return "[File is empty]"
    if start_line > total:
        raise ValueError(
            f"start_line {start_line} is past the end of the file, which has {total} lines."
        )

    chosen = []
    used = 0
    cut = False
    index = start_line - 1
    # Stop at whichever limit comes first: the line limit or the character
    # budget. The budget is the hard one; it protects our token bill.
    while index < total and len(chosen) < max_lines:
        line = lines[index]
        if used + len(line) + 1 > char_budget:
            if not chosen:
                # A single line bigger than the whole budget (a minified
                # file, say). Return a piece of it rather than nothing.
                chosen.append(line[:char_budget])
                cut = True
            break
        chosen.append(line)
        used += len(line) + 1
        index += 1

    last = start_line - 1 + len(chosen)
    body = "\n".join(chosen)

    # The whole file fit: no footer, no wasted tokens.
    if start_line == 1 and last == total and not cut:
        return body

    # The footer steers the model: it says exactly what to call next.
    note = f"Showing lines {start_line}-{last} of {total}."
    if cut:
        note += f" Line {last} was longer than the output limit and was cut."
    if last < total:
        note += f" To continue, call read_file with start_line={last + 1}."
    return f"{body}\n[{note}]"


@registry.tool(
    description=(
        "Read a UTF-8 text file from the workspace. Returns at most max_lines "
        "lines starting at start_line. If the file is longer, the result ends "
        "with a note saying how to read the next part."
    ),
    parameters=object_schema(
        {
            "path": {
                "type": "string",
                "description": "File path, relative to the workspace folder.",
            },
            "start_line": {
                "type": ["integer", "null"],
                "description": "First line to read, counting from 1. Use null to start at line 1.",
            },
            "max_lines": {
                "type": ["integer", "null"],
                "description": "Maximum number of lines to return. Use null for the default.",
            },
        }
    ),
)
def read_file(path, start_line=None, max_lines=None):
    # Jail first: nothing below touches the disk until the path is proven safe.
    target = safe_path(path)

    start = 1 if start_line is None else start_line
    limit = config.READ_DEFAULT_MAX_LINES if max_lines is None else max_lines
    if start < 1:
        raise ValueError("start_line must be 1 or greater.")
    if limit < 1:
        raise ValueError("max_lines must be 1 or greater.")

    # Errors below name the next step, so the model can recover on its own.
    if not target.exists():
        raise FileNotFoundError(
            f"File not found: {path}. Use list_dir to see what exists in the workspace."
        )
    if target.is_dir():
        raise IsADirectoryError(f"{path} is a directory. Use list_dir to see its contents.")

    size = target.stat().st_size
    if size > config.MAX_READ_FILE_BYTES:
        raise ValueError(
            f"{path} is {size:,} bytes, over the {config.MAX_READ_FILE_BYTES:,}-byte read limit."
        )

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"{path} is not a UTF-8 text file, so it cannot be read.") from None

    return read_page(
        text, start, limit, config.MAX_TOOL_OUTPUT_CHARS - FOOTER_RESERVE
    )


# --- write_file ---

def _write_atomically(target, content: str) -> None:
    """Write `content` so the old file survives if anything goes wrong.

    Story: writing straight into the real file means a failure halfway
    leaves it half-written. Instead we write the whole new content to a
    temp file first and only then swap it in with os.replace.
    """
    # The temp file lives in the SAME folder as the target: os.replace only
    # swaps within one filesystem, and a sibling file guarantees that.
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        # Explicit UTF-8, and "\n" newlines. Windows text mode would turn
        # every "\n" into "\r\n", so files would differ between machines.
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, target)
    except BaseException:
        # Leave no half-written temp file behind, then let the error go on.
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


@registry.tool(
    description=(
        "Write text to a file in the workspace, creating any missing folders. "
        "Set overwrite to false to create a new file: the call fails if the "
        "file already exists, which protects saved work. Set overwrite to true "
        "only to replace the full content of an existing file."
    ),
    parameters=object_schema(
        {
            "path": {
                "type": "string",
                "description": "File path, relative to the workspace folder.",
            },
            "content": {
                "type": "string",
                "description": "The full text to write, saved as UTF-8.",
            },
            "overwrite": {
                "type": "boolean",
                "description": "True to replace the file if it exists, false to fail if it exists.",
            },
        }
    ),
)
def write_file(path, content, overwrite):
    # Jail first: nothing below touches the disk until the path is proven safe.
    target = safe_path(path)

    if not isinstance(content, str):
        raise ValueError("content must be a string.")
    if len(content) > config.MAX_WRITE_CHARS:
        raise ValueError(
            f"content is {len(content):,} characters, over the "
            f"{config.MAX_WRITE_CHARS:,}-character limit. Split it across "
            "several files, or write a shorter version."
        )

    if target.is_dir():
        raise IsADirectoryError(f"{path} is a directory. Give a file path instead.")

    existed = target.exists()
    if existed and not overwrite:
        # The error names the next step, so the model can recover on its own.
        raise FileExistsError(
            f"{path} already exists. Call read_file to review it, then call "
            "write_file again with overwrite set to true to replace it."
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError):
        raise ValueError(
            f"A part of the path {path} is an existing file, not a folder."
        ) from None

    try:
        _write_atomically(target, content)
    except PermissionError:
        # On Windows os.replace fails when the file is open elsewhere. The
        # raw OS message is unhelpful, so we explain it.
        raise PermissionError(
            f"Could not write {path}. It may be open in another program or be read-only."
        ) from None

    verb = "Overwrote" if existed else "Created"
    return f"{verb} {path} ({len(content):,} characters)."


# --- list_dir ---

def format_listing(entries, limit: int, char_budget: int) -> str:
    """Turn (name, is_dir, size) tuples into the text the model sees.

    Pure function (no disk), so sorting and cutting are tested alone.
    """
    if not entries:
        return "[Folder is empty]"

    # Folders first, then files, each A-Z ignoring case. iterdir() gives no
    # guaranteed order, so we sort ourselves for predictable output.
    ordered = sorted(entries, key=lambda entry: (not entry[1], entry[0].lower()))

    lines = []
    used = 0
    for name, is_dir, size in ordered:
        if len(lines) >= limit:
            break
        if is_dir:
            line = f"{name}/"
        elif size is None:
            line = f"{name} (size unknown)"
        else:
            # Sizes let the model skip reading a huge file in full.
            line = f"{name} ({size:,} bytes)"
        # Stop at the character budget too, so the listing plus footer
        # always fit under MAX_TOOL_OUTPUT_CHARS.
        if used + len(line) + 1 > char_budget:
            break
        lines.append(line)
        used += len(line) + 1

    text = "\n".join(lines)
    if len(lines) < len(ordered):
        # The footer steers the model instead of just cutting the list.
        text += (
            f"\n[Showing {len(lines)} of {len(ordered)} entries. "
            "Call list_dir on a subfolder to narrow it down.]"
        )
    return text


@registry.tool(
    description=(
        "List the files and folders directly inside a workspace folder. "
        "Folders end with a slash, and files show their size in bytes. "
        'Use path "." for the workspace root.'
    ),
    parameters=object_schema(
        {
            "path": {
                "type": "string",
                "description": "Folder path, relative to the workspace folder.",
            },
        }
    ),
)
def list_dir(path):
    # Jail first: nothing below touches the disk until the path is proven safe.
    target = safe_path(path)

    # A brand-new workspace may not exist yet. That is an empty workspace,
    # not an error, and listing it must not create anything.
    root = config.WORKSPACE_DIR.resolve()
    if target == root and not target.exists():
        return "[Folder is empty]"

    # Errors below name the next step, so the model can recover on its own.
    if not target.exists():
        raise FileNotFoundError(
            f'Folder not found: {path}. Call list_dir with path "." to see the workspace root.'
        )
    if not target.is_dir():
        raise NotADirectoryError(f"{path} is a file. Use read_file to read it.")

    entries = []
    for child in target.iterdir():
        try:
            size = child.stat().st_size
        except OSError:
            size = None
        entries.append((child.name, child.is_dir(), size))

    return format_listing(
        entries,
        config.MAX_LIST_ENTRIES,
        config.MAX_TOOL_OUTPUT_CHARS - FOOTER_RESERVE,
    )

