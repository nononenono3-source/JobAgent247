from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional


class FileSystemError(Exception):
    """Base exception for file utility errors."""


def safe_path(*parts: str | Path, create_parent: bool = True) -> Path:
    """
    Join path parts, resolve, and optionally create parent directory.
    Raises FileSystemError on validation failures.
    """
    if not parts:
        raise FileSystemError("safe_path requires at least one path component.")
    try:
        path = Path(*parts).resolve()
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except Exception as exc:
        raise FileSystemError(f"Failed to create or validate path for {parts}: {exc}") from exc


def write_text_atomic(path: str | Path, content: str, *, encoding: str = "utf-8", **kwargs: Any) -> None:
    """
    Atomically write text content to a file by writing to a temporary file
    in the same directory and then renaming it.
    """
    target_path = safe_path(path, create_parent=True)
    parent = target_path.parent
    fd, tmp_path_str = tempfile.mkstemp(dir=str(parent), prefix=f".{target_path.name}.")
    try:
        with os.fdopen(fd, "w", encoding=encoding, **kwargs) as f:
            f.write(content)
        os.replace(tmp_path_str, target_path)
    except Exception as exc:
        # Cleanup temp file on failure
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise FileSystemError(f"Atomic write to {path} failed: {exc}") from exc


def write_json_atomic(path: str | Path, data: Any, *, encoding: str = "utf-8", indent: int = 2, **kwargs: Any) -> None:
    """
    Atomically write JSON data to a file.
    """
    content = json.dumps(data, ensure_ascii=False, indent=indent, **kwargs)
    write_text_atomic(path, content, encoding=encoding)


def read_json_safe(path: str | Path) -> tuple[Optional[dict | list], Optional[str]]:
    """
    Read JSON file safely.
    Returns (data, error_message). On success, error_message is None.
    On failure, data is None.
    """
    target_path = Path(path)
    if not target_path.is_file():
        return None, f"File not found at {path}"
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as exc:
        return None, f"Corrupted JSON file at {path}: {exc}"
    except Exception as exc:
        return None, f"Failed to read file at {path}: {exc}"


def copy_file_safe(src: str | Path, dst: str | Path) -> None:
    """
    Copy a file, ensuring the destination directory exists.
    """
    try:
        dst_path = safe_path(dst, create_parent=True)
        shutil.copyfile(src, dst_path)
    except Exception as exc:
        raise FileSystemError(f"Failed to copy file from {src} to {dst}: {exc}") from exc
